import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class EmbeddingConfig:
    """本地 BGE-M3 的位置与推理设备。"""

    model_path: Path
    device: str
    use_fp16: bool


def load_embedding_config() -> EmbeddingConfig:
    """相对模型路径以项目根目录解析，系统环境变量优先。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env", override=False)
    model_path = Path(os.getenv("SHOPKEEPER_BRAIN_BGE_M3_PATH", "workspace/models/bge-m3"))
    if not model_path.is_absolute():
        model_path = project_root / model_path

    return EmbeddingConfig(
        model_path=model_path,
        device=os.getenv("SHOPKEEPER_BRAIN_BGE_DEVICE", "cpu").strip(),
        use_fp16=os.getenv("SHOPKEEPER_BRAIN_BGE_FP16", "false").strip().lower() in ("1", "true")
    )
