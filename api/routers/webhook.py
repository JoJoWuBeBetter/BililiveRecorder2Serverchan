import logging
from fastapi import APIRouter, HTTPException, status
from models import WebhookPayload
from services import webhook_processor, serverchan  # 注意这里的导入路径

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def receive_webhook(payload: WebhookPayload):
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

        # 根据 ServerChan 的响应判断是否成功
        if serverchan_response and serverchan_response.get("code") == 0:
            logger.info(f"Message for EventId={payload.EventId} successfully forwarded to ServerChan.")
            return {
                "message": "Webhook received and forwarded to ServerChan successfully.",
                "serverchan_status": "success",
                "serverchan_detail": serverchan_response
            }
        else:
            error_message = serverchan_response.get("message", "Unknown error from ServerChan.")
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
