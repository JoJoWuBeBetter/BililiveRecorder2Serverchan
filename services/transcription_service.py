# services/transcription_service.py
import asyncio
import os
import uuid

from sqlalchemy.orm import Session

from config import logger
from crud import task_crud
from models.task import TaskStatus
from services.tencent_cloud_asr import TencentCloudASRService
from services.tencent_cloud_cos import TencentCosService


async def run_batch_transcription_pipeline(db: Session, task_ids: list[uuid.UUID], asr_params: dict):
    """
    Concurrently runs the transcription pipeline for a batch of tasks.
    """
    tasks = [run_transcription_pipeline(db, task_id, asr_params) for task_id in task_ids]
    await asyncio.gather(*tasks)


async def run_transcription_pipeline(db: Session, task_id: uuid.UUID, asr_params: dict):
    """
    完整的语音转写任务流程
    """
    try:
        # 1. 更新状态为上传中
        logger.info(f"[Task {task_id}] Status -> UPLOADING")
        task_crud.update_task(db, task_id, {"status": TaskStatus.UPLOADING})
        task = task_crud.get_task(db, task_id)

        # 2. 上传文件到 COS
        cos_service = TencentCosService()
        cos_key = f"{os.path.basename(task.original_audio_path)}"

        success = await cos_service.upload_file_async(local_file_path=task.original_audio_path, key=cos_key)
        if not success:
            raise RuntimeError(f"Failed to upload {task.original_audio_path} to COS.")

        logger.info(f"[Task {task_id}] File uploaded to COS. Key: {cos_key}")
        task_crud.update_task(db, task_id, {"cos_bucket": cos_service.bucket, "cos_key": cos_key})

        # 3. 获取 COS 临时链接
        # ASR 服务需要一个可公网访问的链接，预签名URL是最佳选择
        # 链接有效期应长于ASR处理时间，这里设为1小时
        presigned_url = cos_service.get_presigned_download_url(key=cos_key, expiration_seconds=3600)
        if not presigned_url:
            raise RuntimeError("Failed to generate presigned URL from COS.")

        logger.info(f"[Task {task_id}] Got presigned URL for ASR.")

        # 4. 创建 ASR 任务
        logger.info(f"[Task {task_id}] Status -> AWAITING_ASR. Creating ASR task...")
        task_crud.update_task(db, task_id, {"status": TaskStatus.AWAITING_ASR})

        asr_response = TencentCloudASRService.create_rec_task(
            engine_model_type=asr_params['engine_model_type'],
            channel_num=asr_params['channel_num'],
            res_text_format=asr_params['res_text_format'],
            source_type=0,  # 0 表示使用 URL
            url=presigned_url
        )
        asr_task_id = asr_response.Data.TaskId
        logger.info(f"[Task {task_id}] ASR task created with ID: {asr_task_id}")
        task_crud.update_task(db, task_id, {"asr_task_id": asr_task_id, "status": TaskStatus.PROCESSING})

        # 5. 轮询 ASR 任务结果
        logger.info(f"[Task {task_id}] Status -> PROCESSING. Polling for ASR result...")
        asr_result = await TencentCloudASRService.poll_task_status(task_id=asr_task_id)

        # 6. 任务完成，更新数据库
        final_transcription = asr_result.get("result", "No result text found.")
        logger.info(f"[Task {task_id}] Status -> COMPLETED. Transcription: {final_transcription[:100]}...")
        task_crud.update_task(db, task_id, {
            "status": TaskStatus.COMPLETED,
            "transcription_result": final_transcription
        })

    except Exception as e:
        error_message = str(e)
        logger.error(f"[Task {task_id}] Pipeline failed: {error_message}", exc_info=True)
        task_crud.update_task(db, task_id, {"status": TaskStatus.FAILED, "error_message": error_message})
