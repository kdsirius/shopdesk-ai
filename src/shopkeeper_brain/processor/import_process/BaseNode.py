from abc import ABC, abstractmethod
import logging
from typing import TypeVar

from .exceptions import ImportProcessError
from .state import ImportGraphState

StateT = TypeVar('StateT', bound=ImportGraphState)


class BaseNode(ABC):
    """所有导入节点共享的执行外壳。"""
    name = "base_node"

    def __init__(self) -> None:
        if self.name == "base_node":
            raise ValueError("子类必须覆盖 name")
        self.logger = logging.getLogger(f"import.{self.name}")

    def __call__(self, state: StateT) -> StateT:
        """让节点实例可以被 LangGraph 当作函数调用。"""
        self.logger.info("%s 开始", self.name)
        try:
            result = self.process(state)
        except ImportProcessError:
            raise
        except Exception as exc:
            raise ImportProcessError(
                message=str(exc),
                node_name=self.name,
                cause=exc,
            )from exc
        self.logger.info("%s 完成", self.name)
        return result

    @abstractmethod
    def process(self, state: StateT) -> StateT:
        """子类实现具体业务。"""
        raise NotImplementedError
