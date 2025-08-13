# schemas/webhook_event.py
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from pydantic import BaseModel


class WebhookEventCreate(BaseModel):
    """创建 Webhook 事件的请求模型"""
    event_id: uuid.UUID
    event_type: str
    event_timestamp: Optional[str] = None
    room_id: Optional[str] = None
    short_id: Optional[str] = None
    streamer_name: Optional[str] = None
    room_title: Optional[str] = None
    area_parent: Optional[str] = None
    area_child: Optional[str] = None
    recording: Optional[str] = None
    streaming: Optional[str] = None
    danmaku_connected: Optional[str] = None
    session_id: Optional[uuid.UUID] = None
    relative_path: Optional[str] = None
    file_size: Optional[str] = None
    duration: Optional[str] = None
    file_open_time: Optional[str] = None
    file_close_time: Optional[str] = None
    raw_event_data: Dict[str, Any]
    serverchan_sent: Optional[str] = None
    serverchan_response: Optional[Dict[str, Any]] = None
    serverchan_title: Optional[str] = None
    serverchan_description: Optional[str] = None


class WebhookEvent(BaseModel):
    """Webhook 事件的响应模型"""
    event_id: uuid.UUID
    event_type: str
    event_timestamp: Optional[str] = None
    created_at: datetime
    room_id: Optional[str] = None
    short_id: Optional[str] = None
    streamer_name: Optional[str] = None
    room_title: Optional[str] = None
    area_parent: Optional[str] = None
    area_child: Optional[str] = None
    recording: Optional[str] = None
    streaming: Optional[str] = None
    danmaku_connected: Optional[str] = None
    session_id: Optional[uuid.UUID] = None
    relative_path: Optional[str] = None
    file_size: Optional[str] = None
    duration: Optional[str] = None
    file_open_time: Optional[str] = None
    file_close_time: Optional[str] = None
    raw_event_data: Dict[str, Any]
    serverchan_sent: Optional[str] = None
    serverchan_response: Optional[Dict[str, Any]] = None
    serverchan_title: Optional[str] = None
    serverchan_description: Optional[str] = None

    class Config:
        from_attributes = True


class WebhookEventUpdate(BaseModel):
    """更新 Webhook 事件的请求模型"""
    serverchan_sent: Optional[str] = None
    serverchan_response: Optional[Dict[str, Any]] = None