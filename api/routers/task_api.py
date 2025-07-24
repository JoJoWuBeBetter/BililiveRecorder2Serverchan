# routers/task_api.py
import uuid

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from config import logger
from crud.task_crud import create_task, get_task
from database import SessionLocal
from schemas.task import TaskCreate, Task
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


@router.get("/{task_id}", response_model=Task)
async def get_task_status(task_id: uuid.UUID, db: Session = Depends(get_db)):
    """
    根据任务ID查询任务的状态和结果。
    """
    db_task = get_task(db, task_id)
    if db_task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    return db_task
