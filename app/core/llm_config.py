import os

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr


@dataclass
class LLMConfig:
    """主体识别文本模型的连接信息；默认展示时隐藏密钥。"""

    base_url: str
    api_key: SecretStr = field(repr=False) # 打印时不显示明文
    model: str
    temperature: float


def load_llm_config() -> LLMConfig:
    """读取本地文本模型配置，已有系统环境变量优先。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)

    return LLMConfig(
        base_url=os.getenv('SHOPKEEPER_BRAIN_LLM_BASE_URL'),
        api_key=SecretStr(os.getenv('SHOPKEEPER_BRAIN_LLM_API_KEY',"")),
        model=os.getenv('SHOPKEEPER_BRAIN_LLM_MODEL'),
        temperature=float(
            os.getenv('SHOPKEEPER_BRAIN_LLM_TEMPERATURE', '0.1')
        )
    )


if __name__ == '__main__':
    config = load_llm_config()
    print(config)
