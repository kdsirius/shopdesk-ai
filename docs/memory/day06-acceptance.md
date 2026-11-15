# 第 6 节验收记录：主体识别

- 验收日期：2026-11-15
- 用户真实实现：`src/shopkeeper_brain/processor/import_process/nodes/node_item_name_recognition.py`
- 配置与状态：`src/shopkeeper_brain/core/llm_config.py`、`src/shopkeeper_brain/processor/import_process/state.py`
- 原始验收副本：`workspace/verification/day06/formal-acceptance-20261115/project/`
- 第二轮副本：`workspace/verification/day06/formal-acceptance-20261115-rerun/project/`
- 最终定向复验副本：`workspace/verification/day06/formal-acceptance-20261115-final/project/`
- 自动化测试：没有新增项目测试文件，测试条数记为“无自动化测试”；本记录中的探针结果不充当 pytest 测试条数。

## 验收范围

从第 5 节真实 `chunks.json` 读取 `file_title` 和切片列表，取文档前 3 个 Chunk 构建最多 2500 字符的识别上下文，识别产品主体并回填 `state["item_name"]` 和全部 Chunk，保留名称内部空格、原正文与元数据。配置缺失或没有可用识别上下文时，以文件标题兜底。

本节不生成 BGE-M3 向量，不写 Milvus，不重跑前五节。读取真实输入不等于重新执行切片。

## 用户真实运行证据

用户在本轮会话提供了实际运行日志：

- 真实输入为 RS-12 使用说明书的 21 个 Chunk；
- 识别上下文为 1932 字符；
- OpenAI 兼容服务的 `/v1/responses` 请求返回 HTTP 200；
- 返回主体名称为 `RS PRO RS-12 数字万用表`；
- 程序退出码为 0。

以上属于用户提供的真实运行证据。代理本轮没有再次调用外部模型，没有把 SDK 消息对象的本地形状验证当成远程模型验证。用户日志取得时采用的是单文本块读取方式，最终修改的是客户端文本提取表达式；未对最终版本重新发起远程调用。

## 首轮问题与修正

1. 原教程把 `response.content` 转为字符串并删除所有空白，既会把内容块列表结构写入名称，也会破坏品牌与型号之间的空格。教程已修正。
2. 用户首先改成 `response.content[0].get('text').strip()`，当前单文本块返回正确，但字符串响应会报 `AttributeError`，前置非文本块也会失败，多文本块只取第一段。最终改为 `response.text.strip()`，统一提取正文并保留名称内部空格。
3. `SecretStr(os.getenv(...))` 在地址、模型存在而密钥变量缺失时，配置判断抛出 `TypeError: object of type 'NoneType' has no len()`。用户已补空字符串默认值：`SecretStr(os.getenv(..., ""))`。

第二轮真实保存文件已修正密钥问题，但名称提取仍是旧表达式，因此继续待验收。最终复验读取到真实保存的 `response.text.strip()` 后才完成该项验收。

## 隔离验证结果

| 验证项 | 结果 | 证据来源和范围 |
| --- | --- | --- |
| 按锁文件依赖同步 | 通过 | 首轮及第二轮 `uv sync --locked`实际执行；最终锁文件未变，复用第二轮环境 |
| 编译与模块导入 | 通过 | 首轮、第二轮 `compileall`通过；最终变更文件重新语法编译和导入通过 |
| 真实上下文 | 通过 | 21 个真实 Chunk 的前 3 个生成 1932 字符上下文 |
| 字符上限 | 通过 | 使用真实较长切片，返回长度截断到 2500 |
| 输入校验与状态隔离 | 通过 | 缺少标题、空列表、错误列表类型触发 `StateFieldError`；默认列表独立 |
| 空上下文兜底 | 通过 | 无模型请求，返回原文件标题 |
| 缺少全部配置、缺少密钥、空密钥 | 通过 | 修正后均能进入文件标题兜底；最终保留密钥修正并再次核对 |
| 字符串消息文本 | 通过 | 最终表达式对实际 SDK 的字符串 `AIMessage.content`提取正确 |
| 内容块列表 | 通过 | 单文本块、非文本块在前、多文本块拼接均正确 |
| 首尾空白与名称内部空格 | 通过 | 得到 `RS PRO RS-12 数字万用表`，品牌型号间空格保留 |
| 全部切片回填与原内容保留 | 通过 | 状态与 21 个 Chunk 的名称一致，既有正文与元数据不变 |
| 回填破坏性实验 | 通过 | 仅在首轮和第二轮副本移除逐块回填，探针因缺少 `item_name`按预期失败；原字节恢复后重新通过 |
| 用户源码与真实 JSON 保护 | 通过 | 最终比较 22 个保护文件哈希，本轮运行未修改源码、模板、锁文件或输入 |
| 真实远程识别 | 通过（用户日志） | 用户给出的 HTTP 200、实际产品名称与退出码 0；代理未重复调用 |
| 最终版本再次远程调用 | 未运行 | 不重复请求外部模型，保留此前用户真实证据与本地提取复验的区别 |
| BGE-M3、Milvus及其他前序外部服务 | 跳过 | 不属于第 6 节验收范围 |

环境使用 CPython 3.13.12，依赖包括 `langchain-core==1.7.7`、`langchain-openai==1.7.4`。本节没有另行复验 Python 3.11 最低声明版本。

## 最终变更与证据文件

最终保存版本相较第二轮只有名称提取表达式变化，配置、其他源码、依赖锁文件和真实输入均未变，因此最终定向复验剩余文本提取，同时保留前轮已通过证据。

- 首轮问题与通过项：`workspace/verification/day06/formal-acceptance-20261115/actual-review-results.json`；
- 第二轮密钥修复与剩余项：`workspace/verification/day06/formal-acceptance-20261115-rerun/actual-review-results.json`；
- 最终文本提取与回填：`workspace/verification/day06/formal-acceptance-20261115-final/final-results.json`。

## 结论

第 6 节已满足本节退出条件，没有剩余必须修改项。进度状态统一在 `learning-progress.md` 更新；用户自行提交 Git 后，再进行下一节接手，不在本次验收中提前备课。
