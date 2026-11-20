class ProcessingError(Exception):
    """导入和查询共用的处理异常。"""

    def __init__(
            self,
            message: str,
            node_name: str = "",
            cause: Exception | None = None,
    ) -> None:
        self.node_name = node_name
        self.cause = cause
        super().__init__(message)

    def __str__(self) -> str:
        prefix = f"[{self.node_name}] " if self.node_name else ""
        cause = f" (原因: {self.cause})" if self.cause else ""
        return f"{prefix}{super().__str__()}{cause}"


class StateFieldError(ProcessingError):
    """状态字段缺失、为空或类型不符合预期。"""

    def __init__(
            self,
            node_name: str = "",
            field_name: str = "",
            expected_type: type | None = None,
            message: str = "",
            cause: Exception | None = None,
    ) -> None:
        self.node_name = node_name
        self.field_name = field_name
        self.expected_type = expected_type
        if not message:
            message = f"状态字段 '{field_name}' 缺失或无效"
            if expected_type is not None:
                message += f"，期望类型: {expected_type.__name__}"
        super().__init__(message, node_name=node_name, cause=cause)


class ValidationError(ProcessingError):
    """输入数据不符合节点要求。"""


class ConfigurationError(ProcessingError):
    """外部服务配置缺失。"""
