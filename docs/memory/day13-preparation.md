# 第 13 节备课记录：Web 服务骨架

章节状态见[学习进度](learning-progress.md)。本记录中的实测使用教程副本。

## 资料范围

- day13 的四张视频目录图显示，01 是 day12 回顾，02 至 24 是 HTML、CSS 和 JavaScript 入门。当天代码包含表单、CSS 和 DOM 事件等示例，项目依赖里已有 FastAPI 声明，代码包里没有正式 Web 服务入口。压缩包只在内存中读取。
- day13 课堂笔记 `18【掌柜智库】【Web服务】.md` 同时包含 FastAPI 和 SSE。day14 的视频 02 讲 FastAPI 的启动、调试和热更新，后续视频覆盖参数、响应、静态文件、文件上传和 SSE。
- 用户确认第 13 节只搭静态页与同源 `GET /health` 的闭环。补充笔记 11 的导入上传和任务进度、补充笔记 13 的查询及历史接口留给业务集成，SSE 留给第 14 节，补充笔记 20 的答案输出留给第 16 节。

## 教程验证（2026-11-18）

- **通过**。三块标题、图后说明、相对链接、两个完整文件标记和 Python 语法检查通过，两个代码块按原文抽取到 `workspace/verification/day13/tutorial-20261118/project/`。副本使用现有源码、依赖声明和锁文件，未复制 `.env`。
- **通过**。清华镜像下的 `uv add` 在副本中只新增 `fastapi>=0.163.2`、`uvicorn>=0.54.0` 两条直接依赖，Web 库锁定版本未变。首次解析命令到达 60 秒限制后终止，随后解析成功。完整同步首次在旧依赖 `flagembedding==1.3.5` 的 wheel 构建处失败，报 `configuration_minicpm_reranker.py: No such file or directory`，与第 7 节的长路径现象一致。改用实验区现有的短缓存 `workspace/u/` 后，同步退出码为 0。
- **通过**。用 CPython 3.11.15、FastAPI 0.163.2、Uvicorn 0.54.0，从另一个工作目录直接运行副本的 `api/main.py`。真实浏览器打开 `/`，结果区初始为「等待检查」。点击按钮产生同源请求 `GET /health`，状态码为 200，页面显示 `{"ok":true}`。独立 HTTP 请求确认响应类型为 `application/json`。完成依赖同步后，用副本自己的解释器启动并复验 `/` 的 HTML 与 `/health` 的 JSON。首次探针在启动阶段连接超时，随后等到 Uvicorn 明确进入监听状态再请求，两条路由均返回 200。访问记录见 `uvicorn.log` 和 `uvicorn-synced-retry.log`。
- **通过**。只读接手核对时，Milvus 的 `kb_item_names`、`kb_chunks` 均存在。MongoDB 鉴权 ping 成功，`kb001.chat_message` 存在。
- **未运行**。PyCharm 的 Run 按钮由用户按教程验证。业务图、外部模型、SSE 和用户手敲代码尚未验收。教程副本没有自动化测试套件。
