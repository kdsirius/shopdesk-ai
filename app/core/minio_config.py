import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class MinioConfig:
    """MinIO 图片对象存储配置。"""

    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    image_prefix: str
    secure: bool


def load_minio_config() -> MinioConfig:
    """从项目根目录的 .env 读取 MinIO 配置。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)

    return MinioConfig(
        endpoint=os.getenv("SHOPKEEPER_BRAIN_MINIO_ENDPOINT", "").strip(),
        access_key=os.getenv("SHOPKEEPER_BRAIN_MINIO_ACCESS_KEY", "").strip(),
        secret_key=os.getenv("SHOPKEEPER_BRAIN_MINIO_SECRET_KEY", "").strip(),
        bucket=os.getenv("SHOPKEEPER_BRAIN_MINIO_BUCKET", "").strip(),
        image_prefix=os.getenv(
            "SHOPKEEPER_BRAIN_MINIO_IMAGE_PREFIX", "upload-images"
        ).strip().strip("/"),
        secure=os.getenv(
            "SHOPKEEPER_BRAIN_MINIO_SECURE", "false"
        ).strip().lower() == "true",
    )