# 第 8 节 Milvus 向量入库设计

- 日期：2026-11-16
- 设计确认：用户已确认方案 A 并授权执行；本文保留当时设计，实际实现与验收见 [第 8 节验收记录](../../memory/day08-acceptance.md)，章节状态以 [学习进度](../../memory/learning-progress.md) 为准
- 适用章节：第 8 节“Milvus 向量入库”

## 1. 背景与目标

第 7 节已经使用真实 BGE-M3 完成主体名称和 21 个 Chunk 的 Dense/Sparse 双向量化，并将状态保存到：

`workspace/day07-real-run/state_vector.json`

第 8 节把这份已向量化状态写入 Milvus，完成两个集合的 Schema、索引、幂等清理、真实插入和 Chunk 主键回填。不会重新执行前七节的主体识别、切片或向量生成。

本节使用已经部署的 Milvus 服务：

- URI：`http://192.168.150.120:19530`
- 服务端：`pkg/v2.5.5`
- 客户端：`PyMilvus 3.0.3`
- 模型工具：`pymilvus-model 0.3.4`
- 设计起始时只读核对结果：Milvus 当时没有集合；后续真实入库及实验集合范围见验收记录，不将该起始快照作为当前环境

项目不自动部署、删除或重建 Docker/虚拟机服务，不触碰已有 MinIO 数据。

## 2. 已确认的方案

采用方案 A：保留主体名称保存和 Chunk 入库的职责边界。

```text
state_vector.json
        │
        ├── 主体名称保存步骤
        │       └── kb_item_names：1 条主体记录
        │
        └── Chunk 入库节点
                └── kb_chunks：21 条 Chunk 记录
```

主体保存属于主体识别节点的后续步骤，负责使用顶层主体字段保存名称数据；Chunk 入库使用独立节点，负责批量保存切片并回填 `chunk_id`。学习期入口按“主体保存 → Chunk 入库”顺序调用，但本节不接正式 LangGraph 主图。

不采用一个节点同时保存两类数据，也不增加暂时没有真实复用需求的 Repository/Service 抽象层。

## 3. 集合与字段设计

### 3.1 主体名称集合

集合名默认使用 `kb_item_names`，配置允许通过 `.env` 修改。

| 字段 | Milvus 类型 | 来源与用途 |
| --- | --- | --- |
| `pk` | `INT64`，自增主键 | Milvus 自动生成；当前不回填状态 |
| `file_title` | `VARCHAR` | 状态顶层 `file_title`，用于幂等清理 |
| `item_name` | `VARCHAR` | 状态顶层 `item_name` |
| `dense_vector` | `FLOAT_VECTOR(dim=1024)` | `item_name_dense_vector` |
| `sparse_vector` | `SPARSE_FLOAT_VECTOR` | `item_name_sparse_vector` |

主体保存步骤先校验名称和两个向量，再创建或复用集合，按 `file_title` 删除旧主体记录，最后插入当前主体记录。

参考资料同时出现过“按 `item_name` 或文件 ID 幂等”的概括，但实际参考代码按 `file_title` 删除。本项目采用实际代码行为：当前主体集合按 `file_title` 幂等。

### 3.2 Chunk 集合

集合名默认使用 `kb_chunks`，配置允许通过 `.env` 修改。

| 字段 | Milvus 类型 | 来源与用途 |
| --- | --- | --- |
| `chunk_id` | `INT64`，自增主键 | Milvus 返回后按原顺序回填 |
| `content` | `VARCHAR` | Chunk 的 `content` |
| `title` | `VARCHAR` | Chunk 的 `title` |
| `parent_title` | `VARCHAR` | Chunk 的 `parent_title` |
| `part` | `INT8` | 当前入库前补充为 `0` |
| `file_title` | `VARCHAR` | Chunk 的 `file_title`，用于幂等清理 |
| `item_name` | `VARCHAR` | Chunk 的 `item_name` |
| `dense_vector` | `FLOAT_VECTOR(dim=1024)` | Chunk 的 `dense_vector` |
| `sparse_vector` | `SPARSE_FLOAT_VECTOR` | Chunk 的 `sparse_vector` |

Chunk 入库节点校验全部切片后，按 `file_title` 删除当前文档的旧记录，再批量插入本次切片。Milvus 生成的 `chunk_id` 必须与插入返回的 ID 数量一致，并按返回顺序写回状态副本。

## 4. 索引与相似度

两个集合都为 Dense 和 Sparse 字段建立索引：

| 字段 | 索引类型 | 相似度 |
| --- | --- | --- |
| Dense | `AUTOINDEX` | `COSINE` |
| Sparse | `SPARSE_INVERTED_INDEX` | `IP` |

Sparse 索引沿用参考资料和 Milvus 文档中适用于 BGE-M3 的参数：

```text
inverted_index_algo = DAAT_MAXSCORE
normalize = True
quantization = none
```

选择 `AUTOINDEX` 而不是照搬参考主体集合的 `IVF_FLAT + nlist=128`，原因是当前服务端已确认是 Milvus 2.5.5，且两个参考代码快照对 Dense 索引写法并不一致。第 8 节以当前 PyMilvus API 和真实服务端实际接受的配置为准，不把旧版本参数当成固定契约。

需要区分：

- 第 7 节产生的 Dense 已做 L2 归一化，维度为 1024；
- 第 7 节产生的 Sparse 保留模型原始权重，没有宣称其已 L2 归一化；
- `normalize=True` 是 Milvus Sparse 索引侧配置，不改变 JSON 中保存的 Sparse 数据事实。

## 5. 输入衔接与类型恢复

