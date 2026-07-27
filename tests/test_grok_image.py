import hashlib
import argparse
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


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

    def test_oauth_environment_removes_api_key(self):
        with patch.dict(os.environ, {"XAI_API_KEY": "must-not-pass"}):
            self.assertNotIn("XAI_API_KEY", grok_image.oauth_environment())

    def test_preflight_accepts_grok_com_login(self):
        completed = subprocess.CompletedProcess(
            ["grok", "models"],
            0,
            stdout="You are logged in with grok.com.\n",
            stderr="",
        )
        with patch.object(grok_image.shutil, "which", return_value="/bin/grok"), patch.object(
            grok_image, "run_command", return_value=completed
        ):
            grok_image.preflight_oauth(Path.cwd(), {}, 10)

    def test_preflight_rejects_expired_oauth(self):
        completed = subprocess.CompletedProcess(
            ["grok", "models"], 1, stdout="", stderr="Login required"
        )
        with patch.object(grok_image.shutil, "which", return_value="/bin/grok"), patch.object(
            grok_image, "run_command", return_value=completed
        ), self.assertRaises(grok_image.GenerationError) as raised:
            grok_image.preflight_oauth(Path.cwd(), {}, 10)
        self.assertEqual(raised.exception.code, "oauth_invalid")
        self.assertEqual(raised.exception.exit_code, 3)
        self.assertIn("grok login", raised.exception.next_action)

    def test_run_command_maps_timeout(self):
        with patch.object(
            grok_image.subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired(["grok"], 2),
        ), self.assertRaises(grok_image.GenerationError) as raised:
            grok_image.run_command(["grok"], Path.cwd(), {}, 2)
        self.assertEqual(raised.exception.code, "timeout")
        self.assertEqual(raised.exception.exit_code, 6)

    def test_generate_maps_permission_cancellation(self):
        cancelled = subprocess.CompletedProcess(
            ["grok"],
            0,
            stdout=json.dumps(
                {
                    "type": "end",
                    "stopReason": "Cancelled",
                    "sessionId": "session-1",
                }
            ),
            stderr="",
        )
        with tempfile.TemporaryDirectory() as tmp, patch.object(
            grok_image, "preflight_oauth"
        ), patch.object(grok_image, "run_command", return_value=cancelled):
            output = Path(tmp) / "must-not-exist.jpg"
            with self.assertRaises(grok_image.GenerationError) as raised:
                grok_image.generate("prompt", "1:1", output)
            self.assertEqual(raised.exception.code, "permission_cancelled")
            self.assertEqual(raised.exception.exit_code, 4)
            self.assertFalse(output.exists())

    def test_generate_maps_moderation_failure(self):
        blocked = subprocess.CompletedProcess(
            ["grok"], 1, stdout="", stderr="Request blocked by moderation"
        )
        with patch.object(grok_image, "preflight_oauth"), patch.object(
            grok_image, "run_command", return_value=blocked
        ), self.assertRaises(grok_image.GenerationError) as raised:
            grok_image.generate("prompt", "1:1", Path("unused.jpg"))
        self.assertEqual(raised.exception.code, "moderation_blocked")
        self.assertEqual(raised.exception.exit_code, 5)
        self.assertIn("우회", raised.exception.next_action)

    def test_generate_rejects_empty_response(self):
        empty = subprocess.CompletedProcess(
            ["grok"], 0, stdout=json.dumps({"type": "text", "data": ""}), stderr=""
        )
        with patch.object(grok_image, "preflight_oauth"), patch.object(
            grok_image, "run_command", return_value=empty
        ), self.assertRaises(grok_image.GenerationError) as raised:
            grok_image.generate("prompt", "1:1", Path("unused.jpg"))
        self.assertEqual(raised.exception.code, "empty_response")
        self.assertEqual(raised.exception.exit_code, 5)

    def test_missing_session_output_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp, self.assertRaises(
            grok_image.GenerationError
        ) as raised:
            root = Path(tmp)
            cwd = root / "repo"
            cwd.mkdir()
            grok_image.resolve_source_image(
                cwd, "empty-session", text_events("images/1.jpg"), home=root
            )
        self.assertEqual(raised.exception.code, "output_missing")
        self.assertEqual(raised.exception.exit_code, 7)

    def test_invalid_aspect_ratio_is_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError) as raised:
            grok_image.aspect_ratio("2:1")
        self.assertIn("지원하지 않는", str(raised.exception))

    def test_copy_failure_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jpg"
            source.write_bytes(b"content")
            destination_dir = root / "output"
            with patch.object(
                grok_image.shutil, "copyfile", side_effect=OSError("disk full")
            ), self.assertRaises(grok_image.GenerationError) as raised:
                grok_image.copy_verified(source, destination_dir / "result.jpg")
            self.assertEqual(raised.exception.code, "copy_failed")
            self.assertEqual(list(destination_dir.glob("*.tmp")), [])
            self.assertEqual(list(destination_dir.glob(".*.tmp")), [])
            self.assertFalse((destination_dir / "result.jpg").exists())

    def test_edit_command_uses_only_image_edit_and_absolute_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.jpg"
            prompt = "Change only the vase from blue to red"
            command = grok_image.build_edit_command(prompt, source)
            tools_index = command.index("--tools")
            self.assertEqual(command[tools_index + 1], "image_edit")
            self.assertIn("--always-approve", command)
            self.assertIn("--disable-web-search", command)
            agent_prompt = command[command.index("-p") + 1]
            self.assertIn(json.dumps(prompt), agent_prompt)
            self.assertIn(json.dumps(str(source.resolve())), agent_prompt)
            self.assertNotIn("aspect_ratio", agent_prompt)

    def test_edit_command_includes_explicit_aspect_ratio(self):
        command = grok_image.build_edit_command(
            "Extend the background", Path("source.png"), "16:9"
        )
        agent_prompt = command[command.index("-p") + 1]
        self.assertIn('"aspect_ratio": "16:9"', agent_prompt)

    def test_validate_source_image_checks_signature(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            valid = root / "valid.jpg"
            invalid = root / "invalid.jpg"
            valid.write_bytes(b"\xff\xd8\xff\xe0" + b"jpeg-data")
            invalid.write_bytes(b"not-an-image")
            self.assertEqual(grok_image.validate_source_image(valid), valid.resolve())
            with self.assertRaises(grok_image.GenerationError) as raised:
                grok_image.validate_source_image(invalid)
            self.assertEqual(raised.exception.code, "invalid_source")
            self.assertEqual(raised.exception.exit_code, 2)

    def test_edit_rejects_source_overwrite_before_provider_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.jpg"
            source.write_bytes(b"\xff\xd8\xff\xe0" + b"jpeg-data")
            with patch.object(grok_image, "execute_image_action") as execute, self.assertRaises(
                grok_image.GenerationError
            ) as raised:
                grok_image.edit_image("Make it red", source, source.with_suffix(".png"))
            self.assertEqual(raised.exception.code, "invalid_output")
            execute.assert_not_called()

    def test_edit_routes_valid_source_to_edit_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jpg"
            output = root / "result.jpg"
            source.write_bytes(b"\xff\xd8\xff\xe0" + b"jpeg-data")
            expected = {"ok": True, "action": "edit", "output": str(output)}
            with patch.object(
                grok_image, "execute_image_action", return_value=expected
            ) as execute:
                result = grok_image.edit_image(
                    "Change only the color", source, output, timeout=42
                )
            self.assertEqual(result, expected)
            action, command, requested, timeout = execute.call_args.args
            self.assertEqual(action, "edit")
            self.assertEqual(command[command.index("--tools") + 1], "image_edit")
            self.assertEqual(requested, output)
            self.assertEqual(timeout, 42)

    def test_parser_supports_edit_and_legacy_generate(self):
        edit_args = grok_image.parse_args(
            ["edit", "Make it blue", "--image", "source.jpg"]
        )
        legacy_args = grok_image.parse_args(["Generate a blue cube"])
        self.assertEqual(edit_args.action, "edit")
        self.assertIsNone(edit_args.aspect_ratio)
        self.assertEqual(legacy_args.action, "generate")
        self.assertEqual(legacy_args.aspect_ratio, "auto")

    def test_error_payload_reports_edit_action(self):
        failure = grok_image.error("test", "failed", "retry", 5)
        self.assertEqual(failure.payload("edit")["action"], "edit")


if __name__ == "__main__":
    unittest.main()
