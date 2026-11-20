import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from pydantic import SecretStr

DEFAULT_TAVILY_MCP_URL = "https://mcp.tavily.com/mcp/"


@dataclass(frozen=True)
class TavilyConfig:
    """Tavily 远程 MCP 的地址和密钥；默认展示时隐藏密钥。"""

    mcp_url: str
    api_key: SecretStr = field(repr=False)


def load_tavily_config() -> TavilyConfig:
    """从项目根目录读取 Tavily 配置，系统环境变量优先。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)

    return TavilyConfig(
        # .env.example 里地址留空，留空时也使用官方地址。
        mcp_url=os.getenv("SHOPKEEPER_BRAIN_TAVILY_MCP_URL", "").strip() or DEFAULT_TAVILY_MCP_URL,
        api_key=SecretStr(os.getenv("SHOPKEEPER_BRAIN_TAVILY_API_KEY", "").strip()),
    )


if __name__ == "__main__":
    print(load_tavily_config())
