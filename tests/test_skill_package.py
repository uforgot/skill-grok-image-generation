import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SKILL = ROOT / "SKILL.md"
WRAPPER = ROOT / "scripts" / "grok_image.py"


class SkillPackageTests(unittest.TestCase):
    def test_skill_frontmatter_and_bundle_layout(self):
        text = SKILL.read_text()
        self.assertTrue(text.startswith("---\n"))
        frontmatter = text.split("---", 2)[1]
        self.assertIn("name: grok-image-generation", frontmatter)
        self.assertIn('description: "', frontmatter)
        self.assertTrue(WRAPPER.is_file())

    def test_skill_documents_fresh_generate_and_edit_commands(self):
        text = SKILL.read_text()
        self.assertIn(
            'python3 "<skill-dir>/scripts/grok_image.py" generate', text
        )
        self.assertIn('python3 "<skill-dir>/scripts/grok_image.py" edit', text)
        self.assertIn("--image ./input/cobalt-vase.jpg", text)
        self.assertIn("--timeout 180", text)

    def test_skill_has_explicit_provider_routing_and_fail_closed_policy(self):
        text = SKILL.read_text()
        self.assertIn("Explicit OpenClaw/native image provider", text)
        self.assertIn("Explicit Codex/OpenAI OAuth", text)
        self.assertIn("No provider preference", text)
        self.assertIn("Never fall back to another provider", text)
        self.assertIn("fallback_used: false", text)

    def test_skill_contains_no_machine_specific_install_path(self):
        text = SKILL.read_text()
        self.assertNotIn("/Users/", text)
        self.assertNotIn("~/.openclaw/", text)
        self.assertNotIn("~/.hermes/", text)


if __name__ == "__main__":
    unittest.main()
