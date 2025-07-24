# schemas/task.py
import uuid

from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from models.task import TaskStatus


class TaskCreate(BaseModel):
    local_audio_path: str
    engine_model_type: str = "16k_zh_large"  # 可以设置默认值或让用户指定
    channel_num: int = 1
    res_text_format: int = 0


class Task(BaseModel):
    id: uuid.UUID
    status: TaskStatus
    original_audio_path: str
    cos_key: Optional[str] = None
    asr_task_id: Optional[int] = None
    transcription_result: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
