import logging
from pathlib import Path
from shutil import copyfileobj
from threading import Lock
from typing import BinaryIO
from uuid import UUID, uuid4

from app.processor.import_processor.main_graph import KBImportWorkflow
from app.processor.import_processor.state import create_default_state

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "workspace" / "day15-uploads"
_tasks: dict[UUID, dict] = {}
_import_lock = Lock()


def save_upload(filename: str, source: BinaryIO) -> tuple[UUID, Path]:
    task_id = uuid4()
    folder = UPLOAD_DIR / str(task_id)
    folder.mkdir(parents=True)
    path = folder / filename
    with path.open("wb") as target:
        copyfileobj(source, target)
    _tasks[task_id] = {"status": "pending", "done_list": []}
    return task_id, path


def get_import_status(task_id: UUID) -> dict | None:
    return _tasks.get(task_id)


def run_import(task_id: UUID, path: Path) -> dict | None:
    with _import_lock:
        done: list[str] = []
        _tasks[task_id] = {"status": "processing", "done_list": done}
        try:
            state = create_default_state(import_file_path=str(path), file_dir=str(path.parent), )
            for update in KBImportWorkflow().stream(initial_state=state):
                done = [*done, *update["data"]]
                _tasks[task_id] = {"status": "processing", "done_list": done}
            _tasks[task_id] = {"status": "completed", "done_list": done}
        except Exception:
            logger.exception("导入失败，task_id=%s", task_id)
            _tasks[task_id] = {"status": "failed", "done_list": done}


if __name__ == '__main__':
    print(uuid4())
