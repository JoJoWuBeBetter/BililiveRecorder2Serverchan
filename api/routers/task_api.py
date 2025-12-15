# routers/task_api.py
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from config import logger, VIDEO_DIRECTORY
from crud.task_crud import create_task, get_task, get_tasks_by_batch_id
from database import SessionLocal
from models.task import BatchTranscriptionResults, TaskStatus
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

    if not os.path.isabs(task_request.local_audio_path):
        logger.warning(f"Received relative path: {task_request.local_audio_path}. Converting to absolute path.")
        # 如果接收到的是相对路径，则会基于预设的 `VIDEO_DIRECTORY` 将其转换为绝对路径。
        # 注意：`VIDEO_DIRECTORY` 必须在 `config.py` 中正确配置。
        task_request.local_audio_path = os.path.join(VIDEO_DIRECTORY, task_request.local_audio_path)
        logger.info(f"Converted to absolute path: {task_request.local_audio_path}")

    # 1. 在数据库中创建任务记录
    db_task = create_task(db=db, task_data=task_request)

    # 2. 将耗时任务添加到后台执行
    asr_params = {
        "engine_model_type": task_request.engine_model_type,
        "channel_num": task_request.channel_num,
        "res_text_format": task_request.res_text_format,
        "hotword_id": task_request.hotword_id
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

    # Convert relative path to absolute path if necessary
    if not os.path.isabs(batch_request.directory_path):
        logger.warning(f"Received relative path: {batch_request.directory_path}. Converting to absolute path.")
        batch_request.directory_path = os.path.join(VIDEO_DIRECTORY, batch_request.directory_path)
        logger.info(f"Converted to absolute path: {batch_request.directory_path}")

    # --- 1. 验证文件夹路径是否存在 ---
    if not os.path.isdir(batch_request.directory_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Directory not found: {batch_request.directory_path}"
        )

    created_tasks = []
    task_ids = []
    asr_params = {
        "engine_model_type": batch_request.engine_model_type,
        "channel_num": batch_request.channel_num,
        "res_text_format": batch_request.res_text_format,
        "hotword_id": batch_request.hotword_id
    }

    batch_id = uuid.uuid4()

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
            batch_id=batch_id,
            hotword_id=batch_request.hotword_id
        )

        # b. 在数据库中创建任务记录
        db_task = create_task(db=db, task_data=single_task_data)

        created_tasks.append(db_task)
        task_ids.append(db_task.id)

    if not created_tasks:
        logger.warning(
            f"No matching files found in {batch_request.directory_path} with extension '{batch_request.file_extension}'")
    else:
        background_tasks.add_task(transcription_service.run_batch_transcription_pipeline, db, task_ids, asr_params)
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


@router.get("/batch/{batch_id}/results", response_model=BatchTranscriptionResults)
async def get_batch_transcription_results(
        batch_id: uuid.UUID,
        db: Session = Depends(get_db)
):
    """
    根据批量任务ID查询所有关联任务的状态和转写结果。
    如果批量任务中所有子任务都已完成，则返回所有转写结果。
    否则，返回一个提示信息，指出任务仍在处理中。
    """
    logger.info(f"Received request for batch transcription results for batch_id: {batch_id}")

    # 1. 查询该批量ID下的所有任务
    tasks = get_tasks_by_batch_id(db, batch_id)

    # Ensure tasks are processed in order of their original audio path
    tasks = sorted(tasks, key=lambda task: task.original_audio_path)

    if not tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No tasks found for batch_id: {batch_id}"
        )

    all_completed = True
    transcription_results_list = []
    completed_count = 0
    total_count = len(tasks)

    # 2. 遍历所有任务，检查状态并收集结果
    for task in tasks:
        if task.status == TaskStatus.COMPLETED:
            completed_count += 1
            if task.transcription_result:  # 确保结果不为空
                transcription_results_list.append(task.transcription_result)
        else:
            all_completed = False  # 发现有未完成的任务

    # 3. 根据是否全部完成构造响应
    if all_completed:
        logger.info(f"All {total_count} tasks in batch {batch_id} are completed.")
        return BatchTranscriptionResults(
            batch_id=batch_id,
            status=TaskStatus.COMPLETED,
            results=transcription_results_list,
            completed_count=completed_count,
            total_count=total_count
        )
    else:
        logger.info(f"Batch {batch_id} is still in progress. {completed_count}/{total_count} tasks completed.")
        return BatchTranscriptionResults(
            batch_id=batch_id,
            status=TaskStatus.PROCESSING,
            message=f"Batch tasks are still processing. {completed_count}/{total_count} tasks completed.",
            completed_count=completed_count,
            total_count=total_count
        )
