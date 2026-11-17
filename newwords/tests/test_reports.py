import hashlib
import json
import unittest
from pathlib import Path

import push_report

ROOT = Path(__file__).resolve().parents[1]
COUNTS = {
    "2026-11-09-1100": 22,
    "2026-11-09-1200": 24,
    "2026-11-09-1800": 24,
    "2026-11-10-0000": 25,
    "2026-11-10-0600": 25,
    "2026-11-10-1200": 25,
    "2026-11-10-1800": 25,
    "2026-11-11-0000": 25,
    "2026-11-11-0600": 26,
    "2026-11-11-1200": 26,
    "2026-11-11-1710": 0,
    "2026-11-11-1800": 1,
    "2026-11-12-0000": 0,
    "2026-11-14-1600": 0,
    "2026-11-14-2000": 0,
    "2026-11-15-0000": 0,
    "2026-11-16-2000": 0,
}
EMPTY_IDS = {
    "2026-11-11-1710",
    "2026-11-12-0000",
    "2026-11-14-1600",
    "2026-11-14-2000",
    "2026-11-15-0000",
    "2026-11-16-2000",
}
WORKER_SHA256 = {
    "worker/src/index.js": "0ebb46b0811c0de4dbb6ef1ef4c92cfddd5e89f4bab409454d70d4cf97a02660",
    "worker/wrangler.toml": "14d78b7c14cdb12729737e64c9161c02f5e4dc564490b6d272317fd15e433e5d",
}


class ReportCorpusTest(unittest.TestCase):
    def test_keyword_counts_ids_and_empty_rounds(self):
        paths = sorted((ROOT / "reports").glob("*.json"))
        self.assertEqual([path.stem for path in paths], sorted(COUNTS))
        saw_legacy_status = False
        created = []
        for path in paths:
            report = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.stem, report["report_id"])
            self.assertEqual(len(report["keywords"]), COUNTS[report["report_id"]])
            self.assertTrue(report["created_at"].endswith("+08:00"))
            created.append(report["created_at"])
            if report["report_id"] in EMPTY_IDS:
                self.assertEqual(report["keywords"], [])
                self.assertIn("本轮无新词", report["summary_md"])
            for keyword in report["keywords"]:
                if keyword.get("status") == "观察":
                    saw_legacy_status = True
            warnings = push_report.validate(report)
            self.assertIsInstance(warnings, list)
        self.assertTrue(saw_legacy_status)
        self.assertEqual(created, sorted(created))

    def test_worker_sources_are_unchanged(self):
        for rel, digest in WORKER_SHA256.items():
            data = (ROOT / rel).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest)
        text = (ROOT / "worker" / "wrangler.toml").read_text(encoding="utf-8")
        self.assertIn('name = "newwords"', text)
        self.assertIn('binding = "DATA"', text)
        self.assertIn('id = "f31770c4b7be477aa6842d42d66c1909"', text)
        self.assertIn('account_id = "92d5bc6038e714377091f4c7f05fee56"', text)  # pragma: allowlist secret
        self.assertNotIn("d1", text.lower())
        self.assertNotIn("preview_id", text)

    def test_wrangler_version_is_locked(self):
        package = json.loads((ROOT / "worker" / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(package["devDependencies"]["wrangler"], "4.163.0")
        lock = json.loads((ROOT / "worker" / "package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["packages"]["node_modules/wrangler"]["version"], "4.163.0")


if __name__ == "__main__":
    unittest.main()
