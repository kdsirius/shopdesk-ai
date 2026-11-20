from app.core.exceptions import ProcessingError


class ImportProcessError(ProcessingError):
    """导入流程的基础异常。"""


class FileProcessingError(ImportProcessError):
    """本地文件不存在或无法处理。"""


class MilvusError(ImportProcessError):
    """Milvus 连接、集合或写入操作失败。"""


class PdfConversionError(FileProcessingError):
    """PDF 上传、解析或结果处理失败。"""
