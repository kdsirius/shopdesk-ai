# 根目录 `app` 迁移计划

> 本项目由当前会话按根协作规则执行；Git 只读。用户已确认目录与兼容范围。

**目标：**去掉 `src/shopkeeper_brain` 外层，将现有 Python 包迁到仓库根目录 `app/`。

**范围：**保留六个业务子目录、项目发行名和 CLI 命令、HTTP 接口、环境变量及业务行为。只更新当前运行文档，不改写历史教程与验收记录。

## 1. 迁移目录与定位

- [x] 在仓库根目录确认 `app/api/main.py` 存在且 `src/` 消失的探针当前报错 `app API entry missing`。
- [x] 把 `src/shopkeeper_brain/` 整体移到 `app/`，移除空 `src/`。只把 Python 导入前缀 `shopkeeper_brain.` 改为 `app.`。
- [x] `app/core/*_config.py` 和 `app/services/import_service.py` 的根目录定位由 `parents[3]` 改为 `parents[2]`；`node_bge_embedding.py` 与 `node_import_milvus.py` 的运行示例由 `parents[5]` 改为 `parents[4]`。Web 页面的同级包相对路径保留。
- [x] 对照迁移前后源码，确认统一换行符并扣除上述两类替换后，业务实现和页面内容一致。

## 2. 打包与验证

- [x] 在 `pyproject.toml` 保留 `shopkeeper-brain` 命令，将目标改为 `app:main`。现有 uv 构建后端增加 `[tool.uv.build-backend]`，设置 `module-name = "app"`、`module-root = ""`。
- [x] 在 `workspace/verification/` 的副本运行语法/导入、`.env`、上传路径、真实本地 HTTP 页面及演示 SSE 检查。检查 `uv build --offline --wheel` 的产物含 `app`、HTML 及原 CLI 入口；不在验收中写正式数据库。

## 3. 运行文档与交付

- [x] 更新 `README.md`、`AGENTS.md` 和现行项目概览中的路径和启动方式；带练记录保留原口径。
- [x] 为用户提供 `docs/delivery/` 交付文档，列出审阅入口、实际检查结果和未运行项，以及新入口启动和真实手册问答回归的操作与预期。
- [x] 执行 `git diff --check`，核对迁移文件和文档范围；不执行 Git 写操作。
