import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {".git", "node_modules", ".wrangler", ".wrangler-dry-run", "__pycache__", ".pytest_cache"}
SKIP_FILES = {".gitignore"}
def _joined(*parts):
    return "".join(parts)


BAD = (
    _joined("echo", "_builds"),
    _joined("discover", ".py"),
    _joined("prompts_", "src"),
    _joined("raw", "/"),
    _joined("rounds", "/"),
    _joined("CLOUDFLARE_API_TOKEN", "="),
    _joined("-----BEGIN", " "),
)
POOL_NAME = _joined("pool", ".json")
OBSERVE_NAME = _joined("观察", "池")
BEARER_NAME = _joined("Bear", "er ")
POOL_OK = {"newwords/push_report.py", "newwords/README.md", ".gitignore"}
OBSERVE_OK = {"newwords/push_report.py"}
BEARER_OK = {"newwords/push_report.py"}


class PublicTreeTest(unittest.TestCase):
    def test_repo_does_not_publish_private_material(self):
        files = []
        for path in ROOT.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file() and path.name not in SKIP_FILES:
                files.append(path)
        self.assertTrue(files)
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                self.fail(f"unexpected binary file {rel}")
            if path.suffix == ".json" and "/reports/" in f"/{rel}":
                self.assertNotIn(OBSERVE_NAME, text, rel)
            lowered = text.lower()
            for snippet in BAD:
                self.assertNotIn(snippet.lower(), lowered, rel)
            if POOL_NAME in text:
                self.assertIn(rel, POOL_OK, rel)
            if OBSERVE_NAME in text:
                self.assertIn(rel, OBSERVE_OK, rel)
            if BEARER_NAME in text:
                self.assertIn(rel, BEARER_OK, rel)
        self.assertFalse(list((ROOT / "newwords").rglob(POOL_NAME)))
        self.assertFalse(list((ROOT / "newwords").rglob(_joined("library", ".json"))))
        self.assertFalse(list(ROOT.rglob(".env")))


if __name__ == "__main__":
    unittest.main()
