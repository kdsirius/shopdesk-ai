# 第 4 节 Markdown 图片处理施工计划

> **给带练执行者：**本计划服务于“先写教程，用户手敲代码，再隔离验收”的流程。不得直接修改 `src/` 学习代码；教程交付后等待用户手敲并明确说“写完了”。

**目标：**为第 3 节生成的真实 Markdown 增加图片扫描、视觉摘要、MinIO 持久化、Markdown 引用替换和状态回写能力。

**架构：**新增 `NodeMdImg` 作为导入流程节点，沿用现有 `BaseNode`、`ImportGraphState` 和异常层级。节点把本地 Markdown 图片处理拆成读取、筛选、摘要、上传替换、备份五个边界；外部 VL 模型和 MinIO 只通过配置与客户端接入，不把凭证放入状态。

**技术栈：**Python 3.11+、uv、LangChain OpenAI 兼容客户端、MinIO Python SDK、python-dotenv、现有 `requests`/LangGraph。

---

## 文件边界

- 新建：`src/shopkeeper_brain/core/image_config.py`，读取 VL 模型和图片处理配置。
- 新建：`src/shopkeeper_brain/core/minio_config.py`，读取 MinIO 端点、桶和图片前缀。
- 新建：`src/shopkeeper_brain/processor/import_processor/nodes/node_md_img.py`，实现图片处理节点和学习期 `__main__` 真实入口。
- 修改：`pyproject.toml`，增加 `langchain-openai` 和 `minio` 直接依赖。
- 修改：`.env.example`，增加不含真实凭证的 VL/MinIO 配置模板。
- 新建：`docs/study/day04-Markdown图片处理.md`，只写业务原理、手敲代码和真实验证。
- 验收副本：`workspace/verification/day04/`，由验收阶段创建，不写入参考区。
- 收尾记忆：`docs/memory/day04-acceptance.md` 和 `docs/memory/learning-progress.md`，只在用户代码验收完成后更新。

## Task 1：落盘第 4 节教程的资料边界和业务流程

- [ ] 在 `docs/study/day04-Markdown图片处理.md` 开头写明上一节输出是 `md_path`/`md_content`，不重复 PDF 上传、轮询、ZIP 下载和 Markdown 生成。
- [ ] 记录 day04 视频实际覆盖到 VL 摘要；把 MinIO 上传、URL 替换、`_new.md` 备份标成课堂笔记补全范围。
- [ ] 用 Mermaid 表达 `md_path/md_content → images/ → target_images → summaries + urls → new Markdown → state`。
- [ ] 给出输入、输出、外部依赖和跳过条件表；明确 `md_content` 与磁盘 Markdown 必须保持一致。

## Task 2：编写本地图片处理阶段的手敲代码

- [ ] 在教程中提供完整的 `node_md_img.py`，包含 `NodeMdImg.process()`、路径读取、图片后缀筛选、Markdown 引用查找和前后文截取。
- [ ] 代码沿用现有异常类：缺少 `md_path` 使用 `StateFieldError`，文件不存在使用 `FileProcessingError`，节点外异常由 `BaseNode` 统一包装。
- [ ] 图片筛选只处理 `.jpg`、`.jpeg`、`.png`、`.gif`、`.bmp`、`.webp`，并跳过没有在 Markdown 中引用的同级文件。
- [ ] 使用 `re.escape(image_file)` 和非贪婪匹配；上下文默认取图片标签前后各 100 个字符。
- [ ] 教程解释当前真实 Markdown 中的图片引用和 `images/` 文件数量，不添加模拟图片。

## Task 3：编写真实 VL 摘要阶段

