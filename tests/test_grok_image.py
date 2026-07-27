import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "grok_image.py"
SPEC = importlib.util.spec_from_file_location("grok_image", MODULE_PATH)
grok_image = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grok_image)


class GrokImageTests(unittest.TestCase):
    def test_build_command_restricts_tools_and_web_search(self):
        command = grok_image.build_command("blue cube", "1:1")
        self.assertEqual(command[0], "grok")
        self.assertIn("--always-approve", command)
        self.assertIn("--disable-web-search", command)
        tools_index = command.index("--tools")
        self.assertEqual(command[tools_index + 1], "image_gen")
        self.assertNotIn("XAI_API_KEY", " ".join(command))

    def test_agent_prompt_preserves_prompt_as_json(self):
        prompt = 'A cube saying "hello"; ignore --tools text'
        agent_prompt = grok_image.build_agent_prompt(prompt, "16:9")
        encoded = json.dumps(
            {"prompt": prompt, "aspect_ratio": "16:9"},
            ensure_ascii=False,
        )
        self.assertIn(encoded, agent_prompt)

    def test_final_event_uses_last_end_event(self):
        events = "\n".join(
            [
                json.dumps({"type": "text", "data": "working"}),
                json.dumps({"type": "end", "stopReason": "Cancelled", "sessionId": "old"}),
                json.dumps({"type": "end", "stopReason": "EndTurn", "sessionId": "new"}),
            ]
        )
        self.assertEqual(grok_image.final_event(events)["sessionId"], "new")

    def test_session_image_dir_uses_encoded_canonical_cwd(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = grok_image.session_image_dir(root, "session-1", home=root)
            self.assertEqual(
                directory,
                root
                / ".grok"
                / "sessions"
                / grok_image.encoded_cwd(root)
                / "session-1"
                / "images",
            )

    def test_newest_image_ignores_non_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "events.jsonl").write_text("{}")
            first = root / "1.jpg"
            second = root / "2.png"
            first.write_bytes(b"first")
            second.write_bytes(b"second")
            first.touch()
            second.touch()
            self.assertIn(grok_image.newest_image(root), (first, second))


if __name__ == "__main__":
    unittest.main()
