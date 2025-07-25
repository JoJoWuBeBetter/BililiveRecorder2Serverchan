# routers/task_api.py
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from config import logger
from crud.task_crud import create_task, get_task
from database import SessionLocal
from schemas.task import TaskCreate, Task, BatchTaskCreate
from services import transcription_service

router = APIRouter(
    prefix="/tasks",
    tags=["Transcription Tasks"]
)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/audio-transcription", status_code=status.HTTP_202_ACCEPTED, response_model=Task)
async def create_transcription_task(
        task_request: TaskCreate,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
):
    """
    创建一个新的语音转写任务。

    此接口会立即返回，任务将在后台执行。
    - **local_audio_path**: 服务器上音频文件的绝对路径。
    - **engine_model_type**: ASR 引擎类型，例如 '16k_zh'。
    """
    logger.info(f"Received transcription request for: {task_request.local_audio_path}")

    # 1. 在数据库中创建任务记录
    db_task = create_task(db=db, task_data=task_request)

    # 2. 将耗时任务添加到后台执行
    asr_params = {
        "engine_model_type": task_request.engine_model_type,
        "channel_num": task_request.channel_num,
        "res_text_format": task_request.res_text_format,
    }
    background_tasks.add_task(transcription_service.run_transcription_pipeline, db, db_task.id, asr_params)

    logger.info(f"Task {db_task.id} created and scheduled for background processing.")

    # 3. 立即返回任务初始信息
    return db_task


@router.post("/batch-audio-transcription", status_code=status.HTTP_202_ACCEPTED, response_model=List[Task])
async def create_batch_transcription_task(
        batch_request: BatchTaskCreate,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
):
    """
    从指定文件夹中批量创建语音转写任务。

    此接口会立即返回，所有找到的文件的转写任务都将在后台执行。

    - **directory_path**: 服务器上包含音频文件的文件夹绝对路径。
    - **file_extension**: (可选) 要筛选的文件扩展名，例如 'wav' 或 'mp3'。不提供则处理文件夹内所有文件。
    - **engine_model_type**: 应用于所有文件的 ASR 引擎类型。
    """
    logger.info(f"Received batch transcription request for directory: {batch_request.directory_path}")

    # --- 1. 验证文件夹路径是否存在 ---
    if not os.path.isdir(batch_request.directory_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directory not found: {batch_request.directory_path}"
        )

    created_tasks = []
    asr_params = {
        "engine_model_type": batch_request.engine_model_type,
        "channel_num": batch_request.channel_num,
        "res_text_format": batch_request.res_text_format,
    }

    # --- 2. 遍历文件夹中的文件 ---
    for filename in os.listdir(batch_request.directory_path):
        full_path = os.path.join(batch_request.directory_path, filename)

        # 检查是否是文件，而不是子文件夹
        if not os.path.isfile(full_path):
            continue

        # 检查文件扩展名是否匹配 (如果提供了该选项)
        if batch_request.file_extension and not filename.lower().endswith(f".{batch_request.file_extension.lower()}"):
            continue

        logger.info(f"Found matching file: {full_path}")

        # --- 3. 为每个文件创建任务 ---
        # a. 构造单个任务的请求数据
        single_task_data = TaskCreate(
            local_audio_path=full_path,
            engine_model_type=batch_request.engine_model_type,
            channel_num=batch_request.channel_num,
            res_text_format=batch_request.res_text_format,
        )

        # b. 在数据库中创建任务记录
        db_task = create_task(db=db, task_data=single_task_data)

        # c. 将耗时任务添加到后台执行
        background_tasks.add_task(transcription_service.run_transcription_pipeline, db, db_task.id, asr_params)

        created_tasks.append(db_task)

    if not created_tasks:
        logger.warning(
            f"No matching files found in {batch_request.directory_path} with extension '{batch_request.file_extension}'")
    else:
        logger.info(f"Scheduled {len(created_tasks)} tasks from directory {batch_request.directory_path}.")

    # --- 4. 立即返回所有已创建任务的初始信息 ---
    return created_tasks


@router.get("/{task_id}", response_model=Task)
async def get_task_status(task_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    根据任务ID查询任务的状态和结果。
    """
    db_task = get_task(db, task_id)
    if db_task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return db_task
