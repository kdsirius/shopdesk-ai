import logging
from abc import ABC, abstractmethod

from shopkeeper_brain.processor.query_processor.state import QueryGraphState


class NodeBase(ABC):
    """所有查询节点共享的执行外壳：统一日志，异常记录后原样抛出。"""

    name = "base_node"

    def __init__(self) -> None:
        if self.name == "base_node":
            raise ValueError("子类必须覆盖 name")
        self.logger = logging.getLogger(f"query.{self.name}")

    def __call__(self, state: QueryGraphState) -> QueryGraphState:
        """让节点实例可以被 LangGraph 当作函数调用。"""
        self.logger.info("%s 开始", self.name)
        try:
            result = self.process(state)
        except Exception as exc:
            self.logger.error("%s 失败：%s", self.name, exc)
            raise
        self.logger.info("%s 完成", self.name)
        return result

    @abstractmethod
    def process(self, state: QueryGraphState) -> QueryGraphState:
        """子类实现具体业务。"""
        raise NotImplementedError
