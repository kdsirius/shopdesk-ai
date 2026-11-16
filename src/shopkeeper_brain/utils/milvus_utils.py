import math

from numbers import Real

from pymilvus import MilvusClient

from shopkeeper_brain.core.milvus_config import load_milvus_config
from shopkeeper_brain.processor.import_process.exceptions import ConfigurationError, ValidationError

_milvus_client: MilvusClient | None = None


def get_milvus_client() -> MilvusClient:
    """首次调用连接 Milvus，后续在当前进程复用同一客户端。"""
    global _milvus_client
    if _milvus_client is not None:
        return _milvus_client

    config = load_milvus_config()
    if not config.uri:
        raise ConfigurationError("Milvus URI 未配置，请检查 SHOPKEEPER_BRAIN_MILVUS_URI")

    _milvus_client = MilvusClient(uri=config.uri)
    return _milvus_client


def escape_milvus_string(value: str) -> str:
    """转义 Milvus 过滤表达式中的反斜杠和引号。"""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("'", "\\'")


def restore_sparse_vector(value: object, field_name: str) -> dict[int, float]:
    """把 JSON 读取后的 Sparse 字典恢复为 Milvus 可接受的整数键字典。"""
    if not isinstance(value, dict) or not value:
        raise ValidationError(message=f"{field_name} 必须是非空 Sparse 字典")

    restored: dict[int, float] = {}
    for raw_index, raw_weight in value.items():
        if isinstance(raw_index, bool) or not isinstance(raw_index, (int, str)):
            raise ValidationError(message=f"{field_name} 的特征编号必须是整数或整数文本")

        try:
            index = int(raw_index)
        except(TypeError, ValueError) as exc:
            raise ValidationError(message=f"{field_name} 的特征编号无法转换为整数：{raw_index!r}") from exc

        if index < 0:
            raise ValidationError(message=f"{field_name} 的特征编号不能为负数：{index}")

        if isinstance(raw_weight, bool) or not isinstance(raw_weight, Real):
            raise ValidationError(message=f"{field_name} 的权重必须是数字：{raw_weight!r}")

        weight = float(raw_weight)
        if not math.isfinite(weight):
            raise ValidationError(message=f"{field_name} 的权重必须是有限数值：{raw_weight!r}")

        restored[index] = weight

    return restored
