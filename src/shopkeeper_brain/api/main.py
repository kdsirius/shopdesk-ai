import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, constr
from shopkeeper_brain.api.business import router

app = FastAPI(title="掌柜智库")
app.include_router(router)
# 从入口文件定位页面，IDE 的工作目录变化时路径仍然有效。
INDEX_PATH = Path(__file__).resolve().parents[1] / "front" / "index.html"


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(INDEX_PATH, media_type="text/html")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


class PreviewRequest(BaseModel):
    question: constr(strip_whitespace=True, min_length=1)


@app.post("/demo/preview")
def preview(request: PreviewRequest) -> PreviewRequest:
    return request


@app.get("/demo/sse", response_class=FileResponse)
def sse_page() -> FileResponse:
    return FileResponse(INDEX_PATH.with_name("sse_demo.html"), media_type="text/html")


@app.get("/demo/stream/{run_id}", response_class=StreamingResponse)
async def stream_demo(run_id: int, steps: Annotated[int, Query(ge=1, le=5)] = 3, ) -> StreamingResponse:
    async def event_generator() -> AsyncIterator[str]:
        for step in range(1, steps + 1):
            await asyncio.sleep(1)
            data = json.dumps({"run_id": run_id, "step": step, "total": steps})
            yield f"event: progress\ndata: {data}\n\n"
        yield "event: complete\ndata: 演示完成\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8000)
