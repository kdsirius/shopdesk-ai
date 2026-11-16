# 第 7 节资料与教程验证记录

本文件记录资料依据、设计取舍和教程副本验证事实。章节状态只维护在 [学习进度](learning-progress.md)；本记录不代表用户手敲代码验收。

## 接手与资料事实

- 2026-11-15 开始时 `git status --short` 无输出，最近提交为 `5621efc`、`5fa1814`、`65013d8`。第 1 至第 6 节沿用既有通过结论，不重新请求远程主体识别。
- 已读取根、文档区、参考区规则，项目概览、教学偏好、学习进度、第 6 节验收与教程，以及当前真实状态、主体节点、配置、依赖与环境模板。
- 资料读取顺序为 day07/day08 视频目录图片 → 两天课堂笔记和压缩包代码 → `1.笔记/` 主体识别与向量化主题补充资料。
- 已有实验区解压副本的所选源码逐字节与原 ZIP 核对一致，没有重新运行参考脚本。day07 ZIP SHA-256 为 `f5c4e74287a21711c30a8eb6b0a62aa52bc5b7a0af19039da6a796cf90f8e59e`；day08 为 `aea32611deda6462ecc371c30c9ee65fa5e929bc1d98ed6387e3c999956783c9`。

| 物理资料 | 实际范围与采用依据 |
| --- | --- |
| day07 四张视频目录图 | 共 28 项：课堂笔记、压缩包、CSR 图源和 25 个视频。03—23 讲向量、相似度、依赖、模型下载与配置、单例工具、CSR、L2；24—25 进入主体识别流程与前两步 |
| day07 `knowledge_base.zip` | `utils/embedding_utils.py` 已有模型复用、Dense 转列表、CSR 按行转字典；`node_bge_embedding.py` 仍是直接返回状态的占位 |
| day08 三张视频目录图 | 共 20 项：课堂笔记、压缩包和 18 个视频。02—09 完成主体识别、主体向量与保存，10—18 为 Chunk 向量化、数据组织及入库；第 10、18 项图片文字被截断，不补写不可见标题 |
| day08 `课堂笔记/08【掌柜智库】【导入】主体识别.md` 与同名节点源码 | 第 5 步单独编码商品名称，第 6 步保存名称数据；不把这份向量等同于正文向量 |
| day08 `课堂笔记/09【掌柜智库】【导入】向量化.md` 与 `node_bge_embedding.py` | 按批拼接主体与正文，为每个 Chunk 写双向量；笔记每批 5 条、源码每批 3 条，并非固定业务契约 |
| day08 `课堂笔记/10【掌柜智库】【导入】存入 Milvus.md` | 用于确认第 8 节边界：集合、索引、旧数据清理、插入与主键回填 |
| `1.笔记/08【掌柜智库】【导入】【节点5】主体识别.md`、`09【掌柜智库】【导入】【节点6】向量化.md` | 补充说明，不覆盖当天源码；“稀疏已归一化”等文字必须与真实实现区分 |

## 本节施工边界与输入衔接

本节教程为 [向量化与稀疏向量](../study/day07-向量化与稀疏向量.md)，继续使用第 6 节固定三块教学写法，由当前会话直接编写与验证，不使用子 agent。

- 共享模型工具接收文本列表、缓存一个 BGE-M3 实例，将 Dense 数组转换为列表，将 Sparse CSR 每行转换为整数特征编号字典，不承担 Chunk 拼接或数据库职责。
- 主体识别节点保留已通过的前四步，只在教程中指导新增 `_step_5_generate_vectors(item_name)`，并把结果存入 `item_name_dense_vector`、`item_name_sparse_vector` 两个状态字段。
- Chunk 节点编码 `item_name + 换行 + content`，每批 3 条，复制每个字典后增加 `dense_vector`、`sparse_vector`；全部成功才替换状态中的列表，保留原字段、数量和顺序。
- 名称与 Chunk 两个集合、索引和入库统一留在第 8 节。本节不启动或写入 Milvus，不遗漏名称向量，也不提前实施名称保存。
- 真实输入为第 5 节 RS-12 的 21 个 Chunk。重新读取确认全部没有 `item_name`，第 6 节只修改了内存状态，没有覆盖原 JSON。
- 学习期入口复用第 6 节已确认名称 `RS PRO RS-12 数字万用表`，显式调用已有回填方法重建状态，再单独执行新增名称向量步骤和 Chunk 节点。不把常量输入当作新的远程识别实测，名称内部空格保留。
- 输出另存新的 `workspace/day07-real-run/state_vector.json`。JSON 会把稀疏整数键变为字符串；第 8 节从备份恢复时，须在入库适配处把特征编号转回整数。

