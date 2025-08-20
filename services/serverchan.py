# services/serverchan.py
import logging
from typing import Dict, Any

import requests
from serverchan_sdk import sc_send
from config import get_serverchan_send_key

logger = logging.getLogger(__name__)


def send_serverchan_message(
        title: str,
        desp: str,
        short_description: str,
        tags: str
) -> Dict[str, Any]:
    """
    发送消息到 ServerChan.
    返回 ServerChan 的原始响应。
    """
    send_key = get_serverchan_send_key()
    if not send_key:
        logger.error("ServerChan SEND_KEY is not configured, unable to send message.")
        return {"code": -1, "message": "ServerChan SEND_KEY not configured."}

    try:
        response = sc_send(
            send_key,
            title,
            desp,
            {"tags": tags, "short": short_description}
        )
        response.raise_for_status()  # 如果请求失败（非2xx响应），则引发HTTPError
        serverchan_response = response.json()
        logger.info(f"ServerChan SDK raw response: {serverchan_response}")
        return serverchan_response
    except requests.exceptions.RequestException as e:
        logger.exception(f"An error occurred while sending message to ServerChan: {e}")
        return {"code": -2, "message": f"ServerChan SDK call failed: {e}"}
    except ValueError as e:  # response.json() 可能会引发 ValueError
        logger.exception(f"Failed to decode ServerChan response: {e}")
        return {"code": -3, "message": f"Failed to decode ServerChan response: {e}"}
