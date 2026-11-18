# 第 12 节验收记录：RRF 融合与 Rerank 重排

2026-11-18 对用户手敲的真实源码做了首轮验收。章节状态只维护在 [学习进度](learning-progress.md)。

## 验收方式

- 读取用户四个源码文件（`core/rerank_config.py`、`utils/rerank_utils.py`、`node_rrf.py`、`node_rerank.py`），与教程副本逐行比对；复制 `src/` 和本地 `.env` 到 `workspace/verification/day12/formal-acceptance-20261118/project/`，CPython 3.11.15，`dashscope 2.1.0` 来自 `workspace/verification/day12/site/`。
- 用户在 IDE 运行的日志（用户确认）：配置、重排工具、RRF、重排节点、查询主图均退出码 0。重排工具三个分数 0.7853、0.1769、0.3860；RRF 融合 6 条，与教程副本的得分一致；重排节点三路检索 + RRF + 重排，待重排 11 条、保留 10 条，最高分 0.9530；主图拒答分支不进入检索，确认分支经 RRF（7 条）与重排（待重排 12 条、保留 10 条）后进入答案输出。

## 首轮发现

- **必须改**：`node_rerank.py` 第 7 行 `from workspace.verification.day11.site.win32.lib.win32con import CDN_SHAREVIOLATION` 是 IDE 自动补全的错误导入，指向被 Git 忽略的实验目录，而且 `CDN_SHAREVIOLATION` 在文件里没有使用。IDE 能运行，是因为 PyCharm 把项目根放进了模块路径；脱离 IDE（隔离副本）导入该文件直接 `ModuleNotFoundError: No module named 'workspace'`。同类问题第 11 节出现过。删除该行即可。
- 建议改：`_step_1_merge_docs()` 里 `"title": chunk.get("item_name")` 和 `page.get("title")` 缺 `or ""`，值为 `None` 时学习期入口的 `doc['title'][:20]` 会抛 `TypeError`；真实数据里这两个字段都有值，所以没暴露。另外“Chunk 里没有标题字段，用所属商品名代替。”这行注释被放到了联网结果的 `title` 上方，应在本地 Chunk 的 `title` 上方。
- 可选：`rerank_utils.py`、`node_rrf.py` 与教程相比只有标点、空行、docstring 缩进的差异，行为相同；`node_rerank.py` 的常量改名为 `RERANK_MIN_TOP_K`、`RERANK_MAX_TOP_K`，行为相同。

## 代理亲验（隔离副本）

- 编译通过；用户文件原样导入 `node_rerank` 失败（上面的必须改项）。
- 在副本里仅删除该导入行后，25 项边界探针通过：RRF 空字段、畸形项、公式值、权重、同分稳定；文档合并；契约抛 `StateFieldError`；无文档不调用服务；断崖截断（常量名换成用户的）；降级路径（用故意写错的密钥触发，只保留本地、顺序不变、分数为 `None`）。探针里的降级项在有真实密钥时会走正常重排，所以必须用无效密钥触发。
- 真实百炼：用户代码的 `rerank_documents` 三个分数与用户日志完全一致（0.7853、0.1769、0.3860）。
- 破坏性实验（副本）：把分数按“返回顺序”而不是 `index` 放回后，猪脚饭和电阻两句的分数互换（0.3860 对猪脚饭、0.1769 对电阻），说明按 `index` 放回是必须的；恢复后文件哈希一致。

## 复验（2026-11-18）

- 用户删除了错误导入，并补上 `title` 的 `or ""` 和注释位置。重新读取真实文件：四个文件与教程副本相比只剩标点、空行、docstring 缩进、常量名 `RERANK_MIN_TOP_K`/`RERANK_MAX_TOP_K` 的差异，行为相同；扫描 `src/` 没有 `workspace.` 形式的导入（剩下的 `workspace` 只是路径字符串，来自更早章节的学习期入口）。
- 复制到 `workspace/verification/day12/formal-acceptance-20261118-rerun/project/`：编译通过；`node_rerank` 原样导入成功；25 项探针全部通过（降级项用无效密钥触发）；真实运行重排节点入口：RRF 融合 6 条、待重排 11 条、保留 10 条，分数 0.9530 到 0.4386，与用户日志一致。
- 结论：没有必须修改项，第 12 节通过。

## 观察（不是缺陷）

- 用户日志里重排分数曲线平缓（0.953 → 0.439，相邻分差最大约 0.13，相对下降最大约 21%），断崖没有触发，保留到上限 10 条。联网结果这次基本相关（排在第 2、3、4、6 位的是同款万用表资料和一个示波器页），没有出现股票页，所以“重排挡掉无关联网页面”没有被这次运行直接证明。教程判据已按实际数据改成“保留 3 到 10 条，平缓时保留 10 条属正常”。
- 真实阈值（绝对 0.5、相对 0.25）在这份数据上偏宽松，是参考的默认值，本节不改。

## 跳过或未运行

- 修正后的用户源码没有重跑重排节点入口和主图，以用户日志和教程副本行为一致为据。
- 没有验证百炼限流、超长文档、500 条上限、`instruct` 的实际效果；没有自动化测试，测试条数记为无自动化测试。
