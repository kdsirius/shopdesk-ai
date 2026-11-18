from http import HTTPStatus

import dashscope

from shopkeeper_brain.core.rerank_config import load_rerank_config
from shopkeeper_brain.processor.import_processor.exceptions import ConfigurationError


def rerank_documents(query: str, documents: list[str]) -> list[float]:
    """调用 DashScope 重排模型，返回与 documents 一一对应的相关性分数（0 到 1）。"""
    config = load_rerank_config()
    api_key = config.api_key.get_secret_value()
    if not api_key:
        raise ConfigurationError("重排密钥未配置，请检查 SHOPKEEPER_BRAIN_RERANK_API_KEY")

    response = dashscope.TextReRank.call(
        model=config.model,
        query=query,
        documents=documents,
        # 要全部文档的分数，后面的断崖检测需要完整的分数序列。
        top_n=len(documents),
        return_documents=False,
        # 密钥通过参数传入，不写进 dashscope 的全局变量
        api_key=api_key,
        # 空串换成 None，表示不传 instruct。
        instruct=config.instruct or None
    )

    if response.status_code != HTTPStatus.OK:
        raise RuntimeError(f"DashScope 重排调用失败：{response.status_code} {response.message}")

    # 服务端按分数从高到低返回，index 才是文档在请求里的原位置，分数要按它放回去。
    scores = [0.0] * len(documents)
    for item in response.output["results"]:
        scores[item["index"]] = float(item["relevance_score"])
    return scores


if __name__ == "__main__":
    query = "万用表怎么测量交流电压？"
    documents = [
        "将功能转盘置于 V AC 的位置，黑表笔插 COM，红表笔插 V，笔尖接触被测物。",
        "今天中午去吃猪脚饭吧。",
        "测量电阻前必须先断开被测电路的电源。",
    ]
    for document, score in zip(documents, rerank_documents(query, documents)):
        print(f"{score:.4f}  {document}")
