import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS_INDEX = ROOT / "docs" / "README.md"
READINESS = ROOT / "docs" / "release-readiness.md"
LINK_PATTERN = re.compile(r"\[[^]]+\]\(([^)]+)\)")


class DocumentationTests(unittest.TestCase):
    def test_readme_has_install_usage_and_safety_sections(self):
        text = README.read_text(encoding="utf-8")
        for heading in (
            "## Install",
            "## Agent routing",
            "## Quick start",
            "## Output contract",
            "## Security and failure guarantees",
            "## Test",
            "## Limitations",
            "## Documentation",
        ):
            self.assertIn(heading, text)
        self.assertIn("openclaw skills install", text)
        self.assertIn("~/.hermes/skills/grok-image-generation", text)
        self.assertIn("fallback_used", text)

    def test_documentation_index_lists_every_final_document(self):
        text = DOCS_INDEX.read_text(encoding="utf-8")
        for name in (
            "interface-and-routing.md",
            "oauth-generation-baseline.md",
            "integration-openclaw-hermes.md",
            "openclaw-e2e-review.md",
            "fail-closed-errors.md",
            "release-readiness.md",
        ):
            self.assertIn(name, text)

    def test_local_markdown_links_resolve(self):
        files = [README, DOCS_INDEX, READINESS]
        for document in files:
            for target in LINK_PATTERN.findall(document.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "#")):
                    continue
                path = (document.parent / target.split("#", 1)[0]).resolve()
                self.assertTrue(path.exists(), f"missing link from {document}: {target}")

    def test_release_readiness_records_verified_state(self):
        text = READINESS.read_text(encoding="utf-8")
        self.assertIn("40 tests pass", text)
        self.assertIn("fallback_used: false", text)
        self.assertIn("#1131–#1140", text)
        self.assertIn("user approved finalization", text)


if __name__ == "__main__":
    unittest.main()
