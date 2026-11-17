# 第 11 节验收记录：HyDE 与网络搜索

2026-11-17 对用户手敲的真实源码做了验收。章节状态只维护在 [学习进度](learning-progress.md)。

## 验收方式

- 读取用户真实源码，复制到 `workspace/verification/day11/formal-acceptance-20261117/project/`，CPython 3.11.15，`mcp 2.3.0`（用户虚拟环境已安装，`pyproject.toml` 新增 `mcp>=2.3.0`）。`tavily_config.py` 与教程副本逐行一致；`node_search_embedding_hyde.py` 与教程副本只有导入排列、docstring 缩进和一条日志位置（挪进 `_step_3_search`）的差异，行为相同。
- 用户在 IDE 运行两个节点学习期入口的日志：HyDE 召回 5 条，第一条“交流电压测量”评分 0.9044，一条仅 HyDE（“电阻测量”），其余与直接检索相同，退出码 0；联网搜索返回 5 条，保留 5 条，退出码 0（用户确认，与教程副本现象一致）。

## 首轮发现与复验

- 必须改（已修）：`node_web_search_mcp.py` 第 12 行被 IDE 自动导入成 `from workspace.verification.day11.site.mcp.client.streamable_http import streamable_http_client`，指向被 Git 忽略的实验目录，换机器或清理后会导入失败，并和虚拟环境里的 `mcp` 混用两份。已改为 `from mcp.client.streamable_http import streamable_http_client`；扫描 `src/` 已无 `workspace` 导入。
- 建议改（已修）：`_step_3_format_docs()` 里 `snippet` 缺 `.strip()`，纯空白正文会被保留；已补上，探针中“无正文”那条不再保留（4 条变为 3 条）。
- 复验：用户修订后的文件重新读取，除排版和尾逗号外与教程副本一致；用户重新运行入口日志与首轮相同。

## 代理亲验（隔离副本）

- 编译通过；真实 Tavily 返回 5 条；HyDE 与向量检索并排的入口在教程副本验证过三次（评分 0.9044 至 0.9100）。
- 输入契约：HyDE 缺 `rewritten_query`、空白问题、缺 `item_names`、空列表、含空字符串，网络节点缺或空白问题，均抛 `StateFieldError`；带引号反斜杠的名称 0 条不报错，不存在的产品 0 条，混合名称 5 条。
- 降级：Tavily 密钥无效（日志 `RuntimeError: Tavily 返回错误：401 ...`，返回空列表）、密钥为空，均降级；修订后重新验证通过。
- 格式化：空白正文、缺字段、非字典项、超长正文（截到 500 字）处理正确。
- 查询主图（教程副本，真实服务，MongoDB 临时库已删除）：拒答不进入检索，确认问题三路并行并汇合；这一项在用户源码副本上没有重复运行，因为行为代码与教程副本一致。
- 破坏性实验（教程副本）：HyDE 请求去掉 `expr` 后不存在的商品召回 5 条，恢复后文件哈希一致。

## 结论与建议

- 没有必须修改项，第 11 节通过。
- 联网搜索结果里混有股票页，这是 Tavily 对“RS”一词的搜索结果，每次有浮动，不是代码问题；相关性交给后面的重排。
- 用户 `.env.example` 里把 Tavily 地址写成了官方地址，代码空值也回落同一地址，两者一致。

## 跳过或未运行

- 用户源码副本没有重复运行主图与破坏性实验；以教程副本为证据，源码行为一致。
- 没有异步（FastAPI）环境、Tavily 限流和额度耗尽、长时间超时、多名称写法数据下的 HyDE 过滤验证。
- 没有自动化测试文件，测试条数记为无自动化测试。
