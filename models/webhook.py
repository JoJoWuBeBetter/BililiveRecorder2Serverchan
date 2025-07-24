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
