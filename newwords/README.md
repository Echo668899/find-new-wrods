# 新词监控（newwords）

公开网站和正式报告的源码。发现监控仍在助手侧运行，不在这个仓库里。

- 网站：https://newwords.279135059.workers.dev
- API：`/api/latest`、`/api/reports`、`/api/report/<report_id>`
- Cloudflare 账号：`92d5bc6038e714377091f4c7f05fee56` <!-- pragma: allowlist secret -->
- Worker：`newwords`（`worker/`，绑定名 `DATA`）
- KV namespace：`newwords-data`，id `f31770c4b7be477aa6842d42d66c1909`
- 不使用 D1，也不创建新的 Cloudflare 资源

## 报告

`reports/*.json` 是正式报告，当前为第 1–17 期。第 14–17 期 `keywords` 为空，摘要写明「本轮无新词」。

第 9、10、11、13 期在放入仓库前去掉了内部路径、个人账号和内部名单暗示。`report_id`、`created_at` 和 `keywords` 没有改。第一次生产发布会按相同 id 覆盖这四份正文，不会删除其他报告，也不会把已有词条写成空列表。

校验（不访问网络，不需要 token）：

```bash
python3 push_report.py --all --dry-run
```

在 `newwords/` 目录执行。也可以只校验一份：`python3 push_report.py reports/<report_id>.json --dry-run`。

## 发布

GitHub Actions：

| Workflow | 何时运行 | 密钥 |
|---|---|---|
| `.github/workflows/ci.yml` | pull request | 不使用 |
| `.github/workflows/publish.yml` | 推送到默认分支 `main`，或在 `main` 上手动运行 | 仓库 Secret `CLOUDFLARE_API_TOKEN` |

发布步骤：先跑测试和 `--dry-run`，再部署现有 Worker，最后按 `created_at` 从早到晚把报告合并进现有 KV。

合并规则：

- 先读远端 `index`、`latest` 和将覆盖的报告。读失败或内容无法识别时不写。
- `index` 只合并。已有的 `report_id` 会保留，脚本不删除 KV 键。
- 空的 `keywords` 不能覆盖远端已经有词条的报告。新的「本轮无新词」报告可以新增。
- `latest` 只在新报告的 `created_at` 更晚时更新，不会回退。
- 同一 `report_id` 再推一次会覆盖该报告并重算索引，结果相同。

Token 只放在 GitHub 仓库 Secret `CLOUDFLARE_API_TOKEN`。不要写进仓库、日志或命令行参数。Workflow 只检查它是否已设置，不打印值。

这个 token 需要能更新现有 Worker `newwords`，并向现有 KV namespace 写入值。实用权限是同一账号上的 Workers Scripts Edit 和 Workers KV Storage Edit。不要授予 D1。账号范围限制在上面的 Cloudflare 账号。

仓库 Secret 对默认同仓库分支上的 workflow 可见。发布 workflow 只在 `main` 触发，PR workflow 不引用 Secret。请只把写权限给可信的人。若要挡住非 `main` 分支上被改过的 workflow，需要把 token 改成仅允许 `main` 部署的 GitHub Environment secret。当前按要求使用仓库 Secret。

本地真推送同样读取该环境变量：`python3 push_report.py --all`。可选覆盖 `CLOUDFLARE_ACCOUNT_ID` 和 `NEWWORDS_KV_ID`。

Worker 部署在 `worker/`：`npm ci` 后 `npx wrangler deploy --keep-vars`。`--keep-vars` 避免部署时清掉仪表盘里已有的明文变量；配置仍使用现有 `wrangler.toml`，不新建 KV。Wrangler 版本锁在 `worker/package-lock.json`。

当前线上索引停在第 13 期（`2026-11-12-0000`）。按 `created_at` 合并第 14–17 期后，`latest` 会前进到第 17 期（`2026-11-16-2000`）。第 17 期是「本轮无新词」，首页会显示这一期；更早的有词条报告仍留在历史列表里。

## 不会进入仓库的内容

发现脚本、原始抓取、内部轮次、个人账号和 API token 都不提交。`state/library.json` 与 `state/pool.json` 若出现在本地，会被 git 忽略。推送脚本在缺少 `state/pool.json` 时按空名单处理；若该文件存在，其中的主词和别名不能进入报告。成功的真推送会在该本地库文件已经存在时更新它，但不会把它上传到 KV 或 GitHub。

路径样本只在 `path-samples.md` 和 `state/path_samples.json`，用于校验。

## 测试

```bash
python3 -m unittest discover -s tests -t . -v
```

Python 3.12.3。Worker 工具链是 Node.js 22.23.4 与 Wrangler 4.163.0。
