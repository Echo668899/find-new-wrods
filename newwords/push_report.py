#!/usr/bin/env python3
"""校验并推送正式报告到现有 Cloudflare KV（namespace newwords-data）。

用法:
  python3 push_report.py reports/<id>.json [--dry-run]
  python3 push_report.py --all [--dry-run]

--dry-run 不访问网络，也不需要 CLOUDFLARE_API_TOKEN。
真推送只从环境变量读取该 token，不会打印它。
可选覆盖: CLOUDFLARE_ACCOUNT_ID, NEWWORDS_KV_ID。

写入顺序：先校验全部报告，再读取远端 index、latest 和将覆盖的报告。
读失败、index 与 latest 不一致、或空 keywords 将覆盖已有词条时，不写 KV。
index 只合并，不删除已有 report_id，也不删除报告键。
报告按 created_at 从早到晚写入，然后写 index；只有更晚的 created_at 才会更新 latest。
"""
import json, os, re, sys, datetime as dt, urllib.request, urllib.error, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ACCT = "92d5bc6038e714377091f4c7f05fee56"  # pragma: allowlist secret
DEFAULT_NS = "f31770c4b7be477aa6842d42d66c1909"
LIB = os.path.join(HERE, "state", "library.json")
POOL = os.path.join(HERE, "state", "pool.json")
PS_JSON = os.path.join(HERE, "state", "path_samples.json")

REQ_KW = ["keyword","cn_explain","category","tool_type","source_platform","source_url","trend","user_need",
          "general_ai_can_do","pay_potential","difficulty","score","risks","status"]
NEW_FIELDS = ["aliases","search_variants","format_class","t0","t0_basis","discovered_at","ingested_at","lag_hours",
              "stage","late","copy_evidence","score_parts","uncertainties"]
CATS = {"视频","图片","音频","游戏相关","其他"}
FORMAT_CLASSES = {"足球庆祝与运动员","热歌钩子与跟跳","老片复活","街头 freestyle 和 dembow","一图换人与 CapCut 模版","其他"}
TRENDS = {"刚冒头","上升","平稳","平稳高位","爆发后回落","下降","爆发"}   # “爆发”是旧词条用法，保留兼容
STATUSES = {"新","持续","过热","放弃"}
LMH = {"高","中","低"}
CAN = {"能","部分能","不能"}
RISK_TYPES = ["肖像","商标","原声","版权","平台政策"]
SCORE_KEYS = ["timing","heat","demand","competition","monetize"]
STAGES = ["0–6 小时","6–12 小时","12–24 小时","24 小时以上"]
NO_NEW = "本轮无新词"

