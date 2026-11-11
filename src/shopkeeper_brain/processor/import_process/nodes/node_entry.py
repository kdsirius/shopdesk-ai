from pathlib import Path

from shopkeeper_brain.processor.import_process.BaseNode import BaseNode
from shopkeeper_brain.processor.import_process.exceptions import StateFieldError, ValidationError
from shopkeeper_brain.processor.import_process.state import ImportGraphState


class NodeEntry(BaseNode):
    """入口节点：确认文件类型并准备路由状态。"""
    name = "node_entry"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        import_file_path = state.get("import_file_path")
        if not isinstance(import_file_path, str):
            raise StateFieldError(
                node_name=self.name,
                field_name="import_file_path",
                expected_type=str,
            )

        path = Path(import_file_path)
        if not path.exists() or not path.is_file():
            raise StateFieldError(
                node_name=self.name,
                field_name="import_file_path",
                expected_type=str,
                message=f"文件不存在或不是普通文件: {import_file_path}",
            )

        suffix = path.suffix.lower()
        if suffix not in {'.pdf', '.md'}:
            raise ValidationError(
                message=f"该文件的后缀格式 {path.suffix} 不支持",
                node_name=self.name,
            )

        # 先清理派生字段，保证同一个状态对象被重复使用时不会残留旧分支。
        state["is_pdf_read_enabled"] = suffix == ".pdf"
        state["is_md_read_enabled"] = suffix == ".md"
        state["pdf_path"] = import_file_path if suffix == ".pdf" else ""
        state["md_path"] = import_file_path if suffix == ".md" else ""
        state["file_title"] = path.stem

        return state
