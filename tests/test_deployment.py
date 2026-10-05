"""公开部署完整性测试：入口、依赖、配置和敏感文件忽略规则。"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent


class TestDeploymentReadiness(unittest.TestCase):
    def test_required_cloud_files_exist(self):
        required = [
            "app.py",
            "requirements.txt",
            ".streamlit/config.toml",
            "data/products.csv",
            "data/reviews.csv",
            "README.md",
            "LICENSE",
        ]
        missing = [path for path in required if not (ROOT / path).is_file()]
        self.assertEqual(missing, [])

    def test_runtime_dependencies_are_pinned_and_lightweight(self):
        lines = [
            line.strip() for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertTrue(all("==" in line for line in lines))
        self.assertFalse(any(line.lower().startswith("openai") for line in lines))
        self.assertIn("openai==2.48.0", (ROOT / "requirements-llm.txt").read_text(encoding="utf-8"))

    def test_secrets_and_local_artifacts_are_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for pattern in [".env", ".venv/", "output/", ".idea/"]:
            self.assertIn(pattern, ignore)


if __name__ == "__main__":
    unittest.main(verbosity=2)
