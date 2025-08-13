# services/ffmpeg_service.py
import logging
import os
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


def extract_aac_audio(input_video_path: str) -> Optional[str]:
    """
    使用 ffmpeg 从视频文件中提取 AAC 音频流，并保存为 .aac 文件。

    :param input_video_path: 输入视频文件的完整路径。
    :return: 如果成功，返回提取出的 AAC 文件的路径；如果失败，则返回 None。
    """
    if not os.path.exists(input_video_path):
        logger.error("Input video file not found: {input_video_path}")
        return None

    # 构建输出文件名，将 .flv/.mp4 等后缀替换为 .aac
    output_audio_path = os.path.splitext(input_video_path)[0] + '.aac'

    # 构建 ffmpeg 命令
    # -i: 指定输入文件
    # -vn: 禁用视频录制，只处理音频
    # -acodec copy: 直接复制音频流，不进行重新编码，速度最快且无损
    command = [
        'D:\\Tools\\ffmpeg-master-latest-win64-gpl\\bin\\ffmpeg',
        '-i', input_video_path,
        '-vn',
        '-acodec', 'copy',
        output_audio_path
    ]

    try:
        logger.info("Executing ffmpeg command: {' '.join(command)}")
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        logger.info("Successfully extracted audio to {output_audio_path}")
        if result.stderr:
            # ffmpeg 经常将正常信息输出到 stderr，所以这里用 info 级别记录
            logger.info("ffmpeg output:{result.stderr}")
        return output_audio_path
    except FileNotFoundError:
        logger.error("ffmpeg command not found. Is ffmpeg installed and in the system's PATH?")
        return None
    except subprocess.CalledProcessError as e:
        logger.error("ffmpeg command failed with exit code {e.returncode} for file {input_video_path}")
        logger.error("ffmpeg stderr:{e.stderr}")
        # 如果失败，清理可能已创建的空文件
        if os.path.exists(output_audio_path):
            os.remove(output_audio_path)
        return None
    except Exception as e:
        logger.exception("An unexpected error occurred while extracting audio from {input_video_path}: {e}")
        return None
