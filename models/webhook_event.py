# models/webhook_event.py
import uuid
from typing import Optional
from datetime import datetime

from sqlalchemy import Column, String, DateTime, JSON, UUID, Text
from sqlalchemy.sql import func

from database import Base


class WebhookEvent(Base):
    """存储 Webhook 事件信息的数据库模型"""
    __tablename__ = "webhook_events"

    # 使用外部提供的 event_id 作为主键（UUID）
    event_id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False
    )
    event_type = Column(String, nullable=False, index=True)  # 事件类型
    event_timestamp = Column(String, nullable=True)  # 原始时间戳字符串
    created_at = Column(DateTime(timezone=True), server_default=func.now())  # 入库时间
    
    # 房间和主播信息
    room_id = Column(String, nullable=True, index=True)
    short_id = Column(String, nullable=True)
    streamer_name = Column(String, nullable=True, index=True)
    room_title = Column(String, nullable=True)
    area_parent = Column(String, nullable=True)
    area_child = Column(String, nullable=True)
    
    # 状态信息
    recording = Column(String, nullable=True)  # 存储为字符串，因为可能为 null
    streaming = Column(String, nullable=True)
    danmaku_connected = Column(String, nullable=True)
    
    # 会话和文件信息（可选）
    session_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    relative_path = Column(String, nullable=True)
    file_size = Column(String, nullable=True)
    duration = Column(String, nullable=True)
    file_open_time = Column(String, nullable=True)
    file_close_time = Column(String, nullable=True)
    
    # 原始事件数据（JSON格式存储完整信息）
    raw_event_data = Column(JSON, nullable=False)
    
    # ServerChan 发送状态
    serverchan_sent = Column(String, nullable=True)  # success/failure/null
    serverchan_response = Column(JSON, nullable=True)  # ServerChan 响应信息
    serverchan_title = Column(Text, nullable=True)
    serverchan_description = Column(Text, nullable=True)

    def __repr__(self):
        return f"<WebhookEvent(event_type={self.event_type}, event_id={self.event_id}, room_id={self.room_id})>"