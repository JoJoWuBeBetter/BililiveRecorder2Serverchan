import logging
import os
import uuid
import json
from typing import Dict, Any

from sqlalchemy.orm import Session

from models.webhook import WebhookPayload, BililiveEventType
from services import serverchan, ffmpeg_service
from crud.webhook_event_crud import create_webhook_event, update_webhook_event
from schemas.webhook_event import WebhookEventCreate, WebhookEventUpdate
from config import VIDEO_DIRECTORY
from constants import (
    EMOJI_NOTIFICATION, EMOJI_START, EMOJI_STOP, EMOJI_RECORD,
    EMOJI_FILE_OPEN, EMOJI_FILE_CLOSE, EMOJI_LIVE, EMOJI_OFFLINE,
    EMOJI_CHECK, EMOJI_CROSS, EMOJI_INFO, EMOJI_BULLET
)
from utils import format_bool_emoji, format_file_size, format_duration


logger = logging.getLogger(__name__)


def _generate_serverchan_message(payload: WebhookPayload) -> Dict[str, Any]:
    """
    根据录播姬 Webhook 事件生成 ServerChan 消息的标题、内容和标签。
    返回一个字典，包含 'serverchan_title', 'desp', 'short_description', 'tags'。
    """
    event_data = payload.EventData
    room_id = event_data.get("RoomId", "N/A")
    short_id = event_data.get("ShortId", "N/A")
    name = event_data.get("Name", "未知主播")
    title = event_data.get("Title", "未知标题")
    area_parent = event_data.get("AreaNameParent", "N/A")
    area_child = event_data.get("AreaNameChild", "N/A")

    tags = f"录播姬|{name}"
    serverchan_title = ""
    short_description = ""
    event_display_name = ""
    specific_details = []

    if payload.EventType == BililiveEventType.SESSION_STARTED:
        session_id = event_data.get("SessionId", "N/A")
        serverchan_title = f"{EMOJI_RECORD} {name} 开始录制了！"
        short_description = f"主播 {name} (房间: {room_id}) 的直播录制已开始。"
        event_display_name = "录制开始"
        tags += "|录制开始"
        specific_details = [
            f"{EMOJI_BULLET} **会话ID**: `{session_id}`"
        ]
    elif payload.EventType == BililiveEventType.FILE_OPENING:
        relative_path = event_data.get("RelativePath", "N/A")
        file_open_time = event_data.get("FileOpenTime", "N/A")
        session_id = event_data.get("SessionId", "N/A")
        serverchan_title = f"{EMOJI_FILE_OPEN} {name} 录制文件已打开"
        short_description = f"录制文件 '{relative_path}' 已开始写入。"
        event_display_name = "文件打开"
        tags += "|文件打开"
        specific_details = [
            f"{EMOJI_BULLET} **相对路径**: `{relative_path}`",
            f"{EMOJI_BULLET} **文件打开时间**: `{file_open_time}`",
            f"{EMOJI_BULLET} **会话ID**: `{session_id}`"
        ]
    elif payload.EventType == BililiveEventType.FILE_CLOSED:
        relative_path = event_data.get("RelativePath", "N/A")
        file_size = event_data.get("FileSize")
        duration = event_data.get("Duration")
        file_open_time = event_data.get("FileOpenTime", "N/A")
        file_close_time = event_data.get("FileCloseTime", "N/A")
        session_id = event_data.get("SessionId", "N/A")
        serverchan_title = f"{EMOJI_FILE_CLOSE} {name} 录制文件已关闭"
        short_description = f"录制文件 '{relative_path}' 已保存，大小: {format_file_size(file_size)}。"
        event_display_name = "文件关闭"
        tags += "|文件关闭"
        specific_details = [
            f"{EMOJI_BULLET} **相对路径**: `{relative_path}`",
            f"{EMOJI_BULLET} **文件大小**: `{format_file_size(file_size)}`",
            f"{EMOJI_BULLET} **持续时间**: `{format_duration(duration)}`",
            f"{EMOJI_BULLET} **文件打开时间**: `{file_open_time}`",
            f"{EMOJI_BULLET} **文件关闭时间**: `{file_close_time}`",
            f"{EMOJI_BULLET} **会话ID**: `{session_id}`"
        ]
    elif payload.EventType == BililiveEventType.SESSION_ENDED:
        session_id = event_data.get("SessionId", "N/A")
        serverchan_title = f"{EMOJI_STOP} {name} 录制结束了！"
        short_description = f"主播 {name} (房间: {room_id}) 的直播录制已结束。"
        event_display_name = "录制结束"
        tags += "|录制结束"
        specific_details = [
            f"{EMOJI_BULLET} **会话ID**: `{session_id}`"
        ]
    elif payload.EventType == BililiveEventType.STREAM_STARTED:
        serverchan_title = f"{EMOJI_LIVE} {name} 开始直播了！"
        short_description = f"主播 {name} (房间: {room_id}) 正在直播: {title}。"
        event_display_name = "直播开始"
        tags += "|直播开始"
        specific_details = []
    elif payload.EventType == BililiveEventType.STREAM_ENDED:
        serverchan_title = f"{EMOJI_OFFLINE} {name} 直播结束了！"
        short_description = f"主播 {name} (房间: {room_id}) 的直播已结束。"
        event_display_name = "直播结束"
        tags += "|直播结束"
        specific_details = []
    else:
        serverchan_title = f"{EMOJI_NOTIFICATION} {name} - 未知录播姬事件"
        short_description = f"收到未知录播姬事件: {payload.EventType.value}"
        event_display_name = f"未知事件: {payload.EventType.value}"
        tags += "|未知事件"
        specific_details = []
        if event_data:
            specific_details.append("\n### 未知事件原始数据")
            for key, value in event_data.items():
                if isinstance(value, (dict, list)):
                    try:
                        formatted_value = json.dumps(value, indent=2, ensure_ascii=False)
                        specific_details.append(f"- **{key}**: ```json\n{formatted_value}\n```")
                    except TypeError:
                        specific_details.append(f"- **{key}**: `{repr(value)}` (无法格式化为JSON)")
                else:
                    specific_details.append(f"- **{key}**: `{value}`")
        else:
            specific_details.append("无具体事件数据。")

    # 构造 ServerChan 的消息内容 (desp)，使用 Markdown 格式
    desp_lines = [
        f"# {EMOJI_NOTIFICATION} 录播姬事件通知",
        f"## {event_display_name}",  # 主要事件标题
        f"---",  # 分隔线
        f"### {EMOJI_INFO} 基本信息",
        f"{EMOJI_BULLET} **事件类型**: `{payload.EventType.value}`",
        f"{EMOJI_BULLET} **事件ID**: `{payload.EventId}`",
        f"{EMOJI_BULLET} **事件时间**: `{payload.EventTimestamp if payload.EventTimestamp else 'N/A'}`",
        f"{EMOJI_BULLET} **主播**: **`{name}`**",
        f"{EMOJI_BULLET} **直播间**: `{room_id}` (短号: `{short_id}`)",
        f"{EMOJI_BULLET} **直播间标题**: `{title}`",
        f"{EMOJI_BULLET} **分区**: `{area_parent}` / `{area_child}`",
        f"{EMOJI_BULLET} **当前状态**:",
        f"  {format_bool_emoji(event_data.get('Recording'))} 录制中",
        f"  {format_bool_emoji(event_data.get('Streaming'))} 直播中",
        f"  {format_bool_emoji(event_data.get('DanmakuConnected'))} 弹幕连接",
    ]
    # 添加事件特有的详细信息
    if specific_details:
        desp_lines.append(f"\n### {EMOJI_INFO} 事件详情")
        desp_lines.extend(specific_details)
    desp = "\n\n".join(desp_lines)

    return {
        "serverchan_title": serverchan_title,
        "desp": desp,
        "short_description": short_description,
        "tags": tags
    }


