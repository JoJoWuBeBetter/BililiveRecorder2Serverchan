# main.py
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from serverchan_sdk import sc_send
from enum import Enum  # 导入 Enum

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="录播姬 Webhook 转 ServerChan",
    description="接收录播姬 Webhook 请求，并将其内容格式化后转发至 ServerChan。",
    version="1.2.0"  # 版本号更新
)

SERVERCHAN_SEND_KEY = os.getenv("SERVERCHAN_SEND_KEY")

if not SERVERCHAN_SEND_KEY:
    logger.error("Environment variable 'SERVERCHAN_SEND_KEY' is not set. Please set it in .env or your environment.")


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
    # 将 EventType 的类型改为枚举
    EventType: BililiveEventType = Field(..., description="事件类型")
    EventTimestamp: Optional[str] = Field(None, description="事件时间戳，ISO 8601 格式字符串")
    EventId: str = Field(..., description="事件的唯一随机ID，可用于判断重复事件")
    EventData: Dict[str, Any] = Field(..., description="事件的详细数据，是一个任意键值对的字典")


# 辅助函数：格式化布尔值
def format_bool(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


# 辅助函数：格式化文件大小
def format_file_size(bytes_size: Any) -> str:
    try:
        size = float(bytes_size)
        if size < 1024:
            return f"{size:.2f} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.2f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.2f} GB"
    except (ValueError, TypeError):
        return str(bytes_size)


# 辅助函数：格式化持续时间
def format_duration(seconds: Any) -> str:
    try:
        duration = float(seconds)
        if duration < 60:
            return f"{duration:.2f} 秒"
        elif duration < 3600:
            minutes = int(duration // 60)
            seconds_rem = duration % 60
            return f"{minutes} 分 {seconds_rem:.2f} 秒"
        else:
            hours = int(duration // 3600)
            minutes_rem = int((duration % 3600) // 60)
            seconds_rem = duration % 60
            return f"{hours} 时 {minutes_rem} 分 {seconds_rem:.2f} 秒"
    except (ValueError, TypeError):
        return str(seconds)


@app.post("/webhook", status_code=status.HTTP_200_OK)
async def receive_webhook(payload: WebhookPayload):
    logger.info(f"Received webhook: EventType={payload.EventType.value}, EventId={payload.EventId}")

    if not SERVERCHAN_SEND_KEY:
        logger.error(f"Attempted to process webhook EventId={payload.EventId} without SERVERCHAN_SEND_KEY configured.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="ServerChan SENDKEY is not configured on the server."
        )

    # 提取公共字段
    event_data = payload.EventData
    room_id = event_data.get("RoomId", "N/A")
    short_id = event_data.get("ShortId", "N/A")
    name = event_data.get("Name", "未知主播")
    title = event_data.get("Title", "未知标题")
    area_parent = event_data.get("AreaNameParent", "N/A")
    area_child = event_data.get("AreaNameChild", "N/A")
    recording_status = format_bool(event_data.get("Recording"))
    streaming_status = format_bool(event_data.get("Streaming"))
    danmaku_connected = format_bool(event_data.get("DanmakuConnected"))

    # 初始 ServerChan 的消息标题和标签，后面根据具体事件类型修改
    serverchan_title_prefix = f"🔔 录播姬通知: {name}"
    event_display_name = ""  # 用于显示在通知标题中的事件名
    tags = f"录播姬|{name}"

    # 构造 ServerChan 的消息内容 (desp)，使用 Markdown 格式
    desp_lines = [
        f"--- **基本信息** ---",
        f"- **事件ID**: `{payload.EventId}`",
        f"- **事件时间**: `{payload.EventTimestamp if payload.EventTimestamp else 'N/A'}`",
        f"- **主播**: `{name}`",
        f"- **直播间**: `{room_id}` (短号: `{short_id}`)",
        f"- **标题**: `{title}`",
        f"- **分区**: `{area_parent}` / `{area_child}`",
        f"- **正在录制**: `{recording_status}`",
        f"- **直播中**: `{streaming_status}`",
        f"- **弹幕连接**: `{danmaku_connected}`",
    ]

    # 根据事件类型添加特定信息，现在直接比较枚举成员
    if payload.EventType == BililiveEventType.SESSION_STARTED:
        session_id = event_data.get("SessionId", "N/A")
        desp_lines.append(f"\n--- **录制开始** ---")
        desp_lines.append(f"- **会话ID**: `{session_id}`")
        event_display_name = "录制开始"
        tags += "|录制开始"
    elif payload.EventType == BililiveEventType.FILE_OPENING:
        relative_path = event_data.get("RelativePath", "N/A")
        file_open_time = event_data.get("FileOpenTime", "N/A")
        session_id = event_data.get("SessionId", "N/A")
        desp_lines.append(f"\n--- **文件打开** ---")
        desp_lines.append(f"- **相对路径**: `{relative_path}`")
        desp_lines.append(f"- **文件打开时间**: `{file_open_time}`")
        desp_lines.append(f"- **会话ID**: `{session_id}`")
        event_display_name = "文件打开"
        tags += "|文件打开"
    elif payload.EventType == BililiveEventType.FILE_CLOSED:
        relative_path = event_data.get("RelativePath", "N/A")
        file_size = event_data.get("FileSize")
        duration = event_data.get("Duration")
        file_open_time = event_data.get("FileOpenTime", "N/A")
        file_close_time = event_data.get("FileCloseTime", "N/A")
        session_id = event_data.get("SessionId", "N/A")
        desp_lines.append(f"\n--- **文件关闭** ---")
        desp_lines.append(f"- **相对路径**: `{relative_path}`")
        desp_lines.append(f"- **文件大小**: `{format_file_size(file_size)}`")
        desp_lines.append(f"- **持续时间**: `{format_duration(duration)}`")
        desp_lines.append(f"- **文件打开时间**: `{file_open_time}`")
        desp_lines.append(f"- **文件关闭时间**: `{file_close_time}`")
        desp_lines.append(f"- **会话ID**: `{session_id}`")
        event_display_name = "文件关闭"
        tags += "|文件关闭"
    elif payload.EventType == BililiveEventType.SESSION_ENDED:
        session_id = event_data.get("SessionId", "N/A")
        desp_lines.append(f"\n--- **录制结束** ---")
        desp_lines.append(f"- **会话ID**: `{session_id}`")
        event_display_name = "录制结束"
        tags += "|录制结束"
    elif payload.EventType == BililiveEventType.STREAM_STARTED:
        desp_lines.append(f"\n--- **直播开始** ---")
        event_display_name = "直播开始"
        tags += "|直播开始"
    elif payload.EventType == BililiveEventType.STREAM_ENDED:
        desp_lines.append(f"\n--- **直播结束** ---")
        event_display_name = "直播结束"
        tags += "|直播结束"
    else:  # 理论上，如果 Pydantic 模型严格验证，这里不会被触发，除非有新的枚举成员未在此处处理
        desp_lines.append(f"\n--- **未知事件数据 (EventType: {payload.EventType.value})** ---")
        if event_data:
            for key, value in event_data.items():
                if isinstance(value, (dict, list)):
                    try:
                        formatted_value = json.dumps(value, indent=2, ensure_ascii=False)
                        desp_lines.append(f"- **{key}**: ```json\n{formatted_value}\n```")
                    except TypeError:
                        desp_lines.append(f"- **{key}**: `{repr(value)}` (无法格式化为JSON)")
                else:
                    desp_lines.append(f"- **{key}**: `{value}`")
        else:
            desp_lines.append("无具体事件数据。")
        event_display_name = f"未知事件 {payload.EventType.value}"
        tags += "|未知事件"

    serverchan_title = f"{serverchan_title_prefix} - {event_display_name}"
    desp = "\n\n".join(desp_lines)  # 使用双换行在 Markdown 中创建段落

    try:
        serverchan_response = sc_send(SERVERCHAN_SEND_KEY, serverchan_title, desp, {"tags": tags})
        logger.info(f"ServerChan SDK response: {serverchan_response}")

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
            return {
                "message": "Webhook received, but ServerChan forwarding failed.",
                "serverchan_status": "failure",
                "serverchan_detail": serverchan_response
            }

    except Exception as e:
        logger.exception(f"An unexpected error occurred during ServerChan SDK call for EventId={payload.EventId}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process webhook due to an internal server error: {e}"
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8888)
