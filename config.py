import os
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 获取 ServerChan 的 SendKey
SERVERCHAN_SEND_KEY = os.getenv("SERVERCHAN_SEND_KEY")

# 腾讯云配置
TENCENTCLOUD_SECRET_ID = os.getenv("TENCENTCLOUD_SECRET_ID")
TENCENTCLOUD_SECRET_KEY = os.getenv("TENCENTCLOUD_SECRET_KEY")

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
