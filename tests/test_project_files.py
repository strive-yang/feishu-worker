"""Public template consistency; does not inspect personal config or article state."""

import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DOCS = [
    ROOT / "README.md", ROOT / "AGENTS.md", ROOT / "TODO.md",
    ROOT / "docs/windows-setup.md", ROOT / "docs/security.md",
    ROOT / ".agents/skills/feishu-wechat-knowledge/SKILL.md",
]


class ProjectFileTests(unittest.TestCase):
    def test_local_document_links_exist(self):
        for document in PUBLIC_DOCS:
            text = document.read_text(encoding="utf-8")
            for link in re.findall(r"\]\(([^)]+)\)", text):
                if "://" in link or link.startswith("#"):
                    continue
                target = link.split("#", 1)[0]
                self.assertTrue((document.parent / target).exists(),
                                f"Broken local link in {document.relative_to(ROOT)}: {target}")

    def test_mit_license_and_package_metadata_agree(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License\n"))
        self.assertIn("Copyright (c)", license_text)
        self.assertIn("Permission is hereby granted, free of charge", license_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', license_text)
        for filename in ("package.json", "package-lock.json"):
            metadata = json.loads((ROOT / filename).read_text(encoding="utf-8"))
            root_package = metadata["packages"][""] if filename == "package-lock.json" else metadata
            self.assertEqual(root_package["license"], "MIT", filename)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("[MIT License](LICENSE)", readme)
        self.assertIn("第三方依赖遵循各自许可证", readme)

    def test_status_example_is_empty_and_not_premarked_successful(self):
        example = json.loads((ROOT / "article-status.example.json").read_text(encoding="utf-8"))
        self.assertEqual(example["index"]["document_url"], "")
        self.assertEqual(example["articles"], [])
        self.assertNotIn("status", example["index"])

    def test_public_examples_do_not_pin_personal_resources(self):
        examples = [ROOT / "config.conf.example", ROOT / ".codex/config.toml.example",
                    ROOT / "article-status.example.json"]
        for document in PUBLIC_DOCS + examples:
            text = document.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"https://[\w.-]+\.feishu\.cn/(?:wiki|docx)/[A-Za-z0-9]{15,}")
            self.assertNotRegex(text, r"[A-Za-z]:[/\\](?:Users|Desktop)[/\\]")
        config = (ROOT / "config.conf.example").read_text(encoding="utf-8")
        self.assertIn("APP_ID=cli_your_app_id", config)
        self.assertIn("APP_SECRET=your_app_secret", config)

    @unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "requires a Git checkout")
    def test_personal_files_are_ignored_even_if_index_needs_manual_cleanup(self):
        for relative in ("config.conf", "article-status.json", ".codex/config.toml", ".runtime/test.txt"):
            result = subprocess.run([shutil.which("git"), "check-ignore", "--no-index", relative],
                                    cwd=ROOT, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, f"Missing ignore rule: {relative}")
