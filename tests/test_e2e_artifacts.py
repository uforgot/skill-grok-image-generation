import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "examples" / "e2e-1139-results.json"


class E2EArtifactTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_committed_samples_match_verified_results(self):
        for result in self.manifest["success"].values():
            sample = ROOT / "examples" / result["sample"]
            payload = sample.read_bytes()
            self.assertTrue(payload.startswith(b"\xff\xd8\xff"))
            self.assertEqual(len(payload), result["bytes"])
            self.assertEqual(hashlib.sha256(payload).hexdigest(), result["sha256"])

    def test_manifest_records_ratio_paths_and_fail_closed_results(self):
        generate = self.manifest["success"]["generate"]
        edit = self.manifest["success"]["edit"]
        self.assertEqual((generate["width"], generate["height"]), (1280, 720))
        self.assertEqual((edit["width"], edit["height"]), (720, 1280))
        self.assertEqual(generate["requested_extension"], ".png")
        self.assertEqual(generate["returned_extension"], ".jpg")
        self.assertEqual(edit["requested_extension"], ".png")
        self.assertEqual(edit["returned_extension"], ".jpg")
        self.assertFalse(edit["source_overwritten"])

        oauth = self.manifest["fail_closed"]["oauth_expired"]
        permission = self.manifest["fail_closed"]["permission_cancelled"]
        self.assertEqual((oauth["error"], oauth["exit_code"]), ("oauth_invalid", 3))
        self.assertEqual(
            (permission["error"], permission["exit_code"]),
            ("permission_cancelled", 4),
        )
        for result in (oauth, permission):
            self.assertFalse(result["fallback_used"])
            self.assertFalse(result["output_exists"])
            self.assertTrue(result["message"])
            self.assertTrue(result["next_action"])


if __name__ == "__main__":
    unittest.main()
