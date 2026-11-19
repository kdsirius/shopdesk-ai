from langgraph.constants import END
from langgraph.graph import StateGraph

from shopkeeper_brain.processor.import_processor.nodes.node_bge_embedding import NodeBGEEmbedding
from shopkeeper_brain.processor.import_processor.nodes.node_document_split import NodeDocumentSplit
from shopkeeper_brain.processor.import_processor.nodes.node_entry import NodeEntry
from shopkeeper_brain.processor.import_processor.nodes.node_import_milvus import NodeImportMilvus
from shopkeeper_brain.processor.import_processor.nodes.node_item_name_recognition import NodeItemNameRecognition
from shopkeeper_brain.processor.import_processor.nodes.node_md_img import NodeMdImg
from shopkeeper_brain.processor.import_processor.nodes.node_pdf_to_md import NodePDFToMD
from shopkeeper_brain.processor.import_processor.state import ImportGraphState


def route_after_entry(state: ImportGraphState) -> str:
    """根据入口节点写入的标记选择下一节点。"""
    if state.get("is_pdf_read_enabled"):
        return "node_pdf_to_md"
    if state.get("is_md_read_enabled"):
        return "node_md_img"
    return END


class KBImportWorkflow:
    def __init__(self) -> None:
        workflow = StateGraph(ImportGraphState)
        for node in (
                NodeEntry(), NodePDFToMD(), NodeMdImg(), NodeDocumentSplit(),
                NodeItemNameRecognition(), NodeBGEEmbedding(), NodeImportMilvus(),
        ):
            workflow.add_node(node.name, node)

        workflow.set_entry_point("node_entry")
        workflow.add_conditional_edges(
            "node_entry", route_after_entry, ["node_pdf_to_md", "node_md_img", END]
        )
        workflow.add_edge("node_pdf_to_md", "node_md_img")
        workflow.add_edge("node_md_img", "node_document_split")
        workflow.add_edge("node_document_split", "node_item_name_recognition")
        workflow.add_edge("node_item_name_recognition", "node_bge_embedding")
        workflow.add_edge("node_bge_embedding", "node_import_milvus")
        workflow.add_edge("node_import_milvus", END)
        self._app = workflow.compile()

    def stream(self, initial_state: ImportGraphState):
        return self._app.stream(initial_state, stream_mode="updates", version="v2")
