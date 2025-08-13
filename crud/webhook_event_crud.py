# crud/webhook_event_crud.py
from typing import Optional
from sqlalchemy.orm import Session

from models.webhook_event import WebhookEvent
from schemas.webhook_event import WebhookEventCreate, WebhookEventUpdate


def create_webhook_event(db: Session, event_data: WebhookEventCreate) -> WebhookEvent:
    db_event = WebhookEvent(
        event_id=event_data.event_id,
        event_type=event_data.event_type,
        event_timestamp=event_data.event_timestamp,
        room_id=event_data.room_id,
        short_id=event_data.short_id,
        streamer_name=event_data.streamer_name,
        room_title=event_data.room_title,
        area_parent=event_data.area_parent,
        area_child=event_data.area_child,
        recording=event_data.recording,
        streaming=event_data.streaming,
        danmaku_connected=event_data.danmaku_connected,
        session_id=event_data.session_id,
        relative_path=event_data.relative_path,
        file_size=event_data.file_size,
        duration=event_data.duration,
        file_open_time=event_data.file_open_time,
        file_close_time=event_data.file_close_time,
        raw_event_data=event_data.raw_event_data,
        serverchan_sent=event_data.serverchan_sent,
        serverchan_response=event_data.serverchan_response,
        serverchan_title=event_data.serverchan_title,
        serverchan_description=event_data.serverchan_description,
    )
    db.add(db_event)
    db.commit()
    db.refresh(db_event)
    return db_event


def update_webhook_event(db: Session, event_id, updates: WebhookEventUpdate) -> Optional[WebhookEvent]:
    event = db.query(WebhookEvent).filter_by(event_id=event_id).first()
    if not event:
        return None
    for key, value in updates.model_dump(exclude_unset=True).items():
        if hasattr(event, key):
            setattr(event, key, value)
    db.commit()
    db.refresh(event)
    return event


def get_webhook_event_by_event_id(db: Session, event_id) -> Optional[WebhookEvent]:
    return db.query(WebhookEvent).filter_by(event_id=event_id).first()


def list_webhook_events(db: Session, limit: int = 50, offset: int = 0):
    return db.query(WebhookEvent).order_by(WebhookEvent.created_at.desc()).offset(offset).limit(limit).all()