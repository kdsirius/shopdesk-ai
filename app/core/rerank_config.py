import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr

DEFAULT_RERANK_MODEL = "qwen3-rerank"


@dataclass(frozen=True)
class RerankConfig:
    """阿里云百炼（DashScope）重排模型的配置；默认展示时隐藏密钥。"""

    model: str
    # 留空表示不传 instruct，由服务端按“问答检索”任务打分。
    instruct: str
    api_key: SecretStr = field(repr=False)


def load_rerank_config() -> RerankConfig:
    """从项目根目录读取重排配置，系统环境变量优先。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)

    return RerankConfig(
        # .env.example 里模型名可以留空，留空时使用 qwen3-rerank。
        model=os.getenv("RERANK_MODEL", "").strip() or DEFAULT_RERANK_MODEL,
        instruct=os.getenv("RERANK_INSTRUCT", "").strip(),
        api_key=SecretStr(os.getenv("RERANK_API_KEY", "").strip()),
    )


if __name__ == "__main__":
    print(load_rerank_config())
