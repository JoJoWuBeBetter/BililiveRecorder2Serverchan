from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from typing import List, Optional
import os
from datetime import datetime
from config import VIDEO_DIRECTORY

router = APIRouter()

templates = Jinja2Templates(directory="templates")


class FileInfo(BaseModel):
    name: str
    path: str
    is_directory: bool
    last_modified: datetime
    size: int


@router.get("/files/", response_model=List[FileInfo])
async def list_files(path: Optional[str] = None):
    """
    List files and directories.
    """
    if path is None:
        base_path = VIDEO_DIRECTORY
    else:
        base_path = os.path.join(VIDEO_DIRECTORY, path)

    if not os.path.exists(base_path) or not os.path.isdir(base_path):
        raise HTTPException(status_code=404, detail="Directory not found")

    files_info = []
    for entry in os.scandir(base_path):
        full_path = os.path.join(base_path, entry.name)
        stat = entry.stat()
        files_info.append(FileInfo(
            name=entry.name,
            path=os.path.relpath(full_path, VIDEO_DIRECTORY),
            is_directory=entry.is_dir(),
            last_modified=datetime.fromtimestamp(stat.st_mtime),
            size=stat.st_size
        ))
    return files_info


@router.get("/browser/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/browser/tasks", response_class=HTMLResponse)
async def tasks_console(request: Request):
    """任务控制台页面。"""

    return templates.TemplateResponse("tasks.html", {"request": request})
