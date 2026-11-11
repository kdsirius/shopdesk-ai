# 第 2 节验收记录

- 验收日期：2026-11-11
- 验收副本：`workspace/verification/day02/user-project-rerun/`
- 用户真实文件：`state.py`、`exceptions.py`、`nodes/node_entry.py`、`main_graph.py`
- 自动化测试：本节按约定未新增测试文件

## 首轮审阅

- 编译、模块导入、PDF/Markdown 分支、路由和异常分支均通过。
- AI 内部验收曾在隔离副本中将 PDF 路由临时改为 Markdown 路由，真实路由断言按预期失败，恢复后通过；该实验不属于用户操作步骤。
- 发现必须修改项：`StateFieldError` 接收 `field_name` 但没有保存，调用方读取 `exc.field_name` 时出现 `AttributeError`。

## 修订后验证

- `uv sync --python E:/software/devsoft/python/python/python3.12/python.exe`：通过。
- `uv run python -m compileall -q src/shopkeeper_brain`：通过。
- `StateFieldError` 的 `node_name`、`field_name`、`expected_type`：通过。
- 真实 PDF 路径：PDF 标记、PDF 路径、标题和 `node_pdf_to_md` 路由：通过。
- 真实 Markdown 路径：Markdown 标记、Markdown 路径、标题和 `node_md_img` 路由：通过。
- 不支持格式：抛出 `ValidationError`，节点名为 `node_entry`：通过。
- 缺失路径：抛出 `StateFieldError`，字段名为 `import_file_path`：通过。
- 同一个状态对象由 PDF 重用为 Markdown：旧 PDF 路径清理、标记切换：通过。
- `BaseNode` 普通异常包装：`cause` 和 `__cause__` 均保留原始异常：通过。
- AI 内部破坏性实验：将隔离副本中的 PDF 路由改为 `node_md_img` 后断言失败；恢复后编译和路由验证通过。用户未执行该实验。
- 外部服务：PDF 解析、模型、Milvus、MinIO、MongoDB：跳过，本节未接入。

## 结论

第 2 节验收通过，没有遗留必须改项。可以开始第 3 节 PDF 转 Markdown 施工图纸。
