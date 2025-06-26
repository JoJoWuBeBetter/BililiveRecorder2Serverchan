# services/tencent_cloud_asr.py
import asyncio
import json
from typing import Optional, Dict, Any
from fastapi import HTTPException, status

from tencentcloud.asr.v20190614 import asr_client, models
from tencentcloud.asr.v20190614.models import CreateRecTaskResponse, DescribeTaskStatusResponse
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile

from config import get_tencentcloud_credentials, logger  # 从 config 导入 logger

# 获取腾讯云凭证
SECRET_ID, SECRET_KEY = get_tencentcloud_credentials()


class TencentCloudASRService:
    """
    封装腾讯云语音识别 (ASR) 服务。
    """
    _client = None

    @classmethod
    def _get_asr_client(cls) -> asr_client.AsrClient:
        """
        获取或创建 ASR 客户端实例。
        使用类方法和缓存确保客户端只被初始化一次。
        """
        if cls._client is None:
            if not SECRET_ID or not SECRET_KEY:
                logger.error("Tencent Cloud SecretId or SecretKey is not set. ASR client cannot be initialized.")
                raise ValueError("Tencent Cloud credentials are not configured.")

            try:
                # 实例化一个认证对象
                cred = credential.Credential(SECRET_ID, SECRET_KEY)

                # 实例化一个http选项
                http_profile = HttpProfile()
                http_profile.endpoint = "asr.tencentcloudapi.com"

                # 实例化一个client选项
                client_profile = ClientProfile()
                client_profile.httpProfile = http_profile

                # 实例化要请求产品的client对象
                cls._client = asr_client.AsrClient(cred, "ap-guangzhou", client_profile)  # 建议指定地域，这里以广州为例
                logger.info("Tencent Cloud ASR client initialized successfully.")
            except Exception as e:
                logger.exception(f"Failed to initialize Tencent Cloud ASR client: {e}")
                raise

        return cls._client

    @classmethod
    def create_rec_task(
            cls,
            engine_model_type: str,
            channel_num: int,
            res_text_format: int,
            source_type: int,
            url: Optional[str] = None,
            data: Optional[str] = None,  # Base64 编码的音频数据
            data_len: Optional[int] = None
            # ... 可以添加更多你可能需要的参数
    ) -> CreateRecTaskResponse:
        """
        创建语音识别任务。
        根据腾讯云 ASR 的 CreateRecTask 接口参数封装。
        详见：https://cloud.tencent.com/document/api/1093/35646
        """
        try:
            client = cls._get_asr_client()
            req = models.CreateRecTaskRequest()

            req.EngineModelType = engine_model_type
            req.ChannelNum = channel_num
            req.ResTextFormat = res_text_format
            req.SourceType = source_type

            if req.SourceType == 0:
                req.Url = url
            elif data and data_len is not None:
                req.Data = data
                req.DataLen = data_len
            else:
                raise ValueError("Either 'url' or 'data' and 'data_len' must be provided for ASR task.")

            resp = client.CreateRecTask(req)
            logger.info(f"Tencent Cloud ASR task created successfully. Task ID: {resp.Data.TaskId}")
            return resp

        except TencentCloudSDKException as err:
            logger.error(f"Tencent Cloud ASR SDK Exception: {err}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Tencent Cloud ASR service error: {err.get_message()}"
            )
        except ValueError as ve:
            logger.error(f"Invalid parameters for ASR task: {ve}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid parameters for ASR task: {ve}"
            )
        except Exception as e:
            logger.exception(f"An unexpected error occurred during Tencent Cloud ASR task creation: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred during ASR task creation: {e}"
            )

    @classmethod
    async def describe_task_status(cls, task_id: int) -> DescribeTaskStatusResponse:
        """
        查询语音识别任务状态。
        详见：https://cloud.tencent.com/document/api/1093/35648
        """
        try:
            client = cls._get_asr_client()
            req = models.DescribeTaskStatusRequest()
            params = {"TaskId": task_id}
            req.from_json_string(json.dumps(params))

            resp = client.DescribeTaskStatus(req)
            logger.info(f"Tencent Cloud ASR task status for Task ID {task_id}: {resp.Data.StatusStr}")
            return resp

        except TencentCloudSDKException as err:
            logger.error(f"Tencent Cloud ASR SDK Exception for task status: {err}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Tencent Cloud ASR task status error: {err.get_message()}"
            )
        except Exception as e:
            logger.exception(f"An unexpected error occurred during Tencent Cloud ASR task status query: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"An unexpected error occurred during ASR task status query: {e}"
            )

    @classmethod
    async def poll_task_status(cls, task_id: int, timeout: int = 600, interval: int = 5) -> Dict[str, Any]:
        """
        异步轮询 ASR 任务状态，直到完成或超时。
        返回包含任务最终状态和结果的字典。

        :param task_id: 语音识别任务ID
        :param timeout: 轮询总超时时间（秒），默认为 600 秒 (10 分钟)
        :param interval: 轮询间隔时间（秒），默认为 5 秒
        :return: 任务完成后的结果字典，包含 'status', 'result', 'error_msg' 等
        :raises HTTPException: 如果任务失败或超时，或者查询状态时出现问题
        """
        start_time = asyncio.get_event_loop().time()
        logger.info(f"Starting polling for ASR task {task_id} with timeout {timeout}s and interval {interval}s.")

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                resp = await cls.describe_task_status(task_id)
                status_str = resp.Data.StatusStr
                status_code = resp.Data.Status

                logger.debug(f"ASR task {task_id} current status: {status_str} ({status_code})")

                if status_code == 2 and status_str == "success":  # 任务成功
                    result_text = resp.Data.Result
                    logger.info(f"ASR task {task_id} completed successfully. Result: {result_text[:50]}...")  # 打印部分结果
                    return {
                        "task_id": task_id,
                        "status": "success",
                        "result": result_text,
                        "audio_duration": resp.Data.AudioDuration,
                        "full_response_data": resp.Data  # 返回完整的 TaskStatus 数据
                    }
                elif status_code == 3 and status_str == "failed":  # 任务失败
                    error_msg = resp.Data.ErrorMsg
                    logger.error(f"ASR task {task_id} failed. Error: {error_msg}")
                    raise HTTPException(
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail=f"ASR task {task_id} failed: {error_msg}"
                    )
                else:  # 任务仍在等待或执行中
                    logger.info(f"ASR task {task_id} status: {status_str}. Polling again in {interval} seconds.")

            except HTTPException as e:
                # describe_task_status 抛出的 HTTPException 直接向上抛
                raise e
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON response for ASR task {task_id}.", exc_info=True)
                # 可以选择在这里重试或抛出错误
            except Exception as e:
                # 其他未知异常，日志记录后重试（如果不是致命错误）
                logger.warning(f"An unexpected error occurred while polling ASR task {task_id}: {e}. Retrying...",
                               exc_info=True)

            await asyncio.sleep(interval)  # 异步等待

        logger.error(f"ASR task {task_id} timed out after {timeout} seconds.")
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,  # 504 Gateway Timeout 是一个合适的超时状态码
            detail=f"ASR task {task_id} timed out after {timeout} seconds."
        )
