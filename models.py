from enum import Enum
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field


# 定义 Webhook 事件类型枚举
class BililiveEventType(str, Enum):
    SESSION_STARTED = "SessionStarted"
    FILE_OPENING = "FileOpening"
    FILE_CLOSED = "FileClosed"
    SESSION_ENDED = "SessionEnded"
    STREAM_STARTED = "StreamStarted"
    STREAM_ENDED = "StreamEnded"


# 定义 Webhook 请求体的数据模型
class WebhookPayload(BaseModel):
    EventType: BililiveEventType = Field(..., description="事件类型")
    EventTimestamp: Optional[str] = Field(None, description="事件时间戳，ISO 8601 格式字符串")
    EventId: str = Field(..., description="事件的唯一随机ID，可用于判断重复事件")
    EventData: Dict[str, Any] = Field(..., description="事件的详细数据，是一个任意键值对的字典")


class CosUploadRequest(BaseModel):
    """
    上传文件到COS的请求体模型
    """
    local_file_path: str = Field(
        ...,
        description="文件在服务器上的绝对路径。",
        examples=["/path/to/my/video.mp4"]
    )
    cos_key: Optional[str] = Field(
        default=None,
        description="上传到COS后的对象键名（路径/文件名）。如果省略，将使用本地文件名。",
        examples=["videos/archive/video.mp4"]
    )


class CosUploadResponse(BaseModel):
    """
    上传成功的响应模型
    """
    message: str
    status: str = "success"
    bucket: str
    key: str


class CosUrlResponse(BaseModel):
    """
    获取预签名URL的响应模型
    """
    key: str
    url: str
    expires_in_seconds: int
