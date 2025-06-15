import json
import logging
import os
from enum import Enum
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from serverchan_sdk import sc_send

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(pastime)s - %(levelness)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title="录播姬 Webhook 转 ServerChan",
    description="接收录播姬 Webhook 请求，并将其内容格式化后转发至 ServerChan。",
    version="1.2.1"  # 版本号更新
)

# 获取 ServerChan 的 SendKey
SERVERCHAN_SEND_KEY = os.getenv("SERVERCHAN_SEND_KEY")

# 检查 SendKey 是否已配置
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
    EventType: BililiveEventType = Field(..., description="事件类型")
    EventTimestamp: Optional[str] = Field(None, description="事件时间戳，ISO 8601 格式字符串")
    EventId: str = Field(..., description="事件的唯一随机ID，可用于判断重复事件")
    EventData: Dict[str, Any] = Field(..., description="事件的详细数据，是一个任意键值对的字典")


# --- Emoji 和常量定义 ---
EMOJI_NOTIFICATION = "📢"
EMOJI_START = "▶️"
EMOJI_STOP = "⏹️"
EMOJI_RECORD = "⏺️"
EMOJI_FILE_OPEN = "📂"
EMOJI_FILE_CLOSE = "💾"
EMOJI_LIVE = "🔴"
EMOJI_OFFLINE = "⚫"
EMOJI_CHECK = "✅"
EMOJI_CROSS = "❌"
EMOJI_INFO = "ℹ️"
EMOJI_BULLET = "•"  # 用于 Markdown 列表


# 辅助函数：格式化布尔值（使用 Emoji）
def format_bool_emoji(value: Any) -> str:
    if isinstance(value, bool):
        return EMOJI_CHECK if value else EMOJI_CROSS
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
            detail="ServerChan SEND_KEY is not configured on the server."
        )

    # 提取公共字段
    event_data = payload.EventData
    room_id = event_data.get("RoomId", "N/A")
    short_id = event_data.get("ShortId", "N/A")
    name = event_data.get("Name", "未知主播")
    title = event_data.get("Title", "未知标题")
    area_parent = event_data.get("AreaNameParent", "N/A")
    area_child = event_data.get("AreaNameChild", "N/A")

    # 初始 ServerChan 的消息标题、简短描述和标签
    tags = f"录播姬|{name}"

    # 根据事件类型设置标题、简短描述和详细信息
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
    else:  # 理论上，如果 Pydantic 模型严格验证，这里不会被触发，除非有新的枚举成员未在此处处理
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

    desp = "\n\n".join(desp_lines)  # 使用双换行在 Markdown 中创建段落

    try:
        # 调用 ServerChan SDK 发送消息，传入 short 参数
        serverchan_response = sc_send(
            SERVERCHAN_SEND_KEY,
            serverchan_title,
            desp,
            {"tags": tags, "short": short_description}
        )
        logger.info(f"ServerChan SDK response: {serverchan_response}")

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
