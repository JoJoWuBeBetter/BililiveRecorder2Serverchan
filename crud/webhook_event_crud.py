# crud/webhook_event_crud.py
from typing import Optional
from sqlalchemy.orm import Session

from models.webhook_event import WebhookEvent
from schemas.webhook_event import WebhookEventCreate, WebhookEventUpdate


def create_webhook_event(db: Session, event_data: WebhookEventCreate) -> WebhookEvent:
    db_event = WebhookEvent(**event_data.model_dump())
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