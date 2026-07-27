import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "scripts" / "grok_image.py"


class FailClosedCLITests(unittest.TestCase):
    def run_failure(self, mode, timeout=10):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            log = root / "calls.log"
            output = root / "must-not-exist.jpg"
            fake_grok = fake_bin / "grok"
            fake_grok.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    if [ "${XAI_API_KEY+x}" = "x" ]; then
                      echo "XAI_API_KEY_LEAKED" >> "$FAKE_GROK_LOG"
                    fi
                    printf '%s\\n' "$*" >> "$FAKE_GROK_LOG"
                    if [ "${1:-}" = "models" ]; then
                      if [ "$FAKE_GROK_MODE" = "oauth" ]; then
                        echo "Login required: OAuth expired" >&2
                        exit 1
                      fi
                      echo "You are logged in with grok.com."
                      exit 0
                    fi
                    case "$FAKE_GROK_MODE" in
                      permission)
                        printf '%s\\n' '{"type":"end","stopReason":"Cancelled","sessionId":"permission-test"}'
                        exit 0
                        ;;
                      timeout)
                        sleep 2
                        exit 0
                        ;;
                      moderation)
                        echo "Request blocked by moderation" >&2
                        exit 1
                        ;;
                    esac
                    echo "unexpected fake mode" >&2
                    exit 99
                    """
                ),
                encoding="utf-8",
            )
            fake_grok.chmod(0o700)
            env = os.environ.copy()
            env.update(
                {
                    "PATH": f"{fake_bin}{os.pathsep}{env['PATH']}",
                    "FAKE_GROK_MODE": mode,
                    "FAKE_GROK_LOG": str(log),
                    "XAI_API_KEY": "must-not-reach-child",
                }
            )
            process = subprocess.run(
                [
                    sys.executable,
                    str(WRAPPER),
                    "generate",
                    "A safe test image",
                    "--aspect-ratio",
                    "1:1",
                    "--output",
                    str(output),
                    "--timeout",
                    str(timeout),
                ],
                cwd=root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
            )
            payload = json.loads(process.stderr)
            calls = log.read_text(encoding="utf-8").splitlines()
            return process, payload, calls, output.exists()

    def test_required_failures_stop_without_provider_fallback(self):
        cases = {
            "oauth": (3, "oauth_invalid", "인증 만료", 1),
            "permission": (4, "permission_cancelled", "권한 취소", 2),
            "timeout": (6, "timeout", "timeout", 2),
            "moderation": (5, "moderation_blocked", "moderation", 2),
        }
        forbidden = ("image_generate", "codex", "api.x.ai", "XAI_API_KEY_LEAKED")

        for mode, (exit_code, error, reason, call_count) in cases.items():
            with self.subTest(mode=mode):
                process, payload, calls, output_exists = self.run_failure(
                    mode, timeout=1 if mode == "timeout" else 10
                )
                self.assertEqual(process.returncode, exit_code)
                self.assertEqual(process.stdout, "")
                self.assertEqual(payload["error"], error)
                self.assertFalse(payload["fallback_used"])
                self.assertFalse(output_exists)
                self.assertTrue(payload["next_action"])
                self.assertEqual(
                    payload["user_message"],
                    f"Grok OAuth 이미지 생성 실패 — 원인: {reason}. "
                    "자동 fallback은 실행하지 않았어. "
                    f"다음 행동: {payload['next_action']}",
                )
                self.assertEqual(len(calls), call_count)
                joined = "\n".join(calls)
                for token in forbidden:
                    self.assertNotIn(token, joined)
                if mode == "oauth":
                    self.assertEqual(calls, ["models"])
                else:
                    self.assertEqual(calls[0], "models")
                    self.assertIn("--tools image_gen", calls[1])
                    self.assertIn("--disable-web-search", calls[1])
                    self.assertIn("--always-approve", calls[1])

    def test_fresh_session_manifest_records_no_fallback(self):
        manifest = json.loads(
            (ROOT / "examples" / "fail-closed-1140-results.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["dudu_item"], 1140)
        self.assertEqual(
            set(manifest["cases"]),
            {"oauth_expired", "permission_cancelled", "timeout", "moderation"},
        )
        for result in manifest["cases"].values():
            self.assertFalse(result["fallback_used"])
            self.assertFalse(result["output_exists"])
            self.assertEqual(result["other_provider_calls"], 0)
            self.assertIn("자동 fallback은 실행하지 않았어", result["user_message"])
            self.assertIn("다음 행동:", result["user_message"])


if __name__ == "__main__":
    unittest.main()
