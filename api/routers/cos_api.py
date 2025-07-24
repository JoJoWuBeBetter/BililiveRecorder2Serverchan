# routers/cos_api.py

import os
from fastapi import APIRouter, HTTPException, status, Query
from config import logger  # 从您的全局配置导入 logger
from services.tencent_cloud_cos import TencentCosService
from models import CosUploadRequest, CosUploadResponse, CosUrlResponse

# 创建一个新的 APIRouter 实例
router = APIRouter(
    prefix="/cos",  # 为此路由下的所有路径添加/cos前缀
    tags=["Tencent COS"]  # 在OpenAPI文档中为这些接口分组
)

# 初始化COS服务，单例模式确保只有一个实例
try:
    cos_service = TencentCosService()
except Exception as e:
    # 如果在启动时初始化失败，cos_service会是None或包含一个无效的client
    # 在每个端点中检查其可用性
    cos_service = None
    logger.error(f"Critical: Failed to initialize TencentCosService at startup: {e}")


def get_cos_service() -> TencentCosService:
    """
    依赖注入函数，确保COS服务已成功初始化。
    """
    if not cos_service or not cos_service.client:
        logger.error("COS service is not available or failed to initialize.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="COS service is not properly configured or available."
        )
    return cos_service


@router.post(
    "/upload",
    response_model=CosUploadResponse,
    summary="Upload a local file to COS"
)
async def upload_file_to_cos(payload: CosUploadRequest):
    """
    接收一个包含本地文件路径的请求，将其上传到腾讯云COS。
    """
    service = get_cos_service()
    logger.info(f"Received request to upload file: {payload.local_file_path}")

    # 校验本地文件是否存在
    if not os.path.exists(payload.local_file_path):
        logger.error(f"File not found on server: {payload.local_file_path}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"The specified local file does not exist on the server: {payload.local_file_path}"
        )

    try:
        # 调用服务进行上传
        success = service.upload_file(
            local_file_path=payload.local_file_path,
            key=payload.cos_key
        )

        if success:
            # 如果未指定key，服务会使用文件名，我们需要获取它
            final_key = payload.cos_key or os.path.basename(payload.local_file_path)
            logger.info(f"Successfully uploaded {payload.local_file_path} to COS as {final_key}")
            return CosUploadResponse(
                message="File uploaded successfully to COS.",
                bucket=service.bucket,
                key=final_key
            )
        else:
            # 如果服务返回False，表示重试后仍然失败
            logger.error(f"Failed to upload {payload.local_file_path} to COS after retries.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to upload file to COS. Check server logs for details."
            )
    except Exception as e:
        logger.exception(f"An unexpected error occurred during file upload: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}"
        )


@router.get(
    "/download-url",
    response_model=CosUrlResponse,
    summary="Get a presigned download URL for a COS object"
)
async def get_presigned_url(
        key: str = Query(..., description="The object key (path/filename) in COS.",
                         examples=["videos/archive/video.mp4"]),
        expires_in: int = Query(3600, description="The URL's validity duration in seconds.", ge=1, le=604800)
        # 1s to 7days
):
    """
    为COS中的指定对象生成一个有时效性的预签名下载链接。
    """
    service = get_cos_service()
    logger.info(f"Requesting presigned URL for key: {key} with expiration: {expires_in}s")

    try:
        url = service.get_presigned_download_url(key=key, expiration_seconds=expires_in)
        if url:
            logger.info(f"Successfully generated presigned URL for key: {key}")
            return CosUrlResponse(
                key=key,
                url=url,
                expires_in_seconds=expires_in
            )
        else:
            # 服务返回None表示生成失败
            logger.error(f"Failed to generate presigned URL for key: {key}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate presigned URL. The key might not exist or there was a service error."
            )
    except Exception as e:
        logger.exception(f"An unexpected error occurred while generating presigned URL: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An internal error occurred: {e}"
        )
