import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class ImageConfig:
    """图片摘要所需的视觉模型配置。"""

    base_url: str
    api_key: str = field(repr=False)
    model: str
    temperature: float
    max_requests: int
    window_seconds: int


def load_image_config() -> ImageConfig:
    """从项目根目录的 .env 读取视觉模型和限流配置。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)

    return ImageConfig(
        base_url=os.getenv("VL_BASE_URL", "").strip().rstrip("/"),
        api_key=os.getenv("VL_API_KEY", "").strip(),
        model=os.getenv("VL_MODEL", "").strip(),
        temperature=float(
            os.getenv("VL_TEMPERATURE", "0.1")
        ),
        max_requests=int(
            os.getenv("IMAGE_MAX_REQUESTS", "10")
        ),
        window_seconds=int(
            os.getenv("IMAGE_WINDOW_SECONDS", "60")
        ),
    )
