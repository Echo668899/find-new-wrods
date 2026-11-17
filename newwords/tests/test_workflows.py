import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
PINS = {
    "actions/checkout@fbc6f3992d24b796d5a048ff273f7fcc4a7b6c09",
    "actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444",
}


class WorkflowTest(unittest.TestCase):
    def test_ci_has_no_secrets_and_publish_is_main_only(self):
        ci = (WF / "ci.yml").read_text(encoding="utf-8")
        publish = (WF / "publish.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", ci)
        self.assertNotIn("secrets.", ci)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", ci)
        self.assertNotIn("pull_request_target", ci)
        self.assertNotIn("workflow_dispatch", ci)

        self.assertNotIn("pull_request", publish)
        self.assertNotIn("pull_request_target", publish)
        self.assertIn("workflow_dispatch:", publish)
        self.assertIn("branches:", publish)
        self.assertIn("- main", publish)
        self.assertIn("github.repository == 'Echo668899/find-new-wrods'", publish)
        self.assertIn("github.ref == 'refs/heads/main'", publish)
        self.assertIn("github.event.repository.default_branch == 'main'", publish)
        self.assertIn("cancel-in-progress: false", publish)
        self.assertIn("contents: read", publish)
        self.assertIn("persist-credentials: false", publish)
        self.assertIn("python3 push_report.py --all", publish)
        self.assertIn("npx wrangler deploy", publish)
        self.assertNotIn("wrangler kv namespace create", publish)
        self.assertNotIn("d1 ", publish.lower())
        for line in publish.splitlines():
            if "secrets." in line:
                self.assertIn("secrets.CLOUDFLARE_API_TOKEN", line)
                self.assertNotIn("echo", line.lower())

        for text in (ci, publish):
            for pin in PINS:
                self.assertIn(pin, text)
            self.assertIn('python-version: "3.12.3"', text)
            self.assertIn('node-version: "22.23.4"', text)
            self.assertNotIn("uses: actions/checkout@v", text)
            self.assertNotIn("uses: actions/setup-python@v", text)
            self.assertNotIn("uses: actions/setup-node@v", text)


if __name__ == "__main__":
    unittest.main()