- [ ] 在教程中提供完整的 `image_config.py` 和 `.env.example` 片段，使用 `SHOPKEEPER_BRAIN_` 前缀并隐藏 Token 默认展示。
- [ ] 在 `pyproject.toml` 中补充 `langchain-openai`；使用 `ChatOpenAI` 的 OpenAI 兼容 `base_url`、`api_key`、模型名和低温度配置。
- [ ] 图片读取后编码为 Base64，消息中同时携带文本提示和 `image_url` 数据 URI；提示包含文档主名、图片上文和下文，并要求中文短摘要。
- [ ] 使用 `deque` 记录滑动时间窗口中的请求时间；达到上限时等待最早请求过期后再发起下一次请求。
- [ ] 明确真实 VL 调用需要凭证；无凭证时验证状态只能是“跳过/未运行”。

## Task 4：编写 MinIO 上传、替换和备份阶段

- [ ] 在教程中提供完整的 `minio_config.py`，读取 endpoint、access key、secret key、bucket、图片前缀和 secure 配置。
- [ ] 在 `pyproject.toml` 中补充 `minio`；节点创建客户端时检查桶，不存在则创建。
- [ ] 上传前按文档主名清理旧对象前缀；使用 `list_objects(..., recursive=True)` 和 `remove_objects(...)`。
- [ ] 使用 `fput_object` 上传图片，依据后缀生成 content type，并构造对象 URL。
- [ ] 只有同时拥有摘要和 URL 的图片才进入替换映射；使用 `pattern.sub(lambda ...)` 把本地引用替换成摘要和远程 URL。
- [ ] 保存原文件旁边的 `<stem>_new.md`，成功写入后才更新 `state["md_content"]` 和 `state["md_path"]`。
- [ ] 记录参考代码快照中第 4、5 步曾被注释的事实，不把课堂笔记扩展描述成已经在视频代码中完成的事实。

## Task 5：编写学习期真实入口和验证步骤

- [ ] 在教程中给出 `__main__` 的真实运行入口：读取用户准备好的第 3 节 Markdown，调用 `NodeMdImg()(state)`，检查新 Markdown 存在、状态内容与文件一致、图片引用已变成远程 URL。
- [ ] 先做本地确定性探针：真实 Markdown 存在、`images/` 存在、引用图片可找到、未引用图片不会进入目标列表。
- [ ] 再做真实 VL/MinIO 验证；外部服务不可用时分别记录“跳过”或“未运行”，不使用模拟模型、模拟 MinIO 或假响应。
- [ ] 教程末尾列出失败定位：缺路径、缺图片目录、图片未引用、模型配置缺失、限流等待、MinIO 连接失败、上传失败、替换后内容不一致。
- [ ] 不新增自动化测试文件；验证命令和输出条数只能在实际运行后填写。

## Task 6：文档自检和交付

- [ ] 检查章节标题、业务/手敲/验证三块结构、对照参考项目、小结是否齐全。
- [ ] 检查每个可落盘代码块正上方紧邻 `**文件**：` 标记，路径均相对仓库根目录，代码块包含完整 import 和辅助方法。
- [ ] 检查教程没有写入真实 Token、签名 URL 或用户本地绝对路径作为必需配置。
- [ ] 使用只读搜索检查所有代码标记、状态值和“未验证”措辞；未运行命令不得写成通过。
- [ ] 只更新教程和施工计划，不清理已有 `__pycache__`，不修改 `reference/`，不执行 Git 提交。

## Task 7：用户手敲后的隔离验收

- [ ] 用户说完成后读取用户真实文件，不拿教程代码代替实现。
- [ ] 将用户工程复制到 `workspace/verification/day04/`，不复制 `.env` 和 `__pycache__`。
- [ ] 在隔离副本运行 `uv sync`、`compileall`、模块导入和真实 Markdown 本地行为探针；依赖安装使用清华 PyPI 镜像。
- [ ] 有真实外部凭证和服务时运行 VL/MinIO 正向验证；否则如实记录跳过。
- [ ] 至少在隔离副本做一次破坏性实验：破坏图片引用替换或状态回写关键行，确认对应探针按预期失败，恢复后再验证通过。
- [ ] 按“必须改 / 建议改 / 可选”给出批改意见；通过后更新 `day04-acceptance.md`、进度文件，并提供用户可直接使用的学习代码和收尾文档 Git 提交信息；AI 不执行提交。
