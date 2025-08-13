import logging
import uuid
from fastapi import APIRouter, HTTPException, status, Depends
from sqlalchemy.orm import Session
from models.webhook import WebhookPayload
from services import webhook_processor, serverchan  # 注意这里的导入路径
from database import SessionLocal
from crud.webhook_event_crud import create_webhook_event
from schemas.webhook_event import WebhookEventCreate

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
    logger.info(f"Received webhook: EventType={payload.EventType.value}, EventId={payload.EventId}")

    try:
        # 使用 webhook_processor 处理 webhook 负载，生成 ServerChan 消息详情
        message_details = webhook_processor.process_bililive_webhook_payload(payload)

        # 调用 ServerChan 服务发送消息
        serverchan_response = serverchan.send_serverchan_message(
            message_details["serverchan_title"],
            message_details["desp"],
            message_details["short_description"],
            message_details["tags"]
        )

        # 记录 webhook 事件到数据库（无论 ServerChan 成功与否都入库）
        try:
            event_data = payload.EventData or {}

            # 将 event_id 和 session_id 转为 uuid 类型
            try:
                _event_id = uuid.UUID(payload.EventId)
            except Exception:
                logger.warning(f"Invalid EventId format, cannot parse to UUID: {payload.EventId}")
                _event_id = uuid.uuid4()  # 兜底，尽量不阻塞入库

            _session_id = None
            if event_data.get("SessionId"):
                try:
                    _session_id = uuid.UUID(str(event_data.get("SessionId")))
                except Exception:
                    logger.warning(f"Invalid SessionId format, cannot parse to UUID: {event_data.get('SessionId')}")

            def _to_str(v):
                return str(v) if v is not None else None

            event_create = WebhookEventCreate(
                event_id=_event_id,
                event_type=payload.EventType.value,
                event_timestamp=payload.EventTimestamp,
                room_id=_to_str(event_data.get("RoomId")),
                short_id=_to_str(event_data.get("ShortId")),
                streamer_name=event_data.get("Name"),
                room_title=event_data.get("Title"),
                area_parent=event_data.get("AreaNameParent"),
                area_child=event_data.get("AreaNameChild"),
                recording=_to_str(event_data.get("Recording")),
                streaming=_to_str(event_data.get("Streaming")),
                danmaku_connected=_to_str(event_data.get("DanmakuConnected")),
                session_id=_session_id,
                relative_path=event_data.get("RelativePath"),
                file_size=_to_str(event_data.get("FileSize")),
                duration=_to_str(event_data.get("Duration")),
                file_open_time=event_data.get("FileOpenTime"),
                file_close_time=event_data.get("FileCloseTime"),
                raw_event_data=event_data,
                serverchan_sent=("success" if serverchan_response and serverchan_response.get("code") == 0 else "failure"),
                serverchan_response=serverchan_response,
                serverchan_title=message_details.get("serverchan_title"),
                serverchan_description=message_details.get("desp"),
            )
            create_webhook_event(db, event_create)
            logger.info(f"Webhook event saved. EventId={_event_id}")
        except Exception as e:
            logger.exception(f"Failed to persist webhook event EventId={payload.EventId}: {e}")

        # 根据 ServerChan 的响应判断是否成功
        if serverchan_response and serverchan_response.get("code") == 0:
            logger.info(f"Message for EventId={payload.EventId} successfully forwarded to ServerChan.")
            return {
                "message": "Webhook received and forwarded to ServerChan successfully.",
                "serverchan_status": "success",
                "serverchan_detail": serverchan_response
            }
        else:
            error_message = (serverchan_response or {}).get("message", "Unknown error from ServerChan.")
            logger.error(f"Failed to send message for EventId={payload.EventId} to ServerChan: {error_message}")
            # 这里保持原有的逻辑，即使 ServerChan 发送失败也返回 200 OK，但状态为 failure
            return {
                "message": "Webhook received, but ServerChan forwarding failed.",
                "serverchan_status": "failure",
                "serverchan_detail": serverchan_response
            }
    except Exception as e:
        logger.exception(f"An unexpected error occurred during webhook processing for EventId={payload.EventId}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process webhook due to an internal server error: {e}"
        )
