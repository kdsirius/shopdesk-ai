import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class MilvusConfig:
    """Milvus 连接地址和本节使用的两个集合。"""

    uri: str
    item_name_collection: str
    chunk_collection: str


def load_milvus_config() -> MilvusConfig:
    """从项目根目录读取 Milvus 配置，系统环境变量优先。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)

    return MilvusConfig(
        uri=os.getenv("MILVUS_URI", "").strip(),
        item_name_collection=os.getenv("MILVUS_ITEM_NAME_COLLECTION", "").strip(),
        chunk_collection=os.getenv("MILVUS_CHUNK_COLLECTION", "").strip()
    )
