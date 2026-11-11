from copy import deepcopy
from typing import TypedDict, Unpack


class ImportGraphState(TypedDict):
    """导入流程中所有节点共享的状态。"""

    import_file_path: str
    is_pdf_read_enabled: bool
    is_md_read_enabled: bool
    pdf_path: str
    md_path: str
    file_title: str
    visited_nodes: list[str]
    status: str


GRAPH_DEFAULT_STATE: ImportGraphState = {
    "import_file_path": "",
    "is_pdf_read_enabled": False,
    "is_md_read_enabled": False,
    "pdf_path": "",
    "md_path": "",
    "file_title": "",
    "visited_nodes": [],
    "status": "created",
}


def create_default_state(**overrides: Unpack[ImportGraphState]) -> ImportGraphState:
    """创建彼此隔离的状态副本，并允许调用方覆盖字段。"""
    state = deepcopy(GRAPH_DEFAULT_STATE)
    state.update(overrides)
    return state
