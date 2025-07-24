from typing import Optional
from pydantic import BaseModel, Field


class CosUploadRequest(BaseModel):
    """
    上传文件到COS的请求体模型
    """
    local_file_path: str = Field(
        ...,
        description="文件在服务器上的绝对路径。",
        examples=["/path/to/my/video.mp4"]
    )
    cos_key: Optional[str] = Field(
        default=None,
        description="上传到COS后的对象键名（路径/文件名）。如果省略，将使用本地文件名。",
        examples=["videos/archive/video.mp4"]
    )


class CosUploadResponse(BaseModel):
    """
    上传成功的响应模型
    """
    message: str
    status: str = "success"
    bucket: str
    key: str


class CosUrlResponse(BaseModel):
    """
    获取预签名URL的响应模型
    """
    key: str
    url: str
    expires_in_seconds: int
