# -*- coding=utf--8

import asyncio
import os
from qcloud_cos import CosConfig, CosS3Client, CosClientError, CosServiceError
# 假设您的 config.py 文件与此文件在同一目录或在 Python 路径中
from config import get_tencentcloud_cos_credentials, logger


class TencentCosService:
    """
    腾讯云对象存储(COS)服务类。
    封装了客户端初始化、文件上传、获取预签名URL等常用操作。
    """
    _instance = None

    def __new__(cls, *args, **kwargs):
        """
        使用单例模式，确保在整个应用中只有一个COS客户端实例。
        """
        if not cls._instance:
            cls._instance = super(TencentCosService, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        """
        初始化COS客户端。
        从配置文件中获取凭证，并创建S3客户端。
        """
        # 防止重复初始化
        self.client = None
        if hasattr(self, 'client') and self.client is not None:
            return

        self.logger = logger
        self.client = None
        self.bucket = None

        try:
            secret_id, secret_key, cos_bucket, cos_region = get_tencentcloud_cos_credentials()

            # 校验凭证是否完整
            if not all([secret_id, secret_key, cos_bucket, cos_region]):
                raise ValueError("Tencent COS credentials are not fully configured.")

            self.bucket = cos_bucket
            config = CosConfig(Region=cos_region, SecretId=secret_id, SecretKey=secret_key, Token=None)
            self.client = CosS3Client(config)

            self.logger.info("Tencent COS service initialized successfully.")
        except Exception as e:
            self.logger.error(f"Failed to initialize Tencent COS service: {e}", exc_info=True)
            # 初始化失败时，client 保持为 None，后续操作会安全失败。

    def upload_file(self, local_file_path: str, key: str = None, retries: int = 3) -> bool:
        """
        上传本地文件到COS，支持失败重试。

        :param local_file_path: 本地文件的完整路径。
        :param key: 上传到COS后的对象键名（文件名）。如果为None，则使用本地文件名。
        :param retries: 上传失败时的重试次数。
        :return: 上传成功返回 True，失败返回 False。
        """
        if not self.client:
            self.logger.error("COS client not initialized. Cannot upload file.")
            return False

        if not os.path.exists(local_file_path):
            self.logger.error(f"Local file not found: {local_file_path}")
            return False

        if key is None:
            key = os.path.basename(local_file_path)

        for i in range(retries):
            try:
                self.logger.info(
                    f"Attempting to upload '{local_file_path}' to COS key '{key}' (Attempt {i + 1}/{retries}).")
                # upload_file 是高级接口，本身支持断点续传
                response = self.client.upload_file(
                    Bucket=self.bucket,
                    Key=key,
                    LocalFilePath=local_file_path,
                    EnableMD5=False,  # 根据需要可以开启
                    progress_callback=None
                )
                self.logger.info(f"Successfully uploaded '{local_file_path}' to COS. ETag: {response.get('ETag')}")
                return True
            except (CosClientError, CosServiceError) as e:
                self.logger.warning(f"Upload attempt {i + 1}/{retries} failed for key '{key}': {e}")
                if i == retries - 1:  # 如果是最后一次尝试
                    self.logger.error(f"Failed to upload key '{key}' after {retries} attempts.")
                    return False

        return False  # 循环结束仍未成功

    async def upload_file_async(self, local_file_path: str, key: str = None, retries: int = 3) -> bool:
        """
        Asynchronously uploads a local file to COS using a thread pool.
        """
        return await asyncio.to_thread(self.upload_file, local_file_path, key, retries)

    def get_presigned_download_url(self, key: str, expiration_seconds: int = 3600) -> str or None:
        """
        为COS中的对象生成一个预签名的下载URL。

        :param key: COS中的对象键名（文件名）。
        :param expiration_seconds: URL的有效时间（秒）。默认为1小时。
        :return: 成功返回URL字符串，失败返回None。
        """
        if not self.client:
            self.logger.error("COS client not initialized. Cannot get presigned URL.")
            return None

        try:
            url = self.client.get_presigned_url(
                Method='GET',
                Bucket=self.bucket,
                Key=key,
                Expired=expiration_seconds
            )
            self.logger.info(f"Generated presigned URL for key '{key}'.")
            return url
        except (CosClientError, CosServiceError) as e:
            self.logger.error(f"Failed to generate presigned URL for key '{key}': {e}")
            return None
