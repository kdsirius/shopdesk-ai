import asyncio
import json
from pathlib import Path, PureWindowsPath
from typing import Annotated
from uuid import UUID, uuid4

from fastapi.responses import FileResponse, StreamingResponse
from fastapi import APIRouter, BackgroundTasks, UploadFile, File, HTTPException
from pydantic import BaseModel, constr

from shopkeeper_brain.services.import_service import save_upload, run_import, get_import_status
from shopkeeper_brain.services.query_service import run_query
from shopkeeper_brain.utils.mongo_history_utils import get_recent_messages

router = APIRouter()
FRONT = Path(__file__).resolve().parents[1] / "front"
_pending_streams: dict[UUID, asyncio.Queue[tuple[str, dict]]] = {}


class QueryRequest(BaseModel):
    query: constr(strip_whitespace=True, min_length=1)
    session_id: UUID


@router.get("/import.html", response_class=FileResponse)
def import_page() -> FileResponse:
    return FileResponse(FRONT / "import.html", media_type="text/html")


@router.get("/chat.html", response_class=FileResponse)
def chat_page() -> FileResponse:
    return FileResponse(FRONT / "chat.html", media_type="text/html")


@router.post("/upload", status_code=202)
def upload(background_tasks: BackgroundTasks, file: Annotated[UploadFile, File()]) -> dict:
    name = file.filename or ""
    path = PureWindowsPath(name)
    if path.name != name or ":" in name or path.is_reserved() or path.suffix.lower() not in {".md", ".pdf"}:
        raise HTTPException(status_code=400, detail="请选择文件名有效的 PDF 或 Markdown。")
    task_id, saved_path = save_upload(name, file.file)
    background_tasks.add_task(run_import, task_id, saved_path)
    return {"task_id": task_id}


@router.get("/status/{task_id}")
def import_status(task_id: UUID) -> dict:
    status = get_import_status(task_id)
    if status is None:
        raise HTTPException(status_code=404, detail="没有找到该导入任务。")
    return status


@router.post("/query", status_code=202)
async def query(request: QueryRequest, background_tasks: BackgroundTasks) -> dict:
    run_id = uuid4()
    events: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()
    _pending_streams[run_id] = events
    loop = asyncio.get_running_loop()

    def publish(event: str, data: dict) -> None:
        loop.call_soon_threadsafe(events.put_nowait, (event, data))

    background_tasks.add_task(run_query, str(request.session_id), request.query, publish)
    return {"session_id": request.session_id, "run_id": run_id}


@router.get("/stream/{run_id}", response_class=StreamingResponse)
async def stream(run_id: UUID) -> StreamingResponse:
    events = _pending_streams.pop(run_id, None)
    if events is None:
        raise HTTPException(status_code=404, detail="该运行不存在或已订阅。")

    async def generate():
        while True:
            event, data = await events.get()
            yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
            if event in {"complete", "task_error"}:
                return

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.get("/history/{session_id}")
def history(session_id: UUID) -> dict:
    records = get_recent_messages(str(session_id), limit=5)
    return {"session_id": session_id, "items": [{**record, "_id": str(record["_id"])} for record in records]}


if __name__ == '__main__':
    print(FRONT)
