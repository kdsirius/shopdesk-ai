import base64
import json
import logging
import mimetypes
import re
import time
from collections import deque
from pathlib import Path
from typing import Deque

from langchain_openai import ChatOpenAI
from minio import Minio
from minio.deleteobjects import DeleteObject

from shopkeeper_brain.core.image_config import load_image_config
from shopkeeper_brain.core.minio_config import load_minio_config
from shopkeeper_brain.processor.import_processor.BaseNode import BaseNode
from shopkeeper_brain.processor.import_processor.exceptions import (
    ConfigurationError,
    FileProcessingError,
    StateFieldError,
)
from shopkeeper_brain.processor.import_processor.state import (
    ImportGraphState, create_default_state,
)

ImageTarget = tuple[str, Path, tuple[str, str]]
ImageInfo = dict[str, tuple[str, str]]


class NodeMdImg(BaseNode):
    """处理 Markdown 图片，完成摘要、上传和引用替换。"""

    name = "node_md_img"
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """读取 Markdown，处理图片，并把新结果写回状态。"""
        md_content, md_path, images_dir = self._step_1_get_content(state)
        if not images_dir.is_dir():
            self.logger.info("图片目录不存在，跳过图片处理：%s", images_dir)
            return state

        target_images = self._step_2_scan_images(md_content, images_dir)
        if not target_images:
            self.logger.info("没有找到被 Markdown 引用的支持格式图片")
            return state

        summaries = self._step_3_generate_summaries(
            md_path.stem,
            target_images,
        )

        new_md_content = self._step_4_upload_and_replace(
            md_path.stem,
            target_images,
            summaries,
            md_content,
        )

        new_md_path = self._step_5_backup_new_md_file(
            md_path,
            new_md_content,
        )

        # 只有新文件写入成功后，才让下游看到新的状态。
        state["md_path"] = str(new_md_path)
        state["md_content"] = new_md_content
        return state

    def _step_1_get_content(
            self,
            state: ImportGraphState,
    ) -> tuple[str, Path, Path]:
        """取得 Markdown 正文、文件路径和同级图片目录。"""
        md_path_value = state.get("md_path")
        if not isinstance(md_path_value, str) or not md_path_value.strip():
            raise StateFieldError(
                node_name=self.name,
                field_name="md_path",
                expected_type=str,
            )

        md_path = Path(md_path_value).resolve()
        if not md_path.is_file():
            raise FileProcessingError(
                message=f"Markdown 文件不存在或不是普通文件：{md_path}",
                node_name=self.name,
            )

        md_content = state.get('md_content', "")
        if not isinstance(md_content, str):
            raise StateFieldError(
                node_name=self.name,
                field_name="md_content",
                expected_type=str,
            )
        if not md_content:
            md_content = md_path.read_text(encoding='utf-8')

        return md_content, md_path, md_path.parent / "images"

    def _step_2_scan_images(
            self,
            md_content: str,
            images_dir: Path,
    ) -> list[ImageTarget]:
        """筛选支持格式且确实被 Markdown 引用的图片。"""
        target_images: list[ImageTarget] = []

        for image_path in sorted(images_dir.iterdir()):
            if not image_path.is_file():
                continue
            if image_path.suffix.lower() not in self.image_extensions:
                continue

            context = self._find_image_in_md(md_content, image_path.name)
            if context is None:
                self.logger.info("图片未被 Markdown 引用，跳过：%s", image_path.name)
                continue

            target_images.append((image_path.name, image_path, context))
        self.logger.info("筛选出 %s 张待处理图片", len(target_images))
        return target_images

    def _find_image_in_md(
            self,
            md_content: str,
            image_file: str,
            context_len: int = 100,
    ) -> tuple[str, str] | None:
        """查找图片标签，并截取标签前后各一段文本。"""
        pattern = re.compile(
            r"!\[.*?]\(.*?"
            + re.escape(image_file)
            + r".*?\)"
        )
        match = pattern.search(md_content)
        if match is None:
            return None

        start, end = match.span()
        before = md_content[max(0, start - context_len):start]
        after = md_content[end: min(len(md_content), end + context_len)]
        return before, after

    def _step_3_generate_summaries(
            self,
            doc_stem: str,
            target_images: list[ImageTarget],
    ) -> dict[str, str]:
        """按限流规则调用 VL 模型，返回图片摘要映射。"""
        config = load_image_config()
        if not config.base_url:
            raise ConfigurationError(
                message="视觉模型配置缺失：SHOPKEEPER_BRAIN_VL_BASE_URL",
                node_name=self.name,
            )
        if not config.api_key:
            raise ConfigurationError(
                message="视觉模型配置缺失：SHOPKEEPER_BRAIN_VL_API_KEY",
                node_name=self.name,
            )
        if not config.model:
            raise ConfigurationError(
                message="视觉模型配置缺失：SHOPKEEPER_BRAIN_VL_MODEL",
                node_name=self.name,
            )
        request_times: Deque[float] = deque()
        summaries: dict[str, str] = {}
        for image_file, image_path, context in target_images:
            self._apply_api_rate_limit(
                request_times,
                config.max_requests,
                config.window_seconds
            )
            summaries[image_file] = self._summarize_image(
                image_path,
                doc_stem,
                context,
                config,
            )
        return summaries

    def _apply_api_rate_limit(
            self,
            request_times: Deque[float],
            max_requests: int,
            window_seconds: int,
    ) -> None:
        """用滑动时间窗口限制 VL 请求频率。"""
        if max_requests <= 0 or window_seconds <= 0:
            raise ValueError("图片摘要限流参数必须是正数")

        current_time = time.monotonic()
        while request_times and current_time - request_times[0] >= window_seconds:
            request_times.popleft()

        if len(request_times) >= max_requests:
            sleep_seconds = window_seconds - (current_time - request_times[0])
            if sleep_seconds > 0:
                self.logger.info(
                    "触发 VL 限流，等待 %.2f 秒后继续",
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

            current_time = time.monotonic()
            while request_times and current_time - request_times[0] >= window_seconds:
                request_times.popleft()

        request_times.append(current_time)

    def _summarize_image(
            self,
            image_path: Path,
            doc_stem: str,
            context: tuple[str, str],
            config,
    ) -> str:
        """把一张本地图片和它在文档中的上下文交给 VL 模型。"""
        mime_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        base64_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        prompt = (
            f'这是“{doc_stem}”文件中的一张图片。'
            f'图片上文为“{context[0]}”，下文为“{context[1]}”。'
            "请只返回一段普通中文文本，作为 Markdown 图片标题，"
            "控制在 50 字以内。不要输出 Markdown、代码围栏、图片标签、"
            "解释文字或前缀。"
        )
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{mime_type};base64,{base64_image}"
                        },
                    },
                ],
            }
        ]

        try:
            chat_model = ChatOpenAI(
                model=config.model,
                api_key=config.api_key,
                base_url=config.base_url,
                temperature=config.temperature
            )
            response = chat_model.invoke(messages)
        except Exception as exc:
            raise FileProcessingError(
                message=f"图片摘要生成失败：{image_path.name}",
                node_name=self.name,
            ) from exc

        summary = self._clean_image_summary(str(response.content))
        if not summary or "```" in summary or "![" in summary:
            raise FileProcessingError(
                message=f"图片摘要格式无效：{image_path.name}",
                node_name=self.name,
            )

        return summary

    @staticmethod
    def _clean_image_summary(summary: str) -> str:
        """把模型输出清洗成可以放进 Markdown Alt 文本的普通短文本。"""
        summary = summary.strip()

        # 去掉 ```markdown、```md 或单纯的 ``` 包裹
        summary = re.sub(
            r"^```(?:markdown|md)?\s*",
            "",
            summary,
            flags=re.IGNORECASE,
        )
        summary = re.sub(r"\s*```$", "", summary)

        # 把嵌套图片标签转换成它的 Alt 文本
        summary = re.sub(
            r"!\[([^\]]*)\]\([^)]*\)",
            r"\1",
            summary,
        )

        # 合并换行和多余空格
        summary = re.sub(r"\s+", " ", summary).strip()

        # 保留和提示词一致的长度上限
        return summary[:50]

    def _step_4_upload_and_replace(
            self,
            doc_stem: str,
            target_images: list[ImageTarget],
            summaries: dict[str, str],
            md_content: str,
    ) -> str:
        """清理旧对象、上传图片，并替换 Markdown 中的图片标签。"""
        config = load_minio_config()
        for field_name, value in (
                ("SHOPKEEPER_BRAIN_MINIO_ENDPOINT", config.endpoint),
                ("SHOPKEEPER_BRAIN_MINIO_ACCESS_KEY", config.access_key),
                ("SHOPKEEPER_BRAIN_MINIO_SECRET_KEY", config.secret_key),
                ("SHOPKEEPER_BRAIN_MINIO_BUCKET", config.bucket),
        ):
            if not value:
                raise ConfigurationError(
                    message=f"MinIO 配置缺失：{field_name}",
                    node_name=self.name,
                )

        try:
            client = Minio(
                endpoint=config.endpoint,
                access_key=config.access_key,
                secret_key=config.secret_key,
                secure=config.secure,
            )
            if not client.bucket_exists(config.bucket):
                client.make_bucket(config.bucket)

            # Markdown 保存的是匿名直链，因此桶必须允许匿名读取对象。
            # 这段代码必须放在 if 外面，已有桶也要补上策略。
            policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": ["*"]},
                        "Action": ["s3:GetObject"],
                        "Resource": [
                            f"arn:aws:s3:::{config.bucket}/*"
                        ],
                    }
                ],
            }
            client.set_bucket_policy(
                config.bucket,
                json.dumps(policy),
            )
            upload_dir = f"{config.image_prefix}/{doc_stem}".replace(" ", "")
            self._clean_minio_directory(client, config.bucket, upload_dir)
            urls = self._upload_images_batch(
                client,
                config,
                upload_dir,
                target_images,
            )
        except ConfigurationError:
            raise
        except Exception as exc:
            raise FileProcessingError(
                message=f"MinIO 图片处理失败：{doc_stem}",
                node_name=self.name,
            ) from exc
        image_info = self._merge_summary_and_url(summaries, urls)
        return self._process_md_file(md_content, image_info)

    def _clean_minio_directory(
            self,
            client: Minio,
            bucket: str,
            prefix: str,
    ) -> None:
        """删除当前文档对应的旧对象，保证重复运行不会累积垃圾文件。"""
        objects = client.list_objects(
            bucket_name=bucket,
            prefix=prefix,
            recursive=True,
        )
        delete_list = [
            DeleteObject(name=obj.object_name)
            for obj in objects
        ]
        if not delete_list:
            return
        errors = client.remove_objects(
            bucket_name=bucket,
            delete_object_list=delete_list,
        )
        for error in errors:
            raise RuntimeError(
                f"删除 MinIO 对象失败：{error.name}"
            )

    def _upload_images_batch(
            self,
            client: Minio,
            config,
            upload_dir: str,
            target_images: list[ImageTarget],
    ) -> dict[str, str]:
        """上传目标图片并返回文件名到 URL 的映射。"""
        protocol = "https" if config.secure else "http"
        urls: dict[str, str] = {}

        for image_file, image_path, _ in target_images:
            object_name = f"{upload_dir}/{image_file}"
            content_type = mimetypes.guess_type(image_file)[0] or "application/octet-stream"
            client.fput_object(
                bucket_name=config.bucket,
                object_name=object_name,
                file_path=str(image_path),
                content_type=content_type,
            )
            urls[image_file] = (
                f"{protocol}://{config.endpoint}/{config.bucket}/{object_name}"
            )

        return urls

    def _merge_summary_and_url(
            self,
            summaries: dict[str, str],
            urls: dict[str, str],
    ) -> ImageInfo:
        """只保留同时有摘要和 URL 的图片。"""
        return {
            image_file: (summary, urls[image_file])
            for image_file, summary in summaries.items()
            if urls.get(image_file)
        }

    def _process_md_file(
            self,
            md_content: str,
            image_info: ImageInfo,
    ) -> str:
        """把本地图片标签替换成摘要和远程 URL。"""
        for image_file, (summary, new_url) in image_info.items():
            pattern = re.compile(
                r"!\[.*?]\(.*?"
                + re.escape(image_file)
                + r".*?\)"
            )
            md_content = pattern.sub(
                lambda _: f"![{summary}]({new_url})",
                md_content,
            )
        return md_content

    def _step_5_backup_new_md_file(
            self,
            origin_md_path: Path,
            md_content: str,
    ) -> Path:
        """保留原 Markdown，并把处理后的内容写成 `<stem>_new.md`。"""
        new_md_path = origin_md_path.with_name(
            f"{origin_md_path.stem}_new.md"
        )

        try:
            new_md_path.write_text(md_content, encoding="utf-8")
        except OSError as exc:
            raise FileProcessingError(
                message=f"处理后的 Markdown 保存失败：{new_md_path}",
                node_name=self.name,
            ) from exc
        return new_md_path.resolve()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s %(message)s",
    )

    md_path = Path(
        r'E:\dev\python\project-study\shopkeeper-brain\workspace\day03-real-run\万用表RS-12的使用_5gatm6ph\extracted\万用表RS-12的使用.md'.strip()).expanduser()
    state = create_default_state(
        md_path=str(md_path),
        md_content=md_path.read_text(encoding="utf-8"),
    )

    node = NodeMdImg()
    content, resolved_path, images_dir = node._step_1_get_content(state)
    targets = node._step_2_scan_images(content, images_dir)
    print("Markdown：", resolved_path)
    print("图片目录：", images_dir)
    print("被 Markdown 引用的图片数：", len(targets))

    # 这一步只验证本地输入，外部服务配置不完整时明确跳过完整链路。
    image_config = load_image_config()
    minio_config = load_minio_config()
    if not image_config.api_key or not minio_config.endpoint:
        print("本地图片扫描：通过")
        print("VL/MinIO 完整链路：跳过（缺少本地外部服务配置）")
        raise SystemExit(0)

    result = node(state)
    result_path = Path(result["md_path"])
    assert result is state
    assert result_path.is_file()
    assert result["md_content"] == result_path.read_text(encoding="utf-8")
    assert result_path.name == f"{resolved_path.stem}_new.md"
    print("处理后 Markdown：", result_path)
    print("处理后正文字符数：", len(result["md_content"]))
    print("Markdown 图片处理：通过")
