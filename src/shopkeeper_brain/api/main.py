from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI(title="掌柜智库")
# 从入口文件定位页面，IDE 的工作目录变化时路径仍然有效。
INDEX_PATH = Path(__file__).resolve().parents[1] / "front" / "index.html"


@app.get("/", response_class=FileResponse)
def index() -> FileResponse:
    return FileResponse(INDEX_PATH, media_type="text/html")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


if __name__ == '__main__':
    uvicorn.run(app, host="127.0.0.1", port=8000)
