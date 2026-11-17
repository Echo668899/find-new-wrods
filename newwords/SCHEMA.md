# 新词监控报告 JSON Schema（扩展版：v1 字段 + 消费侧新增字段）

一份报告 = 一个 JSON 文件（UTF-8），放在 `reports/<report_id>.json`，用 `push_report.py` 推送。
**只有一套 schema**：沿用 v1 词库字段（名字和含义不变，网站和旧词条都在用），消费侧发现只**新增** 13 个字段。旧报告（没有新增字段）照常校验、照常渲染；新增字段有就显示。本仓库只保存已经公开的网站和正式报告，不包含发现流程原文。

**不进网站/KV 的东西**：发现过程、内部记录、个人账号。新条目的 `status` 不能是「观察」或「路径样本」。已经公开的旧词条若 `status` 为「观察」，校验只警告，不改词条。路径样本名单在 `path-samples.md`，只用于拦截，不能写进报告。

## 时间约定
- `report_id`、`created_at`、`title` 沿用**北京时间**：`report_id=YYYY-MM-DD-HHMM`，`created_at` 以 `+08:00` 结尾，标题里写“（北京时间）”。
- 其余所有时间（`t0`、`discovered_at`、`ingested_at`、`copy_evidence[].posted_at`）用 **UTC**，ISO 8601 以 `Z` 结尾。
- 看不到的写“未知”（字符串），不要估。

## 顶层字段
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| report_id | string | ✅ | `YYYY-MM-DD-HHMM`（北京时间），同 ID 重推覆盖 |
| created_at | string | ✅ | 北京时间 ISO 8601，如 `2026-11-11T18:00:00+08:00`（历史排序用） |
| title | string | ✅ | 如 `新词监控 第 11 期 · 2026-11-11 18:00（北京时间）` |
| summary_md | string | ✅ | 本期摘要；**无新词时写“本轮无新词”**（此时 `keywords` 可为空数组，这是合法报告）。简易 Markdown |
| trends_md / dropped_md / gaps_md | string | | 同 v1。不要写入发现过程、内部路径或个人账号 |
| watchlist_md | string | | 同 v1。若本地存在未入库的名单，推送时按其中的名字和别名拒绝 |
| sources | array<{name,url}> | | 数据源 |
| keywords | array<Keyword> | ✅ | 正式入库的词（推送时按 score 降序）。无新词时为空数组 |

## Keyword：沿用字段（含义以任务说明表格为准）
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| keyword | string | ✅ | 主词，保留原文 |
| cn_explain | string | ✅ | 格式描述：一两句中文，说清别人在照着做的是什么 |
| category | string | ✅ | 成片形态：`视频` / `图片` / `音频` / `游戏相关` / `其他`（五类对象写在 `format_class`，不写这里） |
| tool_type | string | ✅ | 做出结果要用哪类工具 |
| source_platform | string | ✅ | 首见入口（平台+用哪条检索） |
| source_url | string | ✅ | 那条链接 |
| first_seen | string | | 原帖时间（格式最早出现的时间；不是发现时间） |
| breakout_date | string | | 复制/讨论明显起量的日期；没到写 `尚未` |
| trend | string | ✅ | 刚冒头 / 上升 / 平稳 / 平稳高位 / 爆发后回落 / 下降（旧词条里的 `爆发` 仍可显示） |
| trend_evidence | string | | 热度证据（各写明什么时候看到的） |
| extra_links | array<string> | | 证据链接；**复制证据的链接也要放一份**（页面上只显示这里的链接） |
| user_need | string | ✅ | 用户想要什么结果，附提问原话和联想词 |
| general_ai_can_do | string | ✅ | `能` / `部分能` / `不能` |
| general_ai_reason | string | | 一句原因 |
| underlying_models | string | | 现有哪类模型/工作流能做、难点 |
| cost_estimate | string | | 单次成本 |
| difficulty | string | ✅ | `高` / `中` / `低` |
| competition | string | | 搜主词和“主词 AI”的结果、谁已经在做 |
| domain_taken | string | | 精确域名是否已建站 |
| domains | array<{domain,status}> | | 2–3 个候选域名；已注册的 status 以 `已注册` 开头（页面据此判断） |
| pay_potential | string | ✅ | `高` / `中` / `低`，和变现分一致 |
| pricing_model | string | | 建议收费方式 |
| score | number | ✅ | **10 分制 = 百分制总分 ÷ 10，保留 1 位小数**（页面排序/筛选/颜色用它） |
| risks | string | ✅ | 五类逐项写“有/未发现”：肖像、商标、原声、版权、平台政策；有的写具体对象，并补一句是玩法核心还是换掉仍成立 |
| risk_types | array<string> | | 写“有”的类别，取自 `肖像`/`商标`/`原声`/`版权`/`平台政策` |
| risk_level | string | | `高` / `中` / `低`（粗标，不影响判定和评分） |
| regions | string | | 在哪些语言、哪些国家传开（地区变体也记这里） |
| status | string | ✅ | 本轮首次入库 `新`，之后 `持续`；`过热` / `放弃` 沿用。**新条目不能使用 `观察` 或 `路径样本`；二者不写进网站词表** |

