import os
import logging
from typing import Tuple, Optional

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 获取 ServerChan 的 SendKey
SERVERCHAN_SEND_KEY = os.getenv("SERVERCHAN_SEND_KEY")

# 腾讯云配置
TENCENTCLOUD_SECRET_ID = os.getenv("TENCENTCLOUD_SECRET_ID")
TENCENTCLOUD_SECRET_KEY = os.getenv("TENCENTCLOUD_SECRET_KEY")
TENCENTCLOUD_COS_BUCKET = os.getenv("TENCENTCLOUD_COS_BUCKET")
TENCENTCLOUD_COS_REGION = os.getenv("TENCENTCLOUD_COS_REGION")

# 视频文件存储目录
# 在容器内，这通常是数据卷映射的目标路径
VIDEO_DIRECTORY = os.getenv("VIDEO_DIRECTORY", "videos")

# FFMPEG 可执行文件路径
# 在 Docker 中，ffmpeg 通常在系统 PATH 中，所以默认为 'ffmpeg'
# 在 Windows 本地开发时，可以设置环境变量 FFMPEG_PATH 指向具体的 .exe 文件
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")

# Tushare Token
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
TUSHARE_MIN_INTERVAL_SECONDS = os.getenv("TUSHARE_MIN_INTERVAL_SECONDS", "0")

# 检查 SendKey 是否已配置
if not SERVERCHAN_SEND_KEY:
    logger.error("Environment variable 'SERVERCHAN_SEND_KEY' is not set. Please set it in .env or your environment.")

if not TENCENTCLOUD_SECRET_ID or not TENCENTCLOUD_SECRET_KEY:
    logger.warning(
        "Environment variables 'TENCENTCLOUD_SECRET_ID' and 'TENCENTCLOUD_SECRET_KEY' "
        "are not fully set. Tencent Cloud ASR functionality might be limited.")


def get_serverchan_send_key() -> str:
    """提供一个函数来获取 SERVERCHAN_SEND_KEY"""
    return SERVERCHAN_SEND_KEY


def get_tencentcloud_credentials() -> tuple[str, str]:
    """提供一个函数来获取腾讯云 SecretId 和 SecretKey"""
    return TENCENTCLOUD_SECRET_ID, TENCENTCLOUD_SECRET_KEY


def get_tencentcloud_cos_credentials() -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """提供一个函数来获取腾讯云 COS 存储桶相关参数"""
    return TENCENTCLOUD_SECRET_ID, TENCENTCLOUD_SECRET_KEY, TENCENTCLOUD_COS_BUCKET, TENCENTCLOUD_COS_REGION


def get_tencentcloud_cos_region() -> str:
    """提供一个函数来获取腾讯云 COS 地域"""
    return TENCENTCLOUD_COS_REGION


def get_tushare_token() -> Optional[str]:
    """提供一个函数来获取 TUSHARE_TOKEN"""
    return TUSHARE_TOKEN


def get_tushare_min_interval_seconds() -> float:
    """提供一个函数来获取 Tushare 调用最小间隔秒数。"""
    try:
        return max(0.0, float(TUSHARE_MIN_INTERVAL_SECONDS))
    except (TypeError, ValueError):
        logger.warning(
            "Environment variable 'TUSHARE_MIN_INTERVAL_SECONDS' is invalid: %s. Falling back to 0.",
            TUSHARE_MIN_INTERVAL_SECONDS,
        )
        return 0.0
