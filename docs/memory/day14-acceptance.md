# 第 14 节验收记录：FastAPI 与 SSE

2026-11-18 用户报告已完成手敲与自测。以下为用户实际保存源码的隔离复验，章节状态见[学习进度](learning-progress.md)。

- **通过**。将保存的源码、依赖声明与锁文件逐字节复制到 `workspace/verification/day14/formal-acceptance-20261118/project/`。副本未复制 `.env`。通过清华源和短缓存运行 `uv sync --locked`，并在 CPython 3.11.15 下编译。实际版本为 FastAPI 0.163.2、Pydantic 2.14.3、Uvicorn 0.54.0。直接运行副本的 `api/main.py` 启动服务。
- **通过**。`GET /` 与 `GET /demo/sse` 均返回 200，正文与真实 HTML 字节一致。浏览器点击「检查服务」后显示 `{"ok":true}`。Swagger 页面提交合法问题显示 200，回显已去除首尾空白。缺字段、数字类型和纯空白显示 422。独立 HTTP 请求也核对了 `body.question`、`path.run_id`、`query.steps` 的错误定位及上下限。OpenAPI 声明包含 `question` 的最小长度约束。
- **通过**。真实 HTTP 流返回 `text/event-stream`，省略步数时收到三条 `progress`，显式指定两步时收到两条。每条 JSON 的 `run_id`、`step`、`total` 均正确，末尾是 `complete` 事件，随后响应结束。浏览器约每秒显示一条进度，完成后连接进入 `CLOSED`，按钮恢复可点击。完成后观察 3.5 秒，服务访问日志记录一次对应订阅。
- **通过**。隔离实验首次定位结束行的断言失败，副本当时还未改写。改用事件名前缀定位并确认移除 `complete` 后，真实 HTTP 探针按预期失败，原因是收到最后一条进度后没有完成事件。恢复副本原字节并核对哈希后，同一探针复验通过。
- **结论**。源码无必须修改项。`PreviewRequest.question` 当前使用的 `constr()` 在锁定版本中运行正确。Pydantic 建议使用教程的 `Annotated[str, StringConstraints(...)]`，以便静态分析。验收时新增 SSE 页面在暂存区仍为空文件，工作区已有完整实现，提交前需要重新暂存页面。
- **未运行**。本次隔离复验没有通过 PyCharm 图形界面启动或调试。项目无自动化测试套件。业务上传、查询、会话队列、数据库与模型调用归后续章节，本次跳过。
- **提交后核对通过**。`62636d8` 已包含完整的 SSE 页面。提交中的源码、依赖声明和锁文件共 49 个文件，统一换行符后与正式验收副本一致。`PreviewRequest.question` 保留当时已验证的 `constr()` 写法。本轮收尾以内容比对为依据，HTTP 与浏览器沿用上述实测记录。
