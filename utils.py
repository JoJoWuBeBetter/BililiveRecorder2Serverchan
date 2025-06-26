import json
from typing import Any
from constants import EMOJI_CHECK, EMOJI_CROSS


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
