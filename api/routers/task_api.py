# routers/task_api.py
import os
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from config import logger, VIDEO_DIRECTORY
from crud.task_crud import create_task, get_task, get_tasks_by_batch_id, list_tasks
from database import SessionLocal
from models.task import BatchTranscriptionResults, TaskStatus
from schemas.task import TaskCreate, Task, MultiFileTaskCreate
from services import transcription_service, ffmpeg_service

router = APIRouter(
    prefix="/tasks",
    tags=["Transcription Tasks"]
)

AUDIO_EXTENSIONS = {".aac", ".mp3", ".flac", ".wav", ".m4a", ".ogg"}
VIDEO_EXTENSIONS = {".mp4", ".flv", ".mkv", ".avi", ".mov", ".m4v", ".ts"}


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _resolve_audio_path(source_path: str) -> str:
    """根据扩展名决定直接使用音频或先从视频中提取音频。"""

    extension = os.path.splitext(source_path)[1].lower()
    if extension in AUDIO_EXTENSIONS:
        return source_path
    if extension in VIDEO_EXTENSIONS:
        extracted = ffmpeg_service.extract_aac_audio(source_path)
        if not extracted:
            raise RuntimeError(f"Failed to extract audio from video: {source_path}")
        return extracted

    raise RuntimeError(f"Unsupported file type for transcription: {source_path}")


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


@router.post("/multi-file-transcription", status_code=status.HTTP_202_ACCEPTED, response_model=List[Task])
async def create_multi_file_transcription_task(
        payload: MultiFileTaskCreate,
        background_tasks: BackgroundTasks,
        db: Session = Depends(get_db)
):
    """为浏览器多选的音视频文件创建转写任务。"""

    if not payload.file_paths:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请至少选择一个文件")

    logger.info(f"Received multi-file transcription request for {len(payload.file_paths)} items")

    asr_params = {
        "engine_model_type": payload.engine_model_type,
        "channel_num": payload.channel_num,
        "res_text_format": payload.res_text_format,
        "hotword_id": payload.hotword_id
    }

    created_tasks: List[Task] = []
    task_ids: List[uuid.UUID] = []
    errors: List[str] = []
    batch_id = uuid.uuid4()

    for provided_path in payload.file_paths:
        absolute_path = provided_path if os.path.isabs(provided_path) else os.path.join(VIDEO_DIRECTORY, provided_path)

        if not os.path.isfile(absolute_path):
            errors.append(f"File not found: {provided_path}")
            logger.warning(f"Skipped non-existent path: {absolute_path}")
            continue

        try:
            audio_path = _resolve_audio_path(absolute_path)
        except Exception as exc:  # noqa: BLE001 - keep detailed feedback
            error_message = f"Skip {provided_path}: {exc}"
            errors.append(error_message)
            logger.warning(error_message)
            continue

        single_task_data = TaskCreate(
            local_audio_path=audio_path,
            engine_model_type=payload.engine_model_type,
            channel_num=payload.channel_num,
            res_text_format=payload.res_text_format,
            hotword_id=payload.hotword_id,
            batch_id=batch_id,
        )

        db_task = create_task(db=db, task_data=single_task_data)
        created_tasks.append(db_task)
        task_ids.append(db_task.id)

        logger.info(f"Prepared transcription task for {provided_path} -> {audio_path}")

    if not created_tasks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="未找到可处理的音频或视频文件。")

    if errors:
        logger.warning(f"Some files were skipped: {'; '.join(errors)}")

    background_tasks.add_task(transcription_service.run_batch_transcription_pipeline, db, task_ids, asr_params)

    return created_tasks


@router.get("/", response_model=List[Task])
async def get_recent_tasks(limit: int = 200, db: Session = Depends(get_db)):
    """列出最近的转写任务，按创建时间倒序排列。"""

    return list_tasks(db, limit=limit)


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