唯一输入是第 7 节新状态备份，不使用第 5 节的旧 `chunks.json`：

`workspace/day07-real-run/state_vector.json`

已确认输入包含：

- 顶层 `item_name`；
- 顶层 `item_name_dense_vector`；
- 顶层 `item_name_sparse_vector`；
- 21 个带 `item_name`、`dense_vector` 和 `sparse_vector` 的 Chunk；
- 所有 Dense 向量为 1024 维；
- JSON 中 Sparse 字典的特征键为字符串。

入库适配层必须将主体 Sparse 和每个 Chunk Sparse 的键恢复为整数。不能把 `json.loads()` 得到的字符串键直接当作第 7 节内存对象的原始类型。名称内部空格 `RS PRO RS-12 数字万用表` 必须原样保留。

入库过程使用状态副本：

1. 读取 JSON；
2. 校验并转换待插入行；
3. 完成 Milvus 删除和插入；
4. 只有在对应插入成功、返回 ID 数量正确时才回填副本；
5. 不覆盖原始 `state_vector.json`。

## 6. 幂等性与失败边界

### 6.1 正常重复运行

使用同一份真实状态重复运行时，目标文档应保持：

- `kb_item_names` 中 1 条主体记录；
- `kb_chunks` 中 21 条 Chunk 记录。

不得因为重复运行累积为 2 条主体或 42 条 Chunk。删除过滤条件只针对当前 `file_title`，不能影响其他文档。

本节不执行 `drop_collection`，不删除其他集合，不清空数据库。

### 6.2 输入失败

在连接和写入前拒绝：

- 状态文件不存在或不是 JSON；
- 顶层主体名称为空；
- 名称 Dense 不是 1024 维；
- 主体 Sparse 为空或键不能转换为非负整数；
- Chunk 列表为空或元素不是字典；
- Chunk 缺少正文、主体、Dense 或 Sparse；
- Chunk 主体与顶层主体不一致；
- Chunk Dense 维度不一致；
- Chunk Sparse 键无法恢复为整数。

### 6.3 外部服务失败

Milvus 连接失败、集合创建失败、删除失败、插入失败或返回 ID 数量不一致时，节点抛出带节点上下文的项目异常，不伪造成功状态。

删除和插入不是一个数据库事务。如果插入阶段失败，旧数据可能已经删除；本节会在教程中明确记录这个参考流程边界，不宣称具备事务回滚能力。

## 7. 代码边界

预计新增或修改的学习代码仅服务于以下职责：

- Milvus 连接配置读取；
- Milvus 客户端复用和过滤表达式转义；
- 主体名称集合创建、幂等删除和插入；
- Chunk 集合创建、幂等删除、批量插入和 `chunk_id` 回填；
- 从真实 `state_vector.json` 运行的学习期 `__main__`。

不在本节实现：

- 正式主图串接；
- Dense 检索、Sparse 检索和 Hybrid Search；
- 商品确认查询；
- RRF、Rerank、MongoDB；
- FastAPI、SSE、前端；
- MinIO 修复或重新验收；
- 假 Milvus、内存数据库或模拟模型。

第 7 节保留的两项非阻塞建议不属于本节范围：

- `dense_vector_width` 未使用导入；
- `get_beg_m3_ef` 拼写建议。

## 8. 真实验证设计

验证入口仍是实现文件中的学习期 `__main__`，使用真实 `state_vector.json` 和真实 Milvus 服务。

### 8.1 第一次运行

观察并确认：

1. 连接 URI 为配置的 `192.168.150.120:19530`，不输出密钥；
2. 两个集合创建或复用成功；
3. 两个集合都存在 Dense 和 Sparse 索引；
4. 主体记录插入 1 条；
5. Chunk 批量插入 21 条；
6. Chunk 返回 21 个自增主键并按原顺序回填；
7. 写入数据中的 Sparse 特征键为整数；
8. 原始 `state_vector.json` 未被覆盖。

### 8.2 第二次运行

同一输入再次运行，观察并确认：

1. 不重复创建已有集合；
2. 当前 `file_title` 的主体旧记录被清理后重新写入；
3. 当前 `file_title` 的 21 条旧 Chunk 被清理后重新写入；
4. 查询集合中当前文档仍为 1 条主体和 21 条 Chunk；
5. 没有出现 2 条主体或 42 条 Chunk。

### 8.3 失败定位

- 连接失败：检查虚拟机状态、`19530` 端口和 `.env` URI；
- 集合创建失败：检查服务端版本、字段名、向量维度和索引参数；
- Sparse 插入失败：先检查 JSON 键是否恢复为整数，以及权重是否为有限数；
- 删除失败：检查过滤表达式和 `file_title` 的引号转义；
- ID 回填失败：比较插入返回 ID 数量与输入 Chunk 数量；
- 重复数据：检查删除过滤条件是否使用了当前 `file_title`，以及是否误读第 5 节旧 JSON；
- MinIO 报错不属于本节 Milvus 验证，不用它替代 Milvus 结果。

## 9. 验收退出条件

第 8 节只有在以下事实均由真实运行观察到时，才可记录为通过：

- 主体名称集合真实创建并写入 1 条当前文档数据；
- Chunk 集合真实创建并写入 21 条当前文档数据；
- 两类 Dense/Sparse 字段映射正确；
- 两类索引真实存在且服务端接受配置；
- JSON Sparse 键恢复为整数后真实插入成功；
- Chunk 自增主键完整回填且顺序对应；
- 同一输入重复运行后没有重复记录；
- 原始状态备份和无关集合未被破坏。

如果只完成代码编译、客户端导入或集合 API 调用，而没有真实插入和重复运行观察，不记录为本节通过。
