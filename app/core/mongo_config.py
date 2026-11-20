import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class MongoConfig:
    """MongoDB 连接地址和对话历史所在的数据库；默认展示时隐藏含密码的地址。"""

    uri: str = field(repr=False)
    db_name: str


def load_mongo_config() -> MongoConfig:
    """从项目根目录读取 MongoDB 配置，系统环境变量优先。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)

    return MongoConfig(
        uri=os.getenv("SHOPKEEPER_BRAIN_MONGO_URI", "").strip(),
        db_name=os.getenv("SHOPKEEPER_BRAIN_MONGO_DB_NAME", "").strip(),
    )
