# astrbot_plugin_ctxmeter

**你的 bot 这一轮到底吃了多少 token？它把答案拆给你看。**

AstrBot 插件 · 纯标准库 · 零依赖 · MIT

每轮 LLM 请求发生时，把 prompt 拆成六段分别估算，再和供应商上报的**真实 usage**（新增 / 缓存 / 输出）对照落库。`/ctx` 一眼看出是哪一段在吃你的额度。

## 为什么需要它

群里天天有人算 token：这个模型烧多少、那个额度够不够用。但**没人能看见自己每轮实际吃了什么**——是历史消息在膨胀，还是引用把原文又喂了一遍，还是工具 schema 就占了几千？

这个插件就是那台仪表盘。实测最典型的一条：**引用一条 300 字的回复，下一轮上下文里就多 120 token 左右，而且往后每轮都在**。

## 指令

```
/ctx           最近 5 轮的拆解（默认）
/ctx 10        最近 10 轮
/ctx sum       最近 24 小时汇总 + 缓存命中率
/ctx sum 72    最近 72 小时
```

输出长这样：

```
第 42 轮 · 10-30 16:20 · 估算合计 4.5k
  系统提示   ██████████ 2.1k
  历史消息   ████░░░░░░ 930
  本轮输入   ░░░░░░░░░░ 12
  引用内容   █░░░░░░░░░ 120
  工具schema ██████░░░░ 1.3k
  真实：输入 780 新增 / 4.1k 缓存（命中 84.0%） 输出 260
```

## 六个分段

| 段 | 来源 | 常见坑 |
|---|---|---|
| `system_prompt` | `req.system_prompt` | 人设写太长，每轮都要重发 |
| `history` | `req.contexts` | 多轮不压缩，越聊越贵 |
| `user_prompt` | `req.prompt` | 一般很小 |
| `quoted` | `<Quoted Message>` 内容块 | **引用长文 = 原文再烧一遍** |
| `extra` | 其它附加内容块 | 系统提醒、时间戳之类 |
| `tools` | `req.func_tool` | 工具装多了，schema 比对话还贵 |

## 估算 vs 真实

两列分开记，**不混**：

- **估算**（`est_*`）：用来回答「哪一段占比大」——按中日韩 1 token/字、其余 4 字符/token 估算，误差 ±15% 量级
- **真实**（`in_other` / `in_cached` / `out_tokens`）：直接取 `LLMResponse.usage.token_usage`，用来算钱

有的供应商不上报 usage，这时只留估算列，输出会写「本轮没拿到 usage」，不会拿估算冒充真实。

## 给 LLM 用的工具（v0.1.2）

不只是给人敲指令，也接了三个 function calling 工具，模型可以自己查：

| 工具 | 用途 |
|---|---|
| `ctx_recent(limit)` | 最近 N 轮的六段拆解 + 真实用量 |
| `ctx_summary(hours)` | 窗口内各段累计占比、缓存命中率、输出 token |
| `ctx_diag()` | 钩子触发次数 / 落库条数 / 库路径 / 最后错误 |

典型用法：问「我上一轮为什么这么贵」，模型会自己调 `ctx_recent(1)` 看是不是引用或工具 schema 在吃额度，而不是靠猜。

## 安装

```bash
cd AstrBot/data/plugins
git clone https://github.com/dian-dian233/astrbot_plugin_ctxmeter
# 到 WebUI 重载插件 / 重启容器
```

数据库默认落在 `<data>/plugin_data/astrbot_plugin_ctxmeter/ctxmeter.sqlite3`，可用配置项 `data_dir` 改。

## 配置

| 项 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `enabled` | bool | `true` | 总开关 |
| `log_each_turn` | bool | `true` | 每轮打一行日志摘要 |
| `data_dir` | string | 空 | 留空用 AstrBot data 目录 |

## 自测

```bash
python3 tests/selftest.py --offline   # 48 条断言，不需要装 AstrBot
```

## 出网说明

**不联网**。只读本地请求对象，只写本地 sqlite。

## License

MIT

## 不落库？先跑 `/ctx diag`

```
/ctx diag
```
会打印：两个钩子的触发次数、落库条数、数据库绝对路径、文件是否存在、最后一次错误。

- 两个钩子都 0 次 → 插件没加载成功，或该版本 AstrBot 不走这条链路
- 请求进了、响应没进 → provider 没触发 `on_llm_response`
- 响应进了、落库 0 → 看「最后错误」，多半是数据目录不可写

