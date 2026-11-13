# 第 3 节验收记录：PDF 转 Markdown 流程

- 验收日期：2026-11-13
- 用户真实代码：`src/shopkeeper_brain/processor/import_process/`
- 用户真实运行入口：`src/shopkeeper_brain/processor/import_process/nodes/node_pdf_to_md.py::__main__`
- 隔离验收副本：`workspace/verification/day03/user-project-rerun-20261113/`
- 自动化测试：本节没有新增自动化测试文件；测试条数记为无自动化测试。

## 用户真实 MinerU 验证

用户使用真实 PDF `万用表RS-12的使用.pdf` 运行成功，日志显示：

- 申请上传链接成功并获得 `batch_id=d462badd-171c-415d-8aea-2f5cf7532c01`；
- 状态经历 `waiting-file → pending → running → done`；
- 结果 ZIP 下载和解压成功；
- Markdown 已保存到 `workspace/day03-real-run/万用表RS-12的使用_5gatm6ph/extracted/万用表RS-12的使用.md`；
- `md_content` 字符数为 6617；
- 输出图片文件数为 16；
- 进程退出码为 0。

对用户真实输出目录做了只读复核：

- Markdown 文件存在且正文非空；
- Markdown 中识别出 13 个图片引用；
- 13 个图片引用全部能在 `extracted/images/` 下找到对应文件；
- 结果 ZIP、`full.md` 重命名后的 PDF 同名 Markdown、图片和 MinerU JSON 产物均存在。

## 隔离副本验收

从用户当前真实工程复制到 `workspace/verification/day03/user-project-rerun-20261113/`，不复制 `.env` 和 `__pycache__`，使用 CPython 3.12.9 与清华 PyPI 镜像同步依赖。

| 验证项 | 结果 | 证据 |
| --- | --- | --- |
| uv 依赖同步 | 通过 | Requests、python-dotenv 等依赖安装成功 |
| `compileall` | 通过 | 用户真实源码隔离副本退出码 0 |
| 模块导入 | 通过 | `NodePDFToMD().name` 为 `node_pdf_to_md` |
| 状态隔离 | 通过 | 一个状态追加 `visited_nodes` 后，第二个默认状态仍为空 |
| 真实 PDF 本地路径准备 | 通过 | `万用表RS-12的使用.pdf` 存在，输出目录创建成功 |
| 缺失 `file_dir` | 通过 | 抛出 `StateFieldError`，字段为 `file_dir` |
| 缺失 PDF | 通过 | 抛出 `FileProcessingError` |
| 缺失 MinerU 配置 | 通过 | 未发起网络请求并抛出 `ConfigurationError` |
| 真实 MinerU 上传、轮询、下载、回写 | 通过 | 用户真实日志和真实输出产物；本轮隔离副本未重复上传 |

## 审阅结论

没有发现本节范围内的必须修改项。`NodePDFToMD` 的真实主链路、状态契约、异常边界、轮询和结果产物均符合本节目标。

建议保留的后续观察项：

1. `__main__` 当前仍是学习期临时入口，后续接入正式主图或服务层后再迁移、删除或改为正式命令入口。
2. 当前成功验证覆盖“解析成功并落盘”的正向链路；没有验证 MinerU 长时间超时、网络中断后的重试、服务端返回损坏 ZIP 或 ZIP 缺少 `full.md`。
3. 首次使用 `hak180产品安全手册.pdf` 时，MinerU 返回 `retry limit reached (5 attempts), please replace the file`。只读检查发现该 PDF 带 `Standard V4 R4 128-bit RC4` 加密信息；更换未触发该问题的真实 PDF 后成功。因此该失败记录为输入 PDF/外部解析兼容性边界，不归因于本节代码。
4. 本次实际运行环境为 CPython 3.12.9，未在 Python 3.11 上复验；不影响本节真实成功结论，但保留为环境边界。

## 结论

第 3 节“PDF 转 Markdown 流程”按本节范围验收通过。通过范围是：真实 PDF 经 MinerU v4 上传、异步轮询、结果 ZIP 下载解压、Markdown 状态回写和图片资源保留。该结论不包含下一节图片理解、文档切片、模型调用或数据库入库。
