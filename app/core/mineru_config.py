import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class MinerUConfig:
    base_url: str
    api_token: str = field(repr=False)


def load_mineru_config() -> MinerUConfig:
    """当前源码工程从根目录 .env 读取，已有环境变量优先。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    return MinerUConfig(
        base_url=os.getenv("MINERU_BASE_URL", "").strip().rstrip("/"),
        api_token=os.getenv("MINERU_API_TOKEN", "").strip(),
    )