def norm(s): return re.sub(r"[\W_]+", "", str(s).lower())
def pt(s, what, utc=False):
    s = str(s)
    try: t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception: raise AssertionError(f"{what} 不是 ISO 时间: {s!r}")
    if utc: assert s.endswith("Z") or s.endswith("+00:00"), f"{what} 必须是 UTC（以 Z 结尾）: {s!r}"
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
def jload(p, default):
    try:
        with open(p, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default

def path_sample_names():
    out = {}
    for c in jload(PS_JSON, {}).get("samples", []):
        for n in c["names"] + c["aliases"]: out[norm(n)] = c["name"]
    return out
def pool_names():
    out = {}
    for e in jload(POOL, {}).get("entries", []):
        for n in [e.get("keyword", "")] + list(e.get("aliases", [])):
            if len(norm(n)) >= 4: out[norm(n)] = e["keyword"]
    return out

def validate(r):
    warns = []
    for f in ["report_id","created_at","title","summary_md","keywords"]:
        assert f in r, f"missing report field {f}"
    assert isinstance(r["keywords"], list)
    # 北京时间约定
    m = re.fullmatch(r"(\d{4}-\d\d-\d\d)-(\d\d)(\d\d)", r["report_id"])
    assert m, "report_id 必须是 YYYY-MM-DD-HHMM（北京时间）"
    created = pt(r["created_at"], "created_at")
    assert r["created_at"].endswith("+08:00"), "created_at 必须沿用北京时间（以 +08:00 结尾）"
    assert created.strftime("%Y-%m-%d-%H%M") == r["report_id"], f"report_id 与 created_at 不一致（{created.strftime('%Y-%m-%d-%H%M')}）"
    if not r["keywords"]:
        assert NO_NEW in r["summary_md"], f"keywords 为空时 summary_md 必须写“{NO_NEW}”"
    assert str(r["summary_md"]).strip()
    ps = path_sample_names(); pools = pool_names()
    seen = set()
    for i, k in enumerate(r["keywords"]):
        miss = [f for f in REQ_KW if f not in k]
        assert not miss, f"keyword #{i} ({k.get('keyword')}) missing {miss}"
        nm = k["keyword"]
        assert nm not in seen, f"重复主词 {nm}"; seen.add(nm)
        assert isinstance(k["score"], (int, float)) and not isinstance(k["score"], bool) and 0 <= k["score"] <= 10, f"{nm}: score 必须是 0–10 的数字"
        k.setdefault("domains", []); k.setdefault("extra_links", [])
        new = [f for f in NEW_FIELDS if f in k]
        is_new = bool(new)
        for n in [nm] + list(k.get("aliases", [])):
            assert norm(n) not in ps, f"{nm}: “{n}” 是路径样本（{ps[norm(n)]}），不得写进报告"
            assert norm(n) not in pools, f"{nm}: “{n}” 在观察池里（{pools.get(norm(n))}），观察池不得进网站词表；转正请先从池里移除"
        if k["status"] in ("观察", "路径样本"):
            msg = f"{nm}: status={k['status']} 只能用于观察池/路径样本清单，不能写进网站词表"
            assert not is_new, msg
            warns.append(msg + "（旧格式条目，仅警告）")
        if not is_new: continue
        # ---- 消费侧新条目 ----
        miss = [f for f in NEW_FIELDS if f not in k]; assert not miss, f"{nm}: 新增字段不全，缺 {miss}"
        assert k["category"] in CATS, f"{nm}: category 必须是 {sorted(CATS)}（五类对象写 format_class）"
        assert k["format_class"] in FORMAT_CLASSES, f"{nm}: format_class 必须是 {sorted(FORMAT_CLASSES)}"
        assert k["trend"] in TRENDS, f"{nm}: trend 必须是 {sorted(TRENDS)}"
        assert k["status"] in STATUSES, f"{nm}: status 必须是 {sorted(STATUSES)}（观察/路径样本不进网站）"
        for f, allowed in (("difficulty", LMH), ("pay_potential", LMH), ("general_ai_can_do", CAN)):
            assert k[f] in allowed, f"{nm}: {f} 必须是 {sorted(allowed)}"
        if "risk_level" in k: assert k["risk_level"] in LMH, f"{nm}: risk_level 必须是 高/中/低"
        assert isinstance(k["aliases"], list)
        assert k["search_variants"], f"{nm}: search_variants 不能为空"
        for p in k["search_variants"]:
            assert p.get("text") and p.get("status") in ("已观察到","推测"), f"{nm}: search_variants 每条需 text 和 status(已观察到/推测)"
        for d in k["domains"]: assert d.get("domain") and d.get("status"), f"{nm}: domains 每条需 domain 和 status"
        for f in ("cn_explain","user_need","t0_basis"): assert str(k[f]).strip(), f"{nm}: {f} 不能为空"
        # 风险：五类
        rt = k.get("risk_types", [])
        assert set(rt) <= set(RISK_TYPES), f"{nm}: risk_types 只能取 {RISK_TYPES}"
        lacking = [t for t in RISK_TYPES if t not in k["risks"]]
        assert not lacking, f"{nm}: risks 文字里要对五类逐项写“有/未发现”，缺 {lacking}"
        if rt and not re.search(r"核心|换掉|可替换", k["risks"]):
            warns.append(f"{nm}: risks 里没看到“是玩法核心还是换掉仍成立”的一句")
        # 时间
        t0v = k["t0"]
        if isinstance(t0v, dict):
            assert t0v.get("earliest") and t0v.get("latest"), f"{nm}: t0 区间需 earliest 和 latest"
            t0 = pt(t0v["earliest"], f"{nm}.t0.earliest", True); pt(t0v["latest"], f"{nm}.t0.latest", True)
        else: t0 = pt(t0v, f"{nm}.t0", True)
        disc = pt(k["discovered_at"], f"{nm}.discovered_at", True); ing = pt(k["ingested_at"], f"{nm}.ingested_at", True)
        assert disc <= ing, f"{nm}: 发现时间晚于入库时间"
        h = (ing - t0).total_seconds() / 3600
        assert h >= -0.01, f"{nm}: 入库时间早于 T0"
        assert abs(k["lag_hours"] - h) <= 0.15, f"{nm}: lag_hours={k['lag_hours']} 与 入库−T0={h:.2f}h 不一致"
        stage = STAGES[0] if h <= 6 else STAGES[1] if h <= 12 else STAGES[2] if h <= 24 else STAGES[3]
        assert k["stage"] == stage, f"{nm}: stage 应为“{stage}”"
        assert bool(k["late"]) == (h > 24) and isinstance(k["late"], bool), f"{nm}: late 应为 {h > 24}"
        if k["late"]: warns.append(f"{nm}: 发现偏晚（{h:.1f}h）")
        # 证据
        ce = k["copy_evidence"]; assert isinstance(ce, list)
        for e in ce:
            assert e.get("url") and e.get("account"), f"{nm}: copy_evidence 每条需 url 和 account（posted_at/data_seen 看不到写“未知”）"
            assert e.get("posted_at") and e.get("data_seen"), f"{nm}: copy_evidence 的 posted_at/data_seen 不能空（看不到写“未知”）"
            assert e["url"] in k["extra_links"], f"{nm}: copy_evidence 的链接要在 extra_links 里放一份: {e['url']}"
        if len(ce) < 2: warns.append(f"{nm}: copy_evidence 只有 {len(ce)} 条（输出要求≥2；若靠媒体转载/模版/联想词满足判定第2条，请在 trend_evidence 写明）")
        # 评分
        P = k["score_parts"]; tot = 0
        for sk in SCORE_KEYS:
            assert sk in P, f"{nm}: score_parts 缺 {sk}"
            sc = P[sk].get("score"); b = str(P[sk].get("basis", "")).strip()
            assert isinstance(sc, (int, float)) and not isinstance(sc, bool) and 0 <= sc <= 5, f"{nm}: {sk} 分必须 0–5"
            assert b, f"{nm}: {sk} 必须写一句依据（没证据给 1 分并写缺什么）"
            tot += sc
        assert "total" in P and abs(P["total"] - tot * 4) < 1e-6, f"{nm}: score_parts.total 应为五项之和×4 = {tot*4}"
        assert abs(k["score"] - round(P["total"] / 10, 1)) < 1e-6, f"{nm}: score 应为 total/10 = {round(P['total']/10,1)}（10 分制，保留一位）"
        tanchor = 5 if h <= 6 else 4 if h <= 12 else 3 if h <= 24 else 2 if h <= 48 else 1 if h <= 72 else 0
        if P["timing"]["score"] != tanchor: warns.append(f"{nm}: timing 分 {P['timing']['score']} 与时效锚点 {tanchor}（{h:.1f}h）不同——确认是有意的")
        # 报告范围
        age_h = (created - t0).total_seconds() / 3600
        if age_h > 72:
            assert k["trend"] not in ("平稳","平稳高位","爆发后回落","下降"), f"{nm}: T0 距本报告 {age_h:.0f}h（>72h）且趋势“{k['trend']}”——走平/回落的留在库里，不进报告"
            warns.append(f"{nm}: T0 距本报告 {age_h:.0f}h（>72h），只有“过去 24h 仍明显加速”才该进报告——请在 trend_evidence 写明加速依据")
    r["keywords"].sort(key=lambda k: -k["score"])
    # 全文提到路径样本/观察池 → 警告
    body = json.dumps({x: r.get(x) for x in ("summary_md","trends_md","dropped_md","watchlist_md","gaps_md")}, ensure_ascii=False)
    nb = norm(body)
    for key, who in ps.items():
        if len(key) >= 6 and key in nb: warns.append(f"报告文字里出现路径样本“{who}”的名字——路径样本不得写进报告/举例")
    wl = norm(r.get("watchlist_md") or "")
    for key, who in pools.items():
        assert key not in wl, f"watchlist_md 里出现观察池条目“{who}”——观察池不得写进网站"
    assert_public_report(r)
    return warns


class PublishError(Exception):
    pass


def _joined(*parts):
    return "".join(parts)


def assert_public_report(report):
    raw = json.dumps(report, ensure_ascii=False)
    lowered = raw.lower()
    if _joined("echo", "_builds") in lowered:
        raise AssertionError("报告含有不该公开的个人账号")
    snippets = (
        _joined("raw", "/"),
        _joined("discover", ".py"),
        _joined("rounds", "/"),
        _joined("prompts_", "src"),
        _joined("pool", ".json"),
        _joined("library", ".json"),
        _joined("观察", "池"),
        "CLOUDFLARE_API_TOKEN",
    )
    for snippet in snippets:
        if snippet.lower() in lowered:
            raise AssertionError("报告含有不该公开的内部文本")


def index_entry(report):
    return {
        "report_id": report["report_id"],
        "created_at": report["created_at"],
        "title": report["title"],
        "n_keywords": len(report["keywords"]),
        "top": [item["keyword"] for item in report["keywords"][:5]],
    }


def created_key(entry):
    return pt(entry["created_at"], "created_at"), entry["report_id"]


def build_publish_plan(local_reports, remote_index, remote_latest, remote_bodies):
    """Plan KV writes. Raises PublishError before any write recommendation that could drop history."""
    if not local_reports:
        raise PublishError("没有可发布的报告，拒绝写入")
    ids = [report["report_id"] for report in local_reports]
    if len(ids) != len(set(ids)):
        raise PublishError("本地报告 report_id 重复，拒绝写入")

    index_missing = remote_index is None
    if index_missing:
        remote_index = []
    if not isinstance(remote_index, list):
        raise PublishError("index 不是数组，拒绝写入")
    seen = set()
    for entry in remote_index:
        if not isinstance(entry, dict) or "report_id" not in entry or "created_at" not in entry:
            raise PublishError("index 条目缺少 report_id 或 created_at，拒绝写入")
        if entry["report_id"] in seen:
            raise PublishError("index 含重复 report_id，拒绝写入")
        seen.add(entry["report_id"])
        pt(entry["created_at"], "index.created_at")
    if remote_latest and index_missing:
        raise PublishError("latest 已存在但 index 缺失，拒绝重写 index")
    if remote_latest and remote_latest not in seen:
        raise PublishError("latest 不在 index 中，拒绝写入")

    for report in local_reports:
        rid = report["report_id"]
        old = remote_bodies.get(rid)
        if old is None:
            continue
        if not isinstance(old, dict) or not isinstance(old.get("keywords"), list):
            raise PublishError(f"远端 report:{rid} 不是正式报告，拒绝覆盖")
        if old["keywords"] and not report["keywords"]:
            raise PublishError(f"{rid}: 拒绝用空 keywords 覆盖已有正式词条")

    merged = {entry["report_id"]: dict(entry) for entry in remote_index}
    for report in local_reports:
        merged[report["report_id"]] = index_entry(report)
    if any(entry["report_id"] not in merged for entry in remote_index):
        raise PublishError("合并后丢失已有报告，拒绝写入")

    new_index = sorted(merged.values(), key=created_key, reverse=True)
    if not new_index:
        raise PublishError("拒绝写入空 index")

    newest = new_index[0]
    newest_at = pt(newest["created_at"], "created_at")
    remote_at = None
    if remote_latest:
        remote_entry = next(entry for entry in remote_index if entry["report_id"] == remote_latest)
        remote_at = pt(remote_entry["created_at"], "created_at")
        chosen = newest["report_id"] if newest_at > remote_at else remote_latest
    else:
        chosen = newest["report_id"]
    changed = chosen != remote_latest
    if remote_latest and changed:
        chosen_entry = next(entry for entry in new_index if entry["report_id"] == chosen)
        if pt(chosen_entry["created_at"], "created_at") < remote_at:
            raise PublishError("拒绝把 latest 回退到更早的报告")

    writes = []
    ordered = sorted(local_reports, key=lambda report: (pt(report["created_at"], "created_at"), report["report_id"]))
    for report in ordered:
        body = json.dumps(report, ensure_ascii=False)
        if not body.strip() or body.strip() == "{}":
            raise PublishError(f"拒绝写入空报告 {report['report_id']}")
        writes.append({"key": "report:" + report["report_id"], "body": body})
    index_body = json.dumps(new_index, ensure_ascii=False)
    if not index_body.strip() or index_body.strip() == "[]":
        raise PublishError("拒绝写入空 index")
    writes.append({"key": "index", "body": index_body})
    if changed:
        if not chosen:
            raise PublishError("拒绝写入空 latest")
        writes.append({"key": "latest", "body": chosen})
    return {"writes": writes, "latest": chosen, "latest_changed": changed, "index_count": len(new_index)}


def read_remote(reports, get_text):
    index_raw = get_text("index")
    if index_raw is None:
        remote_index = None
    else:
        if not isinstance(index_raw, str) or index_raw.strip() == "":
            raise PublishError("index 为空，拒绝继续")
        try:
            remote_index = json.loads(index_raw)
        except json.JSONDecodeError:
            raise PublishError("index 不是 JSON，拒绝写入")
    latest_raw = get_text("latest")
    if latest_raw is None:
        remote_latest = None
    else:
        if not isinstance(latest_raw, str) or latest_raw.strip() == "" or latest_raw != latest_raw.strip():
            raise PublishError("latest 为空或格式异常，拒绝继续")
        if "\n" in latest_raw or latest_raw.startswith('"'):
            raise PublishError("latest 格式异常，拒绝写入")
        remote_latest = latest_raw
    bodies = {}
    for report in reports:
        rid = report["report_id"]
        key = "report:" + rid
        raw = get_text(key)
        if raw is None:
            bodies[rid] = None
            continue
        if not isinstance(raw, str) or raw.strip() == "":
            raise PublishError(f"{key} 为空，拒绝覆盖")
        try:
            bodies[rid] = json.loads(raw)
        except json.JSONDecodeError:
            raise PublishError(f"{key} 不是 JSON，拒绝覆盖")
    return remote_index, remote_latest, bodies


def publish_validated(reports, get_text, put_text):
    remote_index, remote_latest, remote_bodies = read_remote(reports, get_text)
    plan = build_publish_plan(reports, remote_index, remote_latest, remote_bodies)
    written = 0
    for item in plan["writes"]:
        try:
            put_text(item["key"], item["body"])
        except Exception:
            if written:
                raise PublishError(
                    "写入中断。已写入的报告键不会自动回滚；index 与 latest 只有在全部报告写入成功后才会更新。"
                    "重跑是幂等的，且不会把 latest 改到更早的报告。"
                ) from None
            raise
        written += 1
    return plan


def _cf_request(token, method, key, body=None):
    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID", DEFAULT_ACCT)
    ns = os.environ.get("NEWWORDS_KV_ID", DEFAULT_NS)
    url = (
        "https://api.cloudflare.com/client/v4/accounts/"
        + urllib.parse.quote(acct, safe="")
        + "/storage/kv/namespaces/"
        + urllib.parse.quote(ns, safe="")
        + "/values/"
        + urllib.parse.quote(key, safe="")
    )
    data = None if body is None else body.encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "text/plain; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read()
    except urllib.error.HTTPError as exc:
        exc.read()
        if method == "GET" and exc.code == 404:
            return None
        raise PublishError(f"KV {method} {key} failed: HTTP {exc.code}")
    except urllib.error.URLError:
        raise PublishError(f"KV {method} {key} failed: network")
    if method == "GET":
        if payload == b"":
            raise PublishError(f"KV GET {key} returned an empty body")
        return payload.decode("utf-8")
    return None


def cf_client():
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        raise PublishError("CLOUDFLARE_API_TOKEN not set")

    def get_text(key):
        return _cf_request(token, "GET", key)

    def put_text(key, body):
        if not isinstance(body, str) or body == "":
            raise PublishError(f"拒绝写入空值 {key}")
        _cf_request(token, "PUT", key, body)

    return get_text, put_text


def upsert_library(report):
    lib = jload(LIB, None)
    if not lib:
        return
    ents = lib["entries"]
    added = 0
    for keyword in report["keywords"]:
        if "ingested_at" not in keyword:
            continue
        existing = next((entry for entry in ents if entry["keyword"] == keyword["keyword"]), None)
        record = {
            "keyword": keyword["keyword"],
            "aliases": keyword["aliases"],
            "t0": keyword["t0"],
            "t0_basis": keyword["t0_basis"],
            "ingested_at": existing["ingested_at"] if existing else keyword["ingested_at"],
            "discovered_at": keyword["discovered_at"],
            "lag_hours": keyword["lag_hours"],
            "stage": keyword["stage"],
            "late": keyword["late"],
            "status": keyword["status"],
            "score": keyword["score"],
            "category": keyword["category"],
            "format_class": keyword["format_class"],
            "last_report_id": report["report_id"],
            "first_report_id": existing["first_report_id"] if existing else report["report_id"],
            "legacy": False,
            "related_to": keyword.get("related_to", []),
        }
        if existing:
            ents.remove(existing)
        else:
            added += 1
        ents.append(record)
    lib["updated_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    json.dump(lib, open(LIB, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"本地库已更新（新增 {added} 个条目；不推送）")


def parse_args(argv):
    dry = False
    positional = []
    for arg in argv[1:]:
        if arg == "--dry-run":
            dry = True
        elif arg == "--all":
            positional.append("--all")
        elif arg.startswith("-"):
            raise SystemExit(__doc__)
        else:
            positional.append(arg)
    if positional == ["--all"]:
        paths = sorted(os.path.join(HERE, "reports", name) for name in os.listdir(os.path.join(HERE, "reports")) if name.endswith(".json"))
        if not paths:
            raise SystemExit("reports/ 下没有 JSON")
        return dry, paths
    if len(positional) == 1:
        return dry, positional
    raise SystemExit(__doc__)


def load_report(path):
    try:
        with open(path, encoding="utf-8") as handle:
            report = json.load(handle)
    except OSError:
        raise SystemExit(f"无法读取报告文件: {os.path.basename(path)}")
    except json.JSONDecodeError:
        raise SystemExit(f"报告不是 JSON: {os.path.basename(path)}")
    if not isinstance(report, dict):
        raise SystemExit(f"报告不是 JSON 对象: {os.path.basename(path)}")
    stem = os.path.splitext(os.path.basename(path))[0]
    if stem != str(report.get("report_id", "")):
        raise SystemExit(f"文件名与 report_id 不一致: {os.path.basename(path)}")
    return report


def is_sample(report):
    return bool(report.get("_sample")) or str(report.get("report_id", "")).upper().startswith("SAMPLE")


def print_dry(reports):
    ordered = sorted(reports, key=lambda report: (pt(report["created_at"], "created_at"), report["report_id"]))
    for report in ordered:
        fresh = sum(1 for keyword in report["keywords"] if "ingested_at" in keyword)
        empty = "；本轮无新词" if not report["keywords"] else ""
        print(f"valid; would push {report['report_id']}; {len(report['keywords'])} keywords（其中消费侧新条目 {fresh}）{empty}")
    print(f"valid; {len(ordered)} reports; newest_local={ordered[-1]['report_id']}; dry-run 不访问 KV")


def main(argv=None):
    if argv is None:
        argv = sys.argv
    dry, paths = parse_args(argv)
    reports = [load_report(path) for path in paths]
    seen = set()
    for report in reports:
        rid = report.get("report_id")
        if rid in seen:
            raise SystemExit(f"重复的 report_id: {rid}")
        seen.add(rid)
        try:
            warnings = validate(report)
        except AssertionError as exc:
            raise SystemExit(f"校验失败 {report.get('report_id')}: {exc}")
        for warning in warnings:
            print("警告:", warning)
    if any(is_sample(report) for report in reports) and not dry:
        raise SystemExit("示例/测试报告（_sample）不能真推送，只能 --dry-run")
    if dry:
        print_dry(reports)
        return 0
    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        raise SystemExit("CLOUDFLARE_API_TOKEN not set")
    try:
        get_text, put_text = cf_client()
        plan = publish_validated(reports, get_text, put_text)
    except PublishError as exc:
        raise SystemExit(f"发布已停止: {exc}")
    for report in reports:
        upsert_library(report)
    print(
        f"pushed {len(reports)} reports; latest={plan['latest']}; "
        f"latest_changed={str(plan['latest_changed']).lower()}; index={plan['index_count']}"
    )
    return 0


if __name__ == "__main__":
    main()
