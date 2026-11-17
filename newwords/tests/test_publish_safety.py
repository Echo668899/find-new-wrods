import copy
import json
import os
import unittest
import urllib.request
from contextlib import redirect_stdout
from io import StringIO

import push_report


def report(rid, created, keywords, title="t"):
    return {
        "report_id": rid,
        "created_at": created,
        "title": title,
        "summary_md": "本轮无新词" if not keywords else "summary",
        "keywords": keywords,
    }


class MemoryKv:
    def __init__(self, store=None, fail_put_on=None, fail_get=False):
        self.store = dict(store or {})
        self.fail_put_on = fail_put_on
        self.fail_get = fail_get
        self.puts = []

    def get_text(self, key):
        if self.fail_get:
            raise push_report.PublishError("read failed")
        return self.store.get(key)

    def put_text(self, key, body):
        self.puts.append(key)
        if self.fail_put_on is not None and len(self.puts) == self.fail_put_on:
            raise RuntimeError("simulated failure")
        self.store[key] = body


class PublishSafetyTest(unittest.TestCase):
    def test_live_index_moves_forward_and_rerun_is_stable(self):
        reports = load_validated_reports()
        live = [item for item in reports if item["report_id"] <= "2026-11-12-0000"]
        self.assertEqual(len(live), 13)
        remote_index = [push_report.index_entry(item) for item in live]
        bodies = {item["report_id"]: copy.deepcopy(item) for item in live}
        plan = push_report.build_publish_plan(reports, remote_index, "2026-11-12-0000", bodies)
        self.assertEqual(plan["latest"], "2026-11-16-2000")
        self.assertTrue(plan["latest_changed"])
        keys = [item["key"] for item in plan["writes"]]
        self.assertEqual(keys[0], "report:2026-11-09-1100")
        self.assertEqual(keys[-2], "index")
        self.assertEqual(keys[-1], "latest")
        self.assertEqual(keys[-1], "latest")
        index = json.loads(plan["writes"][-2]["body"])
        self.assertEqual(len(index), 17)
        self.assertEqual(index[0]["report_id"], "2026-11-16-2000")
        self.assertEqual({item["report_id"] for item in index}, {item["report_id"] for item in reports})
        for item in live:
            written = json.loads(next(entry["body"] for entry in plan["writes"] if entry["key"] == "report:" + item["report_id"]))
            self.assertEqual([keyword["keyword"] for keyword in written["keywords"]], [keyword["keyword"] for keyword in item["keywords"]])

        stored = {item["report_id"]: json.loads(entry["body"]) for entry in plan["writes"] if entry["key"].startswith("report:")}
        rerun = push_report.build_publish_plan(reports, index, plan["latest"], stored)
        self.assertEqual(rerun["latest"], "2026-11-16-2000")
        self.assertFalse(rerun["latest_changed"])
        self.assertNotIn("latest", [item["key"] for item in rerun["writes"]])
        self.assertEqual(len(json.loads(next(item["body"] for item in rerun["writes"] if item["key"] == "index"))), 17)

    def test_older_publish_does_not_roll_latest_back(self):
        remote_index = [{
            "report_id": "2026-11-20-0000",
            "created_at": "2026-11-20T00:00:00+08:00",
            "title": "future",
            "n_keywords": 3,
            "top": ["a", "b", "c"],
        }]
        local = [report("2026-11-16-2000", "2026-11-16T20:00:00+08:00", [])]
        plan = push_report.build_publish_plan(local, remote_index, "2026-11-20-0000", {"2026-11-16-2000": None})
        self.assertEqual(plan["latest"], "2026-11-20-0000")
        self.assertFalse(plan["latest_changed"])
        index = json.loads(next(item["body"] for item in plan["writes"] if item["key"] == "index"))
        self.assertEqual(index[0]["report_id"], "2026-11-20-0000")
        self.assertEqual(index[0]["n_keywords"], 3)
        self.assertEqual({item["report_id"] for item in index}, {"2026-11-20-0000", "2026-11-16-2000"})
        self.assertNotIn("report:2026-11-20-0000", [item["key"] for item in plan["writes"]])

    def test_empty_keywords_cannot_replace_existing_terms(self):
        remote_index = [push_report.index_entry(report("2026-11-09-1100", "2026-11-09T11:00:00+08:00", [{"keyword": "kept"}], "第 1 期"))]
        local = [report("2026-11-09-1100", "2026-11-09T11:00:00+08:00", [])]
        with self.assertRaises(push_report.PublishError):
            push_report.build_publish_plan(
                local,
                remote_index,
                "2026-11-09-1100",
                {"2026-11-09-1100": {"keywords": [{"keyword": "kept"}]}},
            )

    def test_empty_keywords_can_add_a_new_report(self):
        local = [report("2026-11-14-1600", "2026-11-14T16:00:00+08:00", [])]
        plan = push_report.build_publish_plan(local, [], None, {"2026-11-14-1600": None})
        self.assertEqual(plan["latest"], "2026-11-14-1600")
        self.assertTrue(plan["latest_changed"])
        self.assertEqual(json.loads(next(item["body"] for item in plan["writes"] if item["key"].startswith("report:")))["keywords"], [])

    def test_missing_index_with_existing_latest_is_refused(self):
        local = [report("2026-11-09-1100", "2026-11-09T11:00:00+08:00", [{"keyword": "kept"}])]
        with self.assertRaises(push_report.PublishError):
            push_report.build_publish_plan(local, None, "2026-11-12-0000", {"2026-11-09-1100": None})

    def test_read_failure_writes_nothing(self):
        kv = MemoryKv(fail_get=True)
        local = [report("2026-11-14-1600", "2026-11-14T16:00:00+08:00", [])]
        with self.assertRaises(push_report.PublishError):
            push_report.publish_validated(local, kv.get_text, kv.put_text)
        self.assertEqual(kv.puts, [])
        self.assertEqual(kv.store, {})

    def test_failed_report_write_does_not_update_index_or_latest(self):
        kv = MemoryKv(fail_put_on=2)
        local = [
            report("2026-11-14-1600", "2026-11-14T16:00:00+08:00", []),
            report("2026-11-14-2000", "2026-11-14T20:00:00+08:00", []),
        ]
        with self.assertRaises(push_report.PublishError) as caught:
            push_report.publish_validated(local, kv.get_text, kv.put_text)
        self.assertIn("写入中断", str(caught.exception))
        self.assertIn("report:2026-11-14-1600", kv.store)
        self.assertNotIn("index", kv.store)
        self.assertNotIn("latest", kv.store)

    def test_empty_remote_body_is_refused_before_write(self):
        kv = MemoryKv({"index": "[]", "report:2026-11-14-1600": ""})
        local = [report("2026-11-14-1600", "2026-11-14T16:00:00+08:00", [])]
        with self.assertRaises(push_report.PublishError):
            push_report.publish_validated(local, kv.get_text, kv.put_text)
        self.assertEqual(kv.puts, [])

    def test_dry_run_and_missing_token_do_not_call_network(self):
        os.environ.pop("CLOUDFLARE_API_TOKEN", None)
        called = {"n": 0}

        def boom(*args, **kwargs):
            called["n"] += 1
            raise AssertionError("network")

        original = urllib.request.urlopen
        urllib.request.urlopen = boom
        try:
            with redirect_stdout(StringIO()) as stdout:
                result = push_report.main(["push_report.py", "--all", "--dry-run"])
                with self.assertRaises(SystemExit) as caught:
                    push_report.main(["push_report.py", "--all"])
            self.assertEqual(result, 0)
            self.assertIn("newest_local=2026-11-16-2000", stdout.getvalue())
            self.assertIn("CLOUDFLARE_API_TOKEN", str(caught.exception))
            self.assertEqual(called["n"], 0)
        finally:
            urllib.request.urlopen = original

    def test_forbidden_internal_text_fails_validation(self):
        bad = report("2026-11-01-0000", "2026-11-01T00:00:00+08:00", [])
        bad["summary_md"] = "本轮无新词 " + "raw" + "/counts.json"
        with self.assertRaises(AssertionError):
            push_report.validate(bad)


def load_validated_reports():
    paths = push_report.parse_args(["push_report.py", "--all"])[1]
    reports = []
    for path in paths:
        item = push_report.load_report(path)
        push_report.validate(item)
        reports.append(item)
    return reports


if __name__ == "__main__":
    unittest.main()
