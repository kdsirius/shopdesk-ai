# 第 4 节验收记录：Markdown 图片处理

- 验收日期：2026-11-13
- 用户真实代码：`src/shopkeeper_brain/processor/import_process/nodes/node_md_img.py`
- 第一轮隔离验收副本：`workspace/verification/day04/formal-acceptance-20261113/`
- 第二轮隔离验收副本：`workspace/verification/day04/formal-acceptance-20261113-rerun/`
- 破坏性实验副本：`workspace/verification/day04/formal-acceptance-20261113-destructive/` 和第二轮副本内的隔离实验
- 自动化测试：本节没有新增自动化测试文件；测试条数记为无自动化测试。

## 验收范围

本节按完整闭环验收：真实 Markdown 和图片扫描、VL 图片摘要、MinIO 上传、匿名只读策略、Markdown 图片引用替换、`_new.md` 保存、状态回写，以及失败边界。

## 隔离副本和环境

用户真实工程复制到 `workspace/verification/day04/formal-acceptance-20261113/`，没有复制 `.env` 和 `__pycache__`。第 3 节真实 Markdown 及 16 个图片文件复制到隔离输入目录。

- CPython 3.11.15：可用。
- `compileall`：通过。
- `uv sync`：失败，原因是当前 Windows 环境的 uv 在检查 managed Python 时报告“不受信任的装入点”（os error 448）；显式指定 CPython 3.11 后仍被同一环境问题拦截。该结果是环境限制，不归因于用户源码。

## 验证结果

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| 用户真实源码读取 | 通过 | 当前 `NodeMdImg` 的 MinIO 配置校验循环、策略位置和状态回写均已复核 |
| CPython 3.11.15 `compileall` | 通过 | 正式隔离副本退出码 0 |
| 模块导入 | 通过 | `NodeMdImg().name` 为 `node_md_img` |
| 状态隔离 | 通过 | 两个默认状态互不共享 `visited_nodes` |
| 真实 Markdown 输入 | 通过 | Markdown 存在、同级 `images/` 存在 |
| 图片筛选 | 通过 | 16 个图片文件，13 个被引用，3 个未引用 |
| 配置缺失边界 | 通过 | 缺少 `SHOPKEEPER_BRAIN_MINIO_ACCESS_KEY` 时抛出 `ConfigurationError`，没有提前创建 MinIO 客户端 |
| 真实 VL 调用 | 通过 | 13 次请求均返回 HTTP 200，节点正常完成 |
| MinIO 上传 | 通过 | `upload-images/万用表RS-12的使用/` 前缀下读取到 13 个对象 |
| MinIO 匿名访问 | 通过 | 图片 URL 返回 HTTP 200，Content-Type 为 `image/jpeg` |
| 新 Markdown 落盘 | 通过 | 隔离输入目录生成 `万用表RS-12的使用_new.md` |
| 状态与文件一致 | 通过 | `state["md_content"]` 与新 Markdown 文件内容一致 |
| 破坏性实验 | 通过 | 在隔离副本破坏 `state["md_content"]` 回写后，状态一致性探针按预期失败；实验副本已恢复 |
| 第一次最终 Markdown 图片摘要质量 | 失败 | 真实新 Markdown 有 7 行摘要混入 Markdown 代码围栏或嵌套图片标签 |
| 第二次最终 Markdown 图片摘要质量 | 通过 | 真实新 Markdown 有 13 个外层图片标签，0 个摘要污染 |

## 未通过项

`_summarize_image()` 当前只做：

```python
summary = str(response.content).strip().replace("\\n", "")
```

真实 VL 返回过包含 Markdown 结构的内容，例如：

````markdown
```markdown![RS PRO 品牌标志](images/...)```
````

节点随后把它直接放进外层图片 Alt 文本，最终生成类似：

````markdown
![```markdown![RS PRO 品牌标志](images/...)```](http://192.168.150.120:9000/...jpg)
````

本次真实输出中统计到 7 行存在代码围栏或嵌套 `![...]`。虽然外层图片 URL 可以返回 HTTP 200，但 Markdown 结构已经不稳定，不能把图片语义处理结果记为通过。

必须修改的方向是：在摘要进入 `_process_md_file()` 前，保证它是纯文本图片摘要，至少去掉模型返回的代码围栏、嵌套 Markdown 图片标签和换行；然后重新运行真实 VL/MinIO 验证，检查最终 Markdown 的每个图片 Alt 文本都是普通短文本。

## 复验：摘要清洗后

用户修正 `_clean_image_summary()` 和提示词后，重新使用真实 Markdown 执行了 VL/MinIO 流程。日志显示 13 次 VL 请求均返回 HTTP 200，随后生成新的 `_new.md`。

复验结果：

- 外层图片标签：13 个；
- 摘要污染：0 个；
- 代码围栏：0 个；
- 嵌套 `![...]`：0 个；
- 本地 `images/` 图片引用：0 个；
- 匿名图片访问：HTTP 200，`Content-Type=image/jpeg`；
- MinIO 文档前缀对象：13 个；
- 第二轮隔离副本 compileall、模块导入、本地真实输入探针和破坏性实验：通过。

第一次验收发现的摘要污染已被修正，第一次失败结果保留作为问题溯源记录。

## 结论

第 4 节状态更新为 `已通过`。通过范围包括：本地图片扫描、真实 VL 请求、MinIO 上传、匿名只读策略、Markdown 图片引用替换、摘要清洗、文件落盘、状态一致性、配置缺失边界和破坏性实验。

`uv sync` 仍受当前 Windows uv“不受信任的装入点”环境问题影响，但 CPython 3.11.15 编译、导入和真实业务验证均已完成。该环境限制不阻塞本节业务验收结论。