## Keyword：新增字段（有任何一个就必须全有 —— “消费侧新条目”）
| 字段 | 类型 | 说明 |
|---|---|---|
| aliases | array<string> | 歌名、人名、挑战名、模版名、标签，各语言（可空数组） |
| search_variants | array<{text,status}> | 预计搜索写法；`status` ∈ `已观察到` / `推测` |
| format_class | string | `足球庆祝与运动员` / `热歌钩子与跟跳` / `老片复活` / `街头 freestyle 和 dembow` / `一图换人与 CapCut 模版` / `其他` |
| t0 | string \| {earliest,latest} | 一个 UTC 时间点，或最早/最晚两端（时效按较早端算） |
| t0_basis | string | T0 依据 |
| discovered_at | string | 第一次看到它的时间（UTC） |
| ingested_at | string | 写入正式库的时间（UTC）；之后改名/更新都不改 |
| lag_hours | number | 入库 − T0，小时，1 位小数（推送时校验） |
| stage | string | `0–6 小时` / `6–12 小时` / `12–24 小时` / `24 小时以上`（推送时校验） |
| late | bool | 时效 > 24 小时为 `true`（推送时校验） |
| copy_evidence | array<{url,account,posted_at,data_seen}> | 至少两条独立复制；看不到的字段写“未知”。页面只显示 账号/时间/数据，链接看 `extra_links` |
| score_parts | object | `timing`/`heat`/`demand`/`competition`/`monetize`，各 `{score: 0–5, basis: 一句依据}`，另有 `total`（百分制 = 五项和×4）。`score` 必须等于 `total/10` |
| uncertainties | string \| array<string> | 没核实到的、互相矛盾的说法、“命名未定” |

旧词条的 `score` 没有分项，不批量重评；某个旧词条重新进入报告范围时再重评并补上新增字段。

## 校验（`python3 push_report.py reports/<id>.json --dry-run`）
- 所有条目：v1 必填字段、`score` 为 0–10 的数字。
- 报告：`report_id` 为 `YYYY-MM-DD-HHMM` 且与 `created_at`（须 `+08:00`）一致；`keywords` 为空时 `summary_md` 必须含“本轮无新词”。
- 新条目：新增字段齐全；枚举值（category/format_class/trend/status/risk_types/…）；时间为 UTC `Z`；`lag_hours`/`stage`/`late` 与 `t0`、`ingested_at` 一致；五项分 0–5 且有依据；`score_parts.total = 五项和×4`；`score = total/10`；`risks` 文字里五类都出现；`copy_evidence` 的链接都在 `extra_links` 里；T0 距报告超过 72 小时且趋势为平稳/回落/下降的不能进报告。
- 路径样本（`path-samples.md`）：`keyword`/`aliases` 命中会被拒绝；报告文字里提到会警告。
- `status` 为 `观察`/`路径样本`：新条目直接拒绝，旧格式条目警告。
- 警告（不拦截）：复制证据 <2 条、`timing` 分与时效锚点不同、发现偏晚、T0 超过 72 小时但趋势是上升（需在 `trend_evidence` 写明正在爆发）。

## 存储（Cloudflare Workers KV，namespace `newwords-data`，无 D1）
- `report:<report_id>` → 完整报告 JSON
- `index` → `[{report_id, created_at, title, n_keywords, top[5]}]`，按 created_at 倒序
- `latest` → 最新 report_id
- KV 里只有已发布报告。路径样本名单只留在仓库里做校验，不单独写入 KV。

## 发布安全（`push_report.py`）

- `--dry-run` 和 `--all --dry-run` 只做本地校验，不访问 Cloudflare。
- 真推送先校验全部文件，再读取 `index`、`latest` 以及每个将覆盖的 `report:<id>`。任一读取失败、空正文、或无法解析时停止，不写 KV。
- `latest` 已存在但 `index` 缺失，或 `latest` 指向的 id 不在 `index` 里：停止，避免用本地文件重写成残缺索引。
- 新 index 是远端 index 与本次报告的并集，按 `created_at` 倒序。不会删掉远端已有的 `report_id`。
- 远端某报告 `keywords` 非空，而本地同 id 的 `keywords` 为空：拒绝覆盖。
- 报告键按 `created_at` 从早到晚写入，成功后再写 `index`。`latest` 仅当本次最新 `created_at` 晚于远端 `latest` 时更新。
- 不调用删除接口，不使用 D1，不创建新的 namespace。
