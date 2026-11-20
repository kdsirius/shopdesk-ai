import logging
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import MongoClient, DESCENDING
from pymongo.collection import Collection

from shopkeeper_brain.core.mongo_config import load_mongo_config
from shopkeeper_brain.processor.import_processor.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

_chat_message: Collection | None = None


def get_chat_message_collection() -> Collection:
    """首次调用连接 MongoDB 并确保索引存在，后续在当前进程复用同一个集合对象。"""
    global _chat_message
    if _chat_message is not None:
        return _chat_message

    config = load_mongo_config()
    if not config.uri or not config.db_name:
        raise ConfigurationError("MongoDB 未配置，请检查 SHOPKEEPER_BRAIN_MONGO_URI 和 SHOPKEEPER_BRAIN_MONGO_DB_NAME")

    # 创建客户端不会立刻连接；5 秒内选不到服务器就报错，虚拟机没开时不用干等 30 秒。
    client = MongoClient(host=config.uri, serverSelectionTimeoutMS=5000)
    collection = client[config.db_name]["chat_message"]
    # “会话 + 时间倒序”复合索引，对应“取某个会话最新几条”；已存在时重复创建不会报错。
    collection.create_index([("session_id", 1), ("ts", -1)])
    _chat_message = collection
    return collection


def save_chat_message(
        session_id: str,
        role: str,
        text: str,
        rewritten_query: str = "",
        item_names: list[str] | None = None,
        message_id: str | None = None,
        image_urls: list[str] | None = None,
) -> str:
    """没有 message_id 时新增一条消息，有 message_id 时更新这条消息；返回消息主键字符串。"""
    collection = get_chat_message_collection()
    document = {
        "session_id": session_id,
        "role": role,
        "text": text,
        "rewritten_query": rewritten_query or "",
        "item_names": item_names or [],
    }
    if image_urls is not None:
        document["image_urls"] = image_urls
    if message_id:
        # 更新只改内容，不动 ts：消息的先后顺序以第一次写入的时间为准。
        collection.update_one({"_id": ObjectId(message_id)}, {"$set": document})
        return message_id

    document["ts"] = datetime.now().timestamp()
    result = collection.insert_one(document)
    return str(result.inserted_id)


def update_message_item_names(ids: list[str], item_names: list[str]) -> int:
    """批量给历史消息补上商品名，返回实际修改的条数；失败时记录日志并返回 0。"""
    collection = get_chat_message_collection()

    try:
        result = collection.update_many(
            {"_id": {"$in": [ObjectId(message_id) for message_id in ids]}},
            {"$set": {"item_names": item_names}},
        )
        return result.modified_count
    except Exception as exc:
        logger.error("批量回填商品名失败：%s", exc)
        return 0


def get_recent_messages(session_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """读取会话最近 limit 条消息，按时间从旧到新返回；查询失败时记录日志并返回空列表。"""
    collection = get_chat_message_collection()
    try:
        # 先倒序取最新的 limit 条，再翻转成正序；升序直接加 limit 只会取到最早的几条。
        # Windows 时钟刻度较粗，连续写入的消息 ts 可能相同，再按 _id 兜底保持写入顺序。
        cursor = (
            collection
            .find({"session_id": session_id})
            .sort([("ts", DESCENDING), ("_id", DESCENDING)])
            .limit(limit)
        )
        return list(cursor)[::-1]
    except Exception as exc:
        logger.error("读取历史消息失败：%s", exc)
        return []


def clear_history(session_id: str) -> int:
    """删除一个会话的全部消息，返回删除条数；失败时记录日志并返回 0。"""
    collection = get_chat_message_collection()
    try:
        return collection.delete_many({"session_id": session_id}).deleted_count
    except Exception as exc:
        logger.error("清空会话历史失败：%s", exc)
        return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s", )

    session_id = "day09-history-check"
    clear_history(session_id)  # 每次从空会话开始，结果才能重复

    first_id = save_chat_message(session_id, "user", "你好，有万用表吗？")
    save_chat_message(session_id, "assistant", "你好！请问你想询问哪个型号？")
    save_chat_message(session_id, "user", "RS-12 万用表")
    save_chat_message(session_id, "assistant", "有的")

    # 更新第一条消息：内容变了，但它仍然排在最前面。
    save_chat_message(
        session_id,
        "user",
        "你好，有万用表吗？",
        rewritten_query="有没有万用表？",
        message_id=first_id,
    )
    messages = get_recent_messages(session_id)
    assert [m["text"] for m in messages] == [
        "你好，有万用表吗？",
        "你好！请问你想询问哪个型号？",
        "RS-12 万用表",
        "有的",
    ]
    assert messages[0]["rewritten_query"] == "有没有万用表？"

    # 只取最近 2 条，仍然是从旧到新。
    latest = get_recent_messages(session_id, limit=2)
    assert [m["text"] for m in latest] == ["RS-12 万用表", "有的"]

    # 批量回填：给还没有商品名的消息补上商品名。
    ids = [str(m["_id"]) for m in messages if not m["item_names"]]
    assert update_message_item_names(ids, ["RS PRO RS-12 数字万用表"]) == 4

    for message in get_recent_messages(session_id):
        print(message["role"], message["item_names"], message["text"])
    print("MongoDB 历史读写：通过")
