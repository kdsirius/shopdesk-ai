import math

from numbers import Real

from pymilvus import MilvusClient, AnnSearchRequest, WeightedRanker

from shopkeeper_brain.core.milvus_config import load_milvus_config
from shopkeeper_brain.processor.import_processor.exceptions import ConfigurationError, ValidationError

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


def create_hybrid_search_requests(
        dense_vector: list[float],
        sparse_vector: dict[int, float],
        limit: int = 5,
        expr: str | None = None,
) -> list[AnnSearchRequest]:
    """为同一段文本构造 Dense 与 Sparse 两路检索请求，度量方式与入库时的索引一致；expr 是两路共用的过滤表达式。"""
    dense_req = AnnSearchRequest(
        data=[dense_vector],
        anns_field="dense_vector",
        param={"metric_type": "COSINE"},
        limit=limit,
        expr=expr
    )

    sparse_req = AnnSearchRequest(
        data=[sparse_vector],
        anns_field="sparse_vector",
        param={"metric_type": "IP"},
        limit=limit,
        expr=expr
    )

    return [dense_req, sparse_req]


def hybrid_search(
        client: MilvusClient,
        collection_name: str,
        reqs: list[AnnSearchRequest],
        ranker_weights: tuple[float, float] = (0.5, 0.5),
        norm_score: bool = False,
        limit: int = 5,
        output_fields: list[str] | None = None,
) -> list[list[dict]]:
    """两路结果按权重融合排序；每个查询返回一个按评分从高到低排列的候选列表。"""
    ranker = WeightedRanker(*ranker_weights, norm_score=norm_score)
    return client.hybrid_search(
        collection_name=collection_name,
        reqs=reqs,
        ranker=ranker,
        limit=limit,
        output_fields=output_fields
    )
