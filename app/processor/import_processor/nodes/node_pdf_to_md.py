import logging
import tempfile
import time
import zipfile
from pathlib import Path

import requests

from app.core.mineru_config import load_mineru_config
from app.processor.import_processor.BaseNode import BaseNode
from app.processor.import_processor.exceptions import (
    ConfigurationError,
    FileProcessingError,
    PdfConversionError,
    StateFieldError,
)
from app.processor.import_processor.state import (
    ImportGraphState,
    create_default_state,
)


class NodePDFToMD(BaseNode):
    """调用 MinerU，把一个真实 PDF 转为本地 Markdown 和图片资源。"""

    name = "node_pdf_to_md"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """完成路径校验、远程解析、结果落盘，并回写 Markdown 状态。"""
        pdf_path, output_dir = self._step_1_validate_paths(state)
        try:
            zip_url = self._step_2_upload_and_poll(pdf_path)
            md_path = self._step_3_download_and_extract(
                zip_url,
                output_dir,
                pdf_path.stem,
            )
        except requests.RequestException as exc:
            # 网络异常可能包含临时签名 URL，对外只保留异常类型。
            raise PdfConversionError(
                message=f"MinerU 网络请求失败：{type(exc).__name__}",
                node_name=self.name,
            ) from exc

        md_content = md_path.read_text(encoding="utf-8")
        # 只有本地文件已经真实落盘并读成功，才更新状态。
        state["md_path"] = str(md_path)
        state["md_content"] = md_content
        return state

    def _step_1_validate_paths(
            self,
            state: ImportGraphState,
    ) -> tuple[Path, Path]:
        """校验 PDF 输入并准备输出目录。"""
        for field_name in ("pdf_path", "file_dir"):
            value = state.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise StateFieldError(
                    node_name=self.name,
                    field_name=field_name,
                    expected_type=str,
                )

        pdf_path = Path(state["pdf_path"]).resolve()
        output_dir = Path(state["file_dir"]).resolve()
        if not pdf_path.is_file():
            raise FileProcessingError(
                message=f"PDF 文件不存在或不是普通文件：{pdf_path}",
                node_name=self.name,
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        return pdf_path, output_dir

    def _step_2_upload_and_poll(self, pdf_path: Path) -> str:
        """申请上传地址、上传 PDF，并轮询到 MinerU 返回 ZIP 地址。"""
        config = load_mineru_config()
        for field_name, value in (
            ("MINERU_BASE_URL", config.base_url),
            ("MINERU_API_TOKEN", config.api_token),
        ):
            if not value:
                raise ConfigurationError(
                    message=f"MinerU 配置缺失：{field_name}",
                    node_name=self.name,
                )

        headers = {"Authorization": f"Bearer {config.api_token}"}
        response = requests.post(
            url=f"{config.base_url}/file-urls/batch",
            headers=headers,
            json={
                "files": [{"name": pdf_path.name}],
                "model_version": "vlm",
            },
            timeout=(10, 30),
        )
        response.raise_for_status()
        result = response.json()
        if result.get("code") != 0:
            raise PdfConversionError(
                message=f"申请上传链接失败，业务码：{result.get('code')}",
                node_name=self.name,
            )

        batch_id = result["data"]["batch_id"]
        signed_url = result["data"]["file_urls"][0]

        # 签名 URL 自己带上传授权，不把 MinerU Bearer Token 转发过去。
        with pdf_path.open("rb") as source:
            upload = requests.put(
                signed_url,
                data=source,
                timeout=(10, 120),
            )
        upload.raise_for_status()
        self.logger.info("PDF 上传完成，batch_id=%s", batch_id)

        deadline = time.monotonic() + 600
        poll_url = f"{config.base_url}/extract-results/batch/{batch_id}"
        while time.monotonic() < deadline:
            try:
                response = requests.get(
                    poll_url,
                    headers=headers,
                    timeout=(10, 10),
                )
            except (requests.Timeout, requests.ConnectionError):
                self.logger.warning(
                    "轮询网络暂时不可用，3 秒后重试，batch_id=%s",
                    batch_id,
                )
                time.sleep(3)
                continue

            response.raise_for_status()
            result = response.json()
            if result.get("code") != 0:
                raise PdfConversionError(
                    message=f"查询解析结果失败，业务码：{result.get('code')}",
                    node_name=self.name,
                )

            item = result["data"]["extract_result"][0]
            task_state = item["state"]
            if task_state == "done":
                self.logger.info("MinerU 解析完成，batch_id=%s", batch_id)
                return item["full_zip_url"]
            if task_state == "failed":
                raise PdfConversionError(
                    message=f"MinerU 解析失败：{item.get('err_msg', '未提供原因')}",
                    node_name=self.name,
                )

            self.logger.info(
                "MinerU 解析中，state=%s，batch_id=%s",
                task_state,
                batch_id,
            )
            time.sleep(3)

        raise PdfConversionError(
            message=f"等待 MinerU 解析超时（轮询预算 600 秒），batch_id={batch_id}",
            node_name=self.name,
        )

    def _step_3_download_and_extract(
            self,
            zip_url: str,
            output_dir: Path,
            pdf_stem: str,
    ) -> Path:
        """下载结果 ZIP，保留图片结构并返回 PDF 同名 Markdown 路径。"""
        # 每次运行创建独立目录，不覆盖和删除上一次的结果。
        run_dir = Path(tempfile.mkdtemp(prefix=f"{pdf_stem}_", dir=output_dir))
        zip_path = run_dir / "result.zip"
        with requests.get(
            zip_url,
            stream=True,
            timeout=(10, 120),
        ) as response:
            response.raise_for_status()
            with zip_path.open("wb") as target:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        target.write(chunk)

        extract_dir = run_dir / "extracted"
        extract_dir.mkdir()
        with zipfile.ZipFile(zip_path) as archive:
            # 先检查 ZIP 成员不能逃出本次目录，再执行解压。
            extract_root = extract_dir.resolve()
            for member in archive.infolist():
                target_path = (extract_dir / member.filename).resolve()
                if not target_path.is_relative_to(extract_root):
                    raise PdfConversionError(
                        message="解析结果 ZIP 包含越界路径，已停止解压",
                        node_name=self.name,
                    )
            archive.extractall(extract_dir)

        full_md = extract_dir / "full.md"
        if not full_md.is_file():
            raise PdfConversionError(
                message="解析结果缺少根目录 full.md，请检查本次结果 ZIP",
                node_name=self.name,
            )

        md_path = full_md.with_name(f"{pdf_stem}.md")
        full_md.rename(md_path)
        self.logger.info("Markdown 已保存：%s", md_path)
        return md_path.resolve()


if __name__ == "__main__":
    # 这是本节学习期间的临时真实验证入口，后续接入主图后再迁移或删除。
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    # 先改成你电脑上真实存在的 PDF；不要使用不存在的示例路径。
    pdf_path = Path(
        r"E:\dev\python\project-study\shopkeeper-brain\reference\掌教智库\2.资料\04-设备手册汇总\doc\万用表RS-12的使用.pdf"
    )
    output_dir = Path(
        r"E:\dev\python\project-study\shopkeeper-brain\workspace\day03-real-run"
    )
    state = create_default_state(
        pdf_path=str(pdf_path),
        file_dir=str(output_dir),
    )

    print("开始验证 PDF 转 Markdown")
    print("PDF：", pdf_path)
    print("输出目录：", output_dir)
    result = NodePDFToMD()(state)

    md_path = Path(result["md_path"])
    assert result is state
    assert md_path.is_file()
    assert md_path.is_relative_to(output_dir.resolve())
    assert result["md_content"] == md_path.read_text(encoding="utf-8")
    assert result["md_content"].strip()

    image_suffixes = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    image_count = sum(
        path.is_file() and path.suffix.lower() in image_suffixes
        for path in md_path.parent.rglob("*")
    )
    print("Markdown：", md_path)
    print("正文字符数：", len(result["md_content"]))
    print("图片文件数：", image_count)
    print("Markdown 前 300 个字符：")
    print(result["md_content"][:300])
    print("PDF 转 Markdown：通过")