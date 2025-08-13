import logging
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from models.webhook import WebhookPayload
from services import webhook_service
from database import SessionLocal

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def receive_webhook(payload: WebhookPayload, db: Session = Depends(get_db)):
    try:
        return webhook_service.handle_webhook(payload, db)
    except Exception as e:
        logger.exception(f"An unexpected error occurred during webhook processing for EventId={payload.EventId}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process webhook due to an internal server error: {e}"
        )
