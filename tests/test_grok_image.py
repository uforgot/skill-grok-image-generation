import hashlib
import importlib.util
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "grok_image.py"
SPEC = importlib.util.spec_from_file_location("grok_image", MODULE_PATH)
grok_image = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(grok_image)


def text_events(*chunks):
    return "\n".join(
        json.dumps({"type": "text", "data": chunk}) for chunk in chunks
    )


def source_for(root, cwd, session_id, name, content):
    directory = grok_image.session_image_dir(cwd, session_id, home=root)
    directory.mkdir(parents=True, exist_ok=True)
    source = directory / name
    source.write_bytes(content)
    return source


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
                text_events("working"),
                json.dumps({"type": "end", "stopReason": "Cancelled", "sessionId": "old"}),
                json.dumps({"type": "end", "stopReason": "EndTurn", "sessionId": "new"}),
            ]
        )
        self.assertEqual(grok_image.final_event(events)["sessionId"], "new")

    def test_event_image_path_reassembles_streamed_text(self):
        events = text_events("Saved `", "images", "/", "1", ".jpg", "`")
        self.assertEqual(
            grok_image.event_image_paths(events),
            [Path("images/1.jpg")],
        )

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

    def test_source_resolution_is_bound_to_event_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "repo"
            cwd.mkdir()
            expected = source_for(root, cwd, "session-a", "1.jpg", b"session-a")
            source_for(root, cwd, "session-b", "1.jpg", b"newer-session-b")
            events = text_events("Generated `images/1.jpg`")
            resolved = grok_image.resolve_source_image(
                cwd, "session-a", events, home=root
            )
            self.assertEqual(resolved, expected.resolve())

    def test_source_resolution_rejects_ambiguous_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "repo"
            cwd.mkdir()
            source_for(root, cwd, "session-a", "1.jpg", b"one")
            source_for(root, cwd, "session-a", "2.jpg", b"two")
            with self.assertRaises(grok_image.GenerationError):
                grok_image.resolve_source_image(
                    cwd, "session-a", text_events("done"), home=root
                )

    def test_copy_preserves_source_extension_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jpg"
            source.write_bytes(b"image-content")
            result = grok_image.copy_verified(
                source, root / "nested" / "requested.png"
            )
            output = Path(result["output"])
            self.assertEqual(output.name, "requested.jpg")
            self.assertEqual(output.read_bytes(), source.read_bytes())
            self.assertEqual(
                result["sha256"], hashlib.sha256(source.read_bytes()).hexdigest()
            )

    def test_sequential_session_copies_do_not_cross_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cwd = root / "repo"
            cwd.mkdir()
            outputs = root / "outputs"
            first = source_for(root, cwd, "session-1", "1.jpg", b"first")
            second = source_for(root, cwd, "session-2", "1.jpg", b"second")

            first_result = grok_image.copy_verified(first, outputs / "first")
            second_result = grok_image.copy_verified(second, outputs / "second")

            self.assertEqual(Path(first_result["output"]).read_bytes(), b"first")
            self.assertEqual(Path(second_result["output"]).read_bytes(), b"second")

    def test_concurrent_copies_are_atomic_and_isolated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources = []
            for index in range(8):
                source = root / f"source-{index}.jpg"
                source.write_bytes(bytes([index]) * (1024 + index))
                sources.append(source)

            def copy(index):
                return grok_image.copy_verified(
                    sources[index], root / "outputs" / f"result-{index}.png"
                )

            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(copy, range(8)))

            for index, result in enumerate(results):
                output = Path(result["output"])
                self.assertEqual(output.name, f"result-{index}.jpg")
                self.assertEqual(output.read_bytes(), sources[index].read_bytes())
            self.assertEqual(list((root / "outputs").glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
