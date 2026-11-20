from pymilvus.model.hybrid import BGEM3EmbeddingFunction

from app.core.embedding_config import load_embedding_config
from app.processor.import_processor.exceptions import ConfigurationError

_bge_m3_ef: BGEM3EmbeddingFunction | None = None


def get_bge_m3_ef() -> BGEM3EmbeddingFunction:
    """首次调用加载本地模型，后续批次复用同一实例。"""
    global _bge_m3_ef
    if _bge_m3_ef is not None:
        return _bge_m3_ef

    config = load_embedding_config()
    required_files = (
        "config.json",
        "pytorch_model.bin",
        "tokenizer_config.json",
        "sentencepiece.bpe.model",
        "sparse_linear.pt",
        "colbert_linear.pt",
    )

    for name in required_files:
        if not (config.model_path / name).is_file():
            raise ConfigurationError(f"BGE-M3 模型文件缺失：{config.model_path / name}")

    if config.device == "cpu" and config.use_fp16:
        raise ConfigurationError("本节 CPU 推理请配置 SHOPKEEPER_BRAIN_BGE_FP16=false")

    _bge_m3_ef = BGEM3EmbeddingFunction(
        model_name=str(config.model_path),
        devices=config.device,
        use_fp16=config.use_fp16,
        normalize_embeddings=True,
        passage_max_length=8192,
    )
    return _bge_m3_ef


def generate_embeddings(texts: list[str]) -> dict[str, list]:
    """按输入顺序返回 Dense 列表和整数特征编号的 Sparse 字典。"""
    if not isinstance(texts, list) or not texts:
        raise ValueError("向量化输入必须是非空文本列表")
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError("向量化输入必须是非空文本列表")

    model = get_bge_m3_ef()
    embeddings = model.encode_documents(texts)
    sparse = embeddings["sparse"]
    processed_sparse: list[dict[int, float]] = []

    for index in range(len(texts)):
        start = sparse.indptr[index]
        end = sparse.indptr[index + 1]
        indices = sparse.indices[start:end].tolist()
        weights = sparse.data[start:end].tolist()
        processed_sparse.append(dict(zip(indices, weights)))

    return {
        "dense": [vector.tolist() for vector in embeddings["dense"]],
        "sparse": processed_sparse
    }