## 环境与参考实现修正依据

只读检查发现：根项目解释器实际为 CPython 3.11.15，系统默认 Python 为 3.12.9，另有 uv 管理的 3.12.13、3.13.12；不能沿用第 6 节隔离副本的 3.13.12 当作当前根环境。显卡为 GTX 1650、4 GB，驱动 576.02；机器约 24 GB 内存，检查时约 12 GB 空闲。原 BGE-M3 Hugging Face 缓存只有 `refs/main`，没有模型权重。

本节先采用 Windows CPU/FP32 路线，不安装 CUDA、torchvision 或 torchaudio。官方 uv PyTorch 文档确认 Windows PyPI wheel 为 CPU 版本；普通依赖从清华镜像安装。教程中模型从 ModelScope 下载到 workspace，排除未使用的 ONNX 权重和展示图片。

实际依赖环境位于 `workspace/verification/day07/tutorial-20261115/project/`：

| 包 | 实际安装版本 |
| --- | --- |
| Python | 3.11.15 |
| Torch | 2.15.0，`torch.version.cuda is None` |
| PyMilvus | 3.0.3 |
| pymilvus-model | 0.3.4 |
| FlagEmbedding | 1.3.5 |
| Transformers | 4.57.6 |
| PEFT / sentence-transformers | 0.21.3 / 5.7.0 |
| NumPy / SciPy | 2.4.6 / 1.17.1 |
| ModelScope / modelscope-hub | 1.40.3 / 0.7.1 |

已核对的三处实现事实：

1. `normalize_embeddings=True` 传入底层 FlagEmbedding；推理实现只对 Dense 和启用时的 ColBERT 做 L2，不对词汇 Sparse 归一化。模型工具只改变 CSR 的存储表示，保留原始稀疏权重，不能把补充笔记的“已归一化”照搬进教程。
2. FlagEmbedding 1.3.5 的 `passage_max_length` 默认是 512 Token，PyMilvus 包装器没有主动覆盖。真实分词器核对 21 块的长度为 16—816 Token，第 6 块为 816，确实超过默认上限；全部在 8192 内。教程明确传 `passage_max_length=8192`，避免本份真实文档的尾部被静默截断。分词器词表长度实测为 250002。
3. FlagEmbedding 读取两个投影头；缺少头文件时存在新建参数的分支。教程在加载前检查主权重、配置、分词器与两个头文件，避免把不完整模型目录当成正常推理准备完成。这不是对所有模型格式的通用兼容层，仅针对本节实际 PyTorch 仓库。

首轮依赖安装失败：本机 `LongPathsEnabled=0`，较深实验缓存中的 FlagEmbedding 源码路径已有 255 字符，wheel 构建继续增加路径后报 `could not create ... configuration_minicpm_reranker.py: No such file or directory`。将本轮缓存复制到实验区短路径 `workspace/u/`，保持依赖与安装命令不变后安装成功；没有修改系统注册表或根环境。该环境排障不写入学习教程。

官方接口交叉核对使用 Context7，并读取了实际安装包源码：

