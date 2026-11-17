import json
import logging
import re
from pathlib import Path
from typing import Any

from langchain_text_splitters import RecursiveCharacterTextSplitter

from shopkeeper_brain.processor.import_processor.BaseNode import BaseNode
from shopkeeper_brain.processor.import_processor.exceptions import StateFieldError
from shopkeeper_brain.processor.import_processor.state import ImportGraphState, create_default_state

Chunk = dict[str, Any]

DEFAULT_MAX_CONTENT_LENGTH = 2000
MIN_CONTENT_LENGTH = 500

TITLE_PATTERN = re.compile(r"^\s*#{1,6}\s+.+")
FENCE_PATTERN = re.compile(r"^\s*(`{3,}|~{3,})(?:.*)?$")


class NodeDocumentSplit(BaseNode):
    """文档切片节点：把 Markdown 整理成可检索的 Chunk 列表。"""

    name = "node_document_split"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """按固定步骤完成 Markdown 切片、统计、备份和状态回写。"""
        content, file_title = self._step_1_get_inputs(state)
        sections, title_count, lines_count = self._step_2_split_by_titles(content, file_title)
        sections = self._step_3_handle_no_title(content, sections, title_count, file_title)
        sections = self._step_4_refine_chunks(sections)
        self._step_5_print_stats(lines_count, sections)
        self._step_6_backup(state, sections)

        state["chunks"] = sections
        return state

    def _step_1_get_inputs(self, state: ImportGraphState) -> tuple[str, str]:
        """读取切片需要的字段，并统一正文换行符。"""
        file_title = state.get('file_title', '')
        if not isinstance(file_title, str) or not file_title.strip():
            raise StateFieldError(node_name=self.name, field_name="file_title", expected_type=str)

        md_content = state.get('md_content', "")
        if not isinstance(md_content, str) or not md_content:
            raise StateFieldError(node_name=self.name, field_name="md_content", expected_type=str)

        md_path = state.get('md_path', '')
        if not isinstance(md_path, str) or not md_path.strip():
            raise StateFieldError(node_name=self.name, field_name="md_path", expected_type=str)

        normalized_content = md_content.replace("\r\n", "\n").replace("\r", "\n")
        self.logger.info("输入加载完成，文件标题：%s", file_title)

        return normalized_content, file_title

    def _step_2_split_by_titles(self, content: str, file_title) -> tuple[list[Chunk], int, int]:
        """按 Markdown 标题初切，并跳过代码围栏中的伪标题。"""
        # 把整篇文档按换行拆成一行一行
        lines = content.split('\n')
        # 最终结果：装所有章节的列表
        sections: list[Chunk] = []
        # 统计标题数量
        title_count = 0
        # 当前正在收集的章节标题
        current_title = ""
        # 当前章节的内容行（缓存区）
        current_lines: list[str] = []
        # 标记：是否在代码块里
        in_code_block = False
        # 代码块的围栏字符（` 或 ~）
        fence_char: str | None = None

        def flush_section() -> None:
            """把当前缓存章节写入列表，空缓存不产生空 Chunk。"""
            if not current_lines:
                return
            # 把当前章节塞进结果列表
            sections.append({
                "title": current_title,
                "content": "\n".join(current_lines),  # 把缓存的行重新拼成字符串
                "file_title": file_title,
                # 没有标题时保留空归属；不能因此丢掉标题前正文。
                "parent_title": current_title
            })

        for line in lines:
            fence_match = FENCE_PATTERN.match(line)
            if fence_match:
                marker = fence_match.group(1)
                if not in_code_block:
                    in_code_block = True
                    fence_char = marker[0]
                elif fence_char == marker[0]:
                    in_code_block = False
                    fence_char = None
                current_lines.append(line)
                continue

            if not in_code_block and TITLE_PATTERN.match(line):
                flush_section()
                current_title = line.strip()
                current_lines = [current_title]
                title_count += 1
                self.logger.info("识别标题：%s", current_title)
                continue
            current_lines.append(line)

        flush_section()
        self.logger.info("文档粗切完成，章节数：%s，标题数：%s，文本行数：%s", len(sections), title_count, len(lines))

        return sections, title_count, len(lines)

    def _step_3_handle_no_title(self, content: str, sections: list[Chunk],
                                title_count: int, file_title: str) -> list[Chunk]:
        """没有 Markdown 标题时，把全文包装为一个统一章节。"""
        if title_count == 0:
            self.logger.warning("未识别到 Markdown 标题，按无标题章节处理：%s", file_title)
            return [{
                "title": "无标题",
                "content": content,
                "file_title": file_title,
                "parent_title": "无标题"
            }]
        return sections

    def _step_4_refine_chunks(self, sections: list[Chunk]) -> list[Chunk]:
        """先切超长章节，再合并同归属短块，并补齐归属字段。"""
        refine_sections: list[Chunk] = []

        for section in sections:
            refine_sections.extend(self._split_long_section(section))

        final_sections = self._merge_short_sections(refine_sections)
        for section in final_sections:
            if not section.get('parent_title'):
                section["parent_title"] = section.get('title', "")
        return final_sections

    def _split_long_section(self, section: Chunk) -> list[Chunk]:
        """按段落、换行、标点和空格递归切分超长章节。"""
        content = str(section.get("content",""))
        if len(content) <= DEFAULT_MAX_CONTENT_LENGTH:
            return [section]

        title = str(section.get('title', ''))
        prefix = f"{title}\n\n" if title else ""
        available_length = DEFAULT_MAX_CONTENT_LENGTH - len(prefix)
        if available_length <= 0:
            self.logger.warning("章节标题过长，无法继续切分：%s", title[:20])
            return [section]
        body = content.lstrip()
        if title and body.startswith(title):
            body = body[len(title):].lstrip()

        splitter = RecursiveCharacterTextSplitter(chunk_size=available_length, chunk_overlap=0, separators=[
            "\n\n", "\n", "。", "！",
            "？", "；", ".", "!",
            "?", ";", " ", ""])

        sub_sections: list[Chunk] = []
        for part, chunk in enumerate(splitter.split_text(body), start=1):
            text = chunk.strip()
            if not text:
                continue

            sub_sections.append({
                "title": f"{title}-{part}",
                "content": f"{prefix}{text}".strip(),
                "file_title": section.get("file_title", ""),
                "parent_title": title or section.get("parent_title", ""),
                "part": part
            })
        return sub_sections

    def _merge_short_sections(self, sections: list[Chunk]) -> list[Chunk]:
        """只合并同归属且合并后不超过上限的相邻短块。"""
        if not sections:
            return []

        merged_sections: list[Chunk] = []
        current_chunk: Chunk | None = None

        for section in sections:
            if current_chunk is None:
                current_chunk = section
                continue

            current_content = str(current_chunk.get("content", ""))
            next_content = str(section.get("content", ""))
            current_parent = current_chunk.get("parent_title", "")
            next_parent = section.get("parent_title", "")
            same_parent = current_parent == next_parent
            combined_length = len(current_content) + 2 + len(next_content)

            if (len(current_content) < MIN_CONTENT_LENGTH
                    and same_parent
                    and combined_length <= DEFAULT_MAX_CONTENT_LENGTH):
                parent_title = str(section.get("parent_title", ""))
                if parent_title and next_content.startswith(parent_title):
                    next_content = next_content[len(parent_title):].lstrip()
                current_chunk['content'] = f"{current_content}\n\n{next_content}"
                if "part" in section:
                    current_chunk['part'] = section['part']
                continue

            merged_sections.append(current_chunk)
            current_chunk = section

        if current_chunk is not None:
            merged_sections.append(current_chunk)

        return merged_sections

    def _step_5_print_stats(self, lines_count: int, sections: list[Chunk]) -> None:
        """输出原始行数和最终 Chunk 数，方便观察切片效果。"""
        self.logger.info("文档切片统计：原始行数=%s，最终Chunk数=%s", lines_count, len(sections))

    def _step_6_backup(self, state: ImportGraphState, sections: list[Chunk]) -> None:
        """把最终 Chunk 列表备份到 Markdown 同目录的 JSON 文件。"""
        try:
            backup_path = Path(state["md_path"]).parent / "chunks.json"
            with backup_path.open("w", encoding="utf-8") as target:
                json.dump(sections, target, ensure_ascii=False, indent=2)
                self.logger.info("Chunk 备份完成：%s", backup_path)
        except Exception as exc:
            # 备份失败不抹掉已经算出的切片，方便上层继续决定如何处理。
            self.logger.error("Chunk 备份失败：%s", exc)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    md_path = Path(
        r"E:\dev\python\project-study\shopkeeper-brain\workspace\day03-real-run\万用表RS-12的使用_5gatm6ph\extracted\万用表RS-12的使用_new.md"
    )
    if not md_path.is_file():
        raise SystemExit(f"请先准备真实 Markdown：{md_path}")

    state = create_default_state(
        md_path=str(md_path),
        md_content=md_path.read_text(encoding="utf-8"),
        file_title=md_path.stem.removesuffix("_new")
    )

    node = NodeDocumentSplit()
    result = node(state)
    backup_path = md_path.parent / "chunks.json"
    backup_chunks = json.loads(backup_path.read_text(encoding='utf-8'))

    assert result is state
    assert result["chunks"]
    assert result["chunks"] == backup_chunks
    require_fields = {"title", "content", "file_title", "parent_title"}
    assert all(require_fields <= chunk.keys() for chunk in result["chunks"])


    print("Markdown：", md_path)
    print("Chunk 数量：", len(result["chunks"]))
    print("chunks.json：", backup_path)
    print("状态与 JSON 备份一致：通过")
    print("文档切片：通过")

    # 课堂笔记是仓库中的真实 Markdown，包含 ```python 代码围栏。
    # 这里只调用标题粗切，不会向 reference/ 写入任何文件。
    reference_note = Path(
        r"E:\dev\python\project-study\shopkeeper-brain\reference\掌教智库\4.视频\day05\课堂笔记\07【掌柜智库】【导入】文档切片.md"
    )
    if reference_note.is_file():
        note_content = reference_note.read_text(encoding="utf-8")
        note_sections, _, _ = node._step_2_split_by_titles(
            note_content,
            "day05课堂笔记",
        )
        assert not any(
            str(section["title"]).startswith("# 作用：")
            for section in note_sections
        )
        print("带语言标记的代码围栏保护：通过")
