# models/task.py
import enum
import uuid
from typing import Optional, List

from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, DateTime, Enum as EnumDB
from sqlalchemy import UUID
from sqlalchemy.sql import func

from database import Base


class TaskStatus(enum.Enum):
    PENDING = "PENDING"
    UPLOADING = "UPLOADING"
    AWAITING_ASR = "AWAITING_ASR"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TranscriptionTask(Base):
    __tablename__ = "transcription_tasks"

    id = Column(
        UUID(as_uuid=True),  # as_uuid=True 确保在 Python 代码中作为 uuid.UUID 对象处理
        primary_key=True,
        default=uuid.uuid4  # 使用 uuid.uuid4 作为默认值生成函数
    )
    batch_id = Column(UUID(as_uuid=True), index=True, nullable=True)  # 允许为空，因为单个任务可能没有批次ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    status = Column(EnumDB(TaskStatus), nullable=False, default=TaskStatus.PENDING)

    # 输入信息
    original_audio_path = Column(String, nullable=False)

    # COS 相关信息
    cos_bucket = Column(String, nullable=True)
    cos_key = Column(String, nullable=True)

    # ASR 相关信息
    asr_task_id = Column(Integer, nullable=True)

    # 结果
    transcription_result = Column(String, nullable=True)
    error_message = Column(String, nullable=True)


class BatchTranscriptionResults(BaseModel):
    batch_id: uuid.UUID
    status: TaskStatus  # "COMPLETED" or "IN_PROGRESS"
    message: Optional[str] = None
    results: Optional[List[str]] = None  # 只包含已完成任务的转写结果
    completed_count: int
    total_count: int
