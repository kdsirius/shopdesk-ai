# 项目记忆：掌柜智库带练重建

## 已确认事实

- 新项目仓库名：`shopkeeper-brain`
- Python 包名：`shopkeeper_brain`
- 配置前缀：`SHOPKEEPER_BRAIN_`
- 参考项目：`reference/掌教智库/`
- 视频资料：`reference/掌教智库/4.视频/day01` 至 `day16`
- 包管理工具：`uv`
- 学习方式：教程先于手敲；用户手敲代码；上一节验收通过后才开始下一节
- 原项目优先：完成原项目已有能力前不主动扩展；发现缺陷时记录后再讨论修正
- 实验区：`workspace/`，已由根目录 `.gitignore` 忽略
- 参考资料优先级：先看 `4.视频/dayXX/` 的视频目录图片确定当天范围，再看当天课堂笔记和代码；`1.笔记/` 作为补充资料，不覆盖对应视频日的内容事实

## 当前接手快照

- 第 1 至第 5 节已通过；当前第 6 节是“主体识别”，按业务 day06 组织。
- 参考资料物理目录存在错位：`4.视频/day06/`仍是文档切片，主体识别主题和实现分布在 day07/day08；本节已按该事实整理教程。
- 进度唯一来源：`docs/memory/learning-progress.md`；第 4 节详细证据：`docs/memory/day04-acceptance.md`；第 4 节施工图纸：`docs/study/day04-Markdown图片处理.md`。
- 第 4 节的用户实现入口是 `src/shopkeeper_brain/processor/import_process/nodes/node_md_img.py::__main__`，正式主图尚未接入，`__main__` 仍是学习期真实验证入口。
- `NodeMdImg` 已通过真实 Markdown 图片筛选、VL 摘要、MinIO 上传、匿名只读策略、远程 URL 替换、`_new.md` 保存和状态回写；真实输入结果为 16 个图片文件、13 个 Markdown 引用、3 个未引用文件。
- VL 摘要必须先清洗成普通短文本，再写入 Markdown Alt 文本；当前实现已验证 13 个外层图片标签、0 个代码围栏、0 个嵌套图片标签。
- 当前环境的 `uv sync` 会被 Windows uv“不受信任的装入点”拦截；CPython 3.11.15 的编译、导入和真实业务验收已完成。后续报告这项环境限制时不要把它写成源码失败。

## 业务全景

“掌柜智库”是一个面向产品手册、维修指南和技术文档的 RAG 知识库问答系统。它把 PDF/Markdown 文档加工成可检索知识，再通过多路召回、融合、重排和大语言模型生成答案，并用 FastAPI/SSE 提供交互服务。

```mermaid
flowchart LR
    A[PDF / Markdown] --> B[文档解析]
    B --> C[图片处理]
    C --> D[文档切片]
    D --> E[主体识别]
    E --> F[向量化]
    F --> G[Milvus 入库]
    G --> H[向量检索]
    G --> I[HyDE 检索]
    G --> J[网络搜索]
    H --> K[RRF 融合]
    I --> K
    J --> K
    K --> L[Rerank 重排]
    L --> M[答案生成]
    M --> N[FastAPI / SSE]
```

## 技术事实

- Python 3.11、uv
- FastAPI、Uvicorn、Pydantic
- LangChain、LangGraph
- DashScope 兼容 OpenAI API 的 Qwen 模型
- OpenAI `text-embedding-v4`、BGE-M3、BGE-Reranker-Large
- Milvus、MongoDB、MinIO
- MinerU PDF 转 Markdown
- HTML5 + JavaScript
- SSE 流式输出、MCP Web 搜索

具体版本、环境变量和调用签名在对应章节读取真实资料后补充，不从记忆猜测。

## 初步代码地图

参考笔记给出的代码分层为：

- `api/`：HTTP 接口和路由
- `core/`：配置、路径和基础设施
- `processor/`：导入流程与查询流程的 LangGraph 状态、节点、主图
- `schema/`：请求、响应和任务状态模型
- `services/`：文件导入、任务管理等业务服务
- `utils/`：Milvus、MongoDB、MinIO、LLM、Embedding、Rerank、SSE 等工具
- `front/`：HTML 和 JavaScript 页面
- `test/`：测试代码

这是初步地图。实际重建时，参考代码与课堂笔记不一致的地方以实际代码为准，并在本文件更新。

## 重要边界

- `reference/` 只读，不修改、不格式化、不覆盖解压、不运行其中未知压缩包代码。
- 临时脚本、复制工程和测试输出统一放 `workspace/`。
- Git 只读；提交、推送由用户执行。
