# schemas/task.py
import uuid

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

from models.task import TaskStatus


class TaskCreate(BaseModel):
    local_audio_path: str
    engine_model_type: str = "16k_zh_large"  # 可以设置默认值或让用户指定
    channel_num: int = 1
    res_text_format: int = 0
    batch_id: Optional[uuid.UUID] = None
    hotword_id: Optional[str] = None


class Task(BaseModel):
    id: uuid.UUID
    batch_id: Optional[uuid.UUID] = None
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


class BatchTaskCreate(BaseModel):
    """批量创建任务的请求模型"""
    directory_path: str = Field(..., description="包含音频文件的服务器文件夹绝对路径。")
    file_extension: Optional[str] = Field(None,
                                          description="要处理的文件扩展名 (例如 'wav', 'mp3')。如果为 None，则处理所有文件。")

    # 这些参数将应用于目录中的所有文件
    engine_model_type: str = Field("16k_zh_large", description="ASR 引擎类型。")
    channel_num: int = Field(1, description="音频通道数。")
    res_text_format: int = Field(0, description="转写结果的格式。")
    hotword_id: Optional[str] = Field(None, description="热词表ID。")


class MultiFileTaskCreate(BaseModel):
    """面向浏览器多选文件的批量任务请求模型"""

    file_paths: List[str] = Field(..., description="待转写的文件路径列表（绝对或相对 VIDEO_DIRECTORY）。")
    engine_model_type: str = Field("16k_zh_large", description="ASR 引擎类型。")
    channel_num: int = Field(1, description="音频通道数。")
    res_text_format: int = Field(0, description="转写结果的格式。")
    hotword_id: Optional[str] = Field(None, description="热词表ID。")