- [uv 与 PyTorch](https://docs.astral.sh/uv/guides/integration/pytorch/)
- [Milvus BGE-M3](https://milvus.io/docs/embed-with-bgm-m3.md)
- [ModelScope snapshot_download](https://github.com/modelscope/modelscope/blob/master/modelscope/hub/snapshot_download.py)

## 教程副本验证

实验入口为 `workspace/verification/day07/tutorial-20261115/`。只复制当前真实工程，抽取本节四个完整 Python 文件，并按教程定位应用状态、识别节点与模板增量；根学习源码没有代写。未新增项目测试文件，验证脚本不记为 pytest 测试条数。

| 验证项 | 结果 | 范围 |
| --- | --- | --- |
| 文档结构、完整文件标记与相对链接 | 通过 | 三个主板块、四个完整 Python 文件、五个相对链接、图后直接白话说明 |
| 累积副本增量应用 | 通过 | 新增类型与默认值、主体第 5 步导入/调用/方法、环境模板追加 |
| 清华源依赖安装 | 通过 | 短缓存路径下 `uv add` 实际退出码 0 |
| 源码编译、模型库与 FlagEmbedding 导入 | 通过 | 当前 CPython 3.11.15；没有把导入当成推理成功 |
| 真实分词器长度核对 | 通过 | 21 块，最大 816 Token，1 块超过 512，全部不超过 8192 |
| 新状态容器、输入校验 | 通过 | 两个新增默认容器独立；无效工具输入及缺少主体、空切片、错误切片类型、主体不一致、空正文均在模型调用前被拒绝 |
| 真实 BGE-M3 加载与复用 | 通过 | CPU、`torch.float32`；同一实例复用，正文上限 8192，实际最大输入 816 Token |
| CSR 独立行对应与归一化 | 通过 | 前 3 块实际 CSR 形状 `(3, 250002)`，401 个非零项；由 COO 坐标独立重建每行，与工具输出逐项一致，Dense 前后数值一致 |
| CSR 隔离破坏检查 | 通过 | 只在独立命名空间把行边界固定为第 0 行，继续使用真实模型；检查按预期报“CSR 第 1 行转换错误”，正常工具函数和源码未改动 |
| 名称与全部 21 块、原样学习期入口 | 通过 | 真实名称 Dense 为 1024 维、Sparse 有 8 项；21 块全部有 1024 维 Dense 和非空 Sparse，7 批完成，原字段、数量、顺序和内部空格保留 |
| 新备份与稀疏键序列化 | 通过 | 在副本的 workspace 生成新状态 JSON；JSON 键为字符串，恢复为整数后与原内存字典完全一致；原切片 JSON 哈希未变 |
| 根源码、前六节教程与输入保护 | 通过 | 完整实测结束后 32 个保护文件哈希仍一致 |
| 远程主体识别、前五节外部服务 | 跳过 | 不重复已通过章节 |
| GPU 推理、Milvus 入库 | 跳过 | 本节只验证 CPU；数据库操作属于第 8 节 |

真实权重已经下载到根实验区 `workspace/models/bge-m3/`，主权重为 2271145830 字节，六个必要文件检查通过；用户手敲时可直接复用该目录，不需要再次下载。模型依赖仅装在教程副本，根项目 uv 环境仍需用户按教程同步。

本轮运行中，前 3 块 Dense 的 L2 范数约为 1.00000004、0.99999999、0.99999993，Sparse 范数约为 1.26356、1.24627、1.19243，实测支持“只对 Dense 承诺单位范数，Sparse 保留模型原权重”的讲法。CSR `indptr` 为 `[0, 127, 234, 401]`，三行非零项数分别为 127、107、167。模型加载、对照编码、隔离破坏检查和原样入口共执行约 99 秒；实验进程用 4 个 CPU 线程，不修改教程计算精度或业务源码。

完整运行设置 Hugging Face 离线环境变量，模型从本地路径加载；没有再次请求文本识别模型。GPU 推理和 Milvus 操作没有运行，不把 CPU 编码当作数据库入库或 GPU 环境验收。

证据文件均在本轮实验目录：`document-check.json`、`environment-results.json`、`module-import-results.json`、`token-length-results.json`、`model-download-results.json`、`verification-results.json`、`dependency-install.log`、`model-download.log`、`real-model-verification.log`。本轮完整真实模型验证命令退出码为 0。

这只是教程代码的隔离验证。用户完成手敲和自测后，必须重新读取真实源码、复制到新的验收目录并验证，不能用本轮副本结果直接把章节标为已通过。