def handle_webhook(payload: WebhookPayload, db: Session):
    logger.info(f"Handling webhook: EventType={payload.EventType.value}, EventId={payload.EventId}")

    try:
        # 使用 webhook_processor 处理 webhook 负载，生成 ServerChan 消息详情
        message_details = _generate_serverchan_message(payload)

        # 调用 ServerChan 服务发送消息
        serverchan_response = serverchan.send_serverchan_message(
            message_details["serverchan_title"],
            message_details["desp"],
            message_details["short_description"],
            message_details["tags"]
        )

        # 记录 webhook 事件到数据库
        persist_webhook_event(db, payload, serverchan_response, message_details)

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
            return {
                "message": "Webhook received, but ServerChan forwarding failed.",
                "serverchan_status": "failure",
                "serverchan_detail": serverchan_response
            }
    except Exception as e:
        logger.exception(f"An unexpected error occurred during webhook processing for EventId={payload.EventId}: {e}")
        raise


def persist_webhook_event(db: Session, payload: WebhookPayload, serverchan_response: dict, message_details: dict):
    try:
        event_data = payload.EventData or {}

        try:
            _event_id = uuid.UUID(payload.EventId)
        except (ValueError, TypeError):
            logger.warning(f"Invalid EventId format, cannot parse to UUID: {payload.EventId}")
            _event_id = uuid.uuid4()

        _session_id = None
        if event_data.get("SessionId"):
            try:
                _session_id = uuid.UUID(str(event_data.get("SessionId")))
            except (ValueError, TypeError):
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
            audio_extraction_status=("pending" if payload.EventType == BililiveEventType.FILE_CLOSED else None),
        )
        create_webhook_event(db, event_create)
        logger.info(f"Webhook event saved. EventId={_event_id}")

        # 如果是文件关闭事件，则尝试提取音频
        if payload.EventType == BililiveEventType.FILE_CLOSED and event_data.get("RelativePath"):
            video_path = os.path.join(VIDEO_DIRECTORY, event_data["RelativePath"])
            logger.info(f"FileClosed event: Starting audio extraction for {video_path}")
            extracted_audio_path = ffmpeg_service.extract_aac_audio(video_path)

            update_data = WebhookEventUpdate()
            if extracted_audio_path:
                logger.info(f"Audio extraction successful for {video_path}. Output: {extracted_audio_path}")
                update_data.audio_extraction_status = "success"
                update_data.extracted_audio_path = extracted_audio_path
            else:
                logger.error(f"Audio extraction failed for {video_path}")
                update_data.audio_extraction_status = "failure"
            
            update_webhook_event(db, _event_id, update_data)

    except Exception as e:
        logger.exception(f"Failed to persist webhook event EventId={payload.EventId}: {e}")