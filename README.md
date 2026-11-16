# shopkeeper-brain · 掌柜智库

面向产品手册和技术文档的 RAG 项目带练重建。以只读参考资料为依据，由用户手敲学习代码，AI 负责教程、审阅、隔离验收和文档维护。

章节状态、提交基线、验收范围和下一节门槛统一查看 [学习进度](docs/memory/learning-progress.md)。业务全景与实现边界见 [项目概览](docs/memory/project-overview.md)，协作规则见 [AGENTS.md](AGENTS.md)。

## 现有实现与运行入口

学习代码位于 [src/shopkeeper_brain](src/shopkeeper_brain/)，包括入口路由、PDF 转 Markdown、图片摘要与 MinIO 替换、文档切片、主体识别，以及 BGE-M3 名称和切片双向量化。真实验证的范围与限制见各节验收记录，最近的记录为 [第 7 节验收](docs/memory/day07-acceptance.md)。

当前主要通过各节点文件中的学习期 `__main__` 在 IDE 中运行。[main_graph.py](src/shopkeeper_brain/processor/import_process/main_graph.py) 目前提供入口后的路由函数；声明的命令行入口仍是脚手架问候，正式导入主图、HTTP 服务、检索与前端按学习进度逐节接入。

## 环境准备

- Python 声明为 `>=3.11`，工程选择见 [.python-version](.python-version)。实际验收解释器与依赖版本记录在对应验收文档中。
- 使用 uv 管理依赖，以 [pyproject.toml](pyproject.toml) 和 [uv.lock](uv.lock) 为准；默认 PyPI 源已配置为清华镜像。
- 本地配置参考 [.env.example](.env.example)，在自己的 `.env` 或环境变量中填写；不把有效密钥写进源码、模板或文档。

新环境同步依赖的操作模板如下，执行前按“未验证（未运行）”对待；安装完成只证明环境准备，业务通过仍以真实入口验证为准：

```bash
uv sync --locked --default-index https://pypi.tuna.tsinghua.edu.cn/simple
```

IDE 选择本工程 uv 解释器，具体输入、配置、运行位置与观察判据按对应教程执行。当前不设置项目 pytest 测试套件，也不把隔离行为探针当作 pytest 测试条数。

BGE-M3 的实际路线是 CPU/FP32，模型准备和配置见 [第 7 节教程](docs/study/day07-向量化与稀疏向量.md)。本地模型位于 `workspace/models/bge-m3/`；该目录及运行产物被 Git 忽略，新环境需要自行准备，不能把缓存目录名当作权重已经齐全。

## 文档与目录

| 入口 | 内容 |
| --- | --- |
| [学习教程](docs/study/) | 按业务顺序交付的手敲教程；固定讲法参照 [第 6 节](docs/study/day06-主体识别.md) |
| [学习进度](docs/memory/learning-progress.md) | 唯一章节状态源、提交与接手门槛 |
| [教学偏好](docs/memory/teaching-preferences.md) | IDE 真实验证、不使用子 agent 等长期约定 |
| [验收手册](docs/memory/verification-playbook.md) | AI 内部隔离验证与证据记录方式 |
| [规则与设计](docs/superpowers/) | 已确认设计和执行计划；带日期的文件记录当时决策 |
| [参考区规则](reference/AGENTS.md) | 原资料只读，按视频目录图片、课堂资料、补充笔记的顺序核对 |

`workspace/` 是唯一实验区，容纳模型、真实输入与输出、临时副本和验证日志，不作为需要提交的学习源码目录。参考项目的 `app/` 等目录不能替代本工程的实际包路径。

## 导入产物如何衔接

第 5 节原始 `chunks.json` 保留切片结果；第 6 节的 `item_name` 回填发生在内存中。第 7 节入口显式恢复主体标签并完成向量化，另存 `workspace/day07-real-run/state_vector.json`，包含名称双向量和全部 Chunk 的双向量；后续入库应从这份新状态衔接。

稀疏向量在内存中使用整数特征编号，JSON 对象键会变成字符串；读取备份后需恢复整数键。Dense 为 1024 维并做 L2 归一化，Sparse 保留模型原权重，不能照搬 Dense 的单位范数要求。

参考项目还包括 Milvus 持久化、检索、融合重排和 Web 交互等后续能力，其实现与验证按学习进度推进。安装了 PyMilvus 模型工具并不代表 Milvus 数据库已经验证。
