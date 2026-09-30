import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_orchestrator import dashboard


class NativeSessionImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.outputs = self.root / "outputs"
        self.workspace = self.root / "workspace"
        self.home.mkdir()
        self.outputs.mkdir()
        self.workspace.mkdir()

        codex = (
            self.home / ".codex" / "sessions" / "2026" / "09" / "26"
            / "rollout-test.jsonl"
        )
        codex.parent.mkdir(parents=True)
        codex.write_text(json.dumps({
            "type": "session_meta",
            "payload": {
                "id": "11111111-1111-4111-8111-111111111111",
                "cwd": str(self.workspace),
                "timestamp": "2026-09-26T10:00:00-07:00",
            },
        }) + "\n")
        self.codex_path = codex
        self.codex_original = codex.read_bytes()

        claude = (
            self.home / ".claude" / "projects" / "-tmp-workspace"
            / "22222222-2222-4222-8222-222222222222.jsonl"
        )
        claude.parent.mkdir(parents=True)
        claude.write_text(json.dumps({
            "sessionId": "22222222-2222-4222-8222-222222222222",
            "cwd": str(self.workspace),
            "timestamp": "2026-09-26T11:00:00-07:00",
            "type": "user",
        }) + "\n")

        cursor = (
            self.home / ".cursor" / "projects" / "tmp-workspace"
            / "agent-transcripts" / "33333333-3333-4333-8333-333333333333"
            / "33333333-3333-4333-8333-333333333333.jsonl"
        )
        cursor.parent.mkdir(parents=True)
        cursor.write_text(json.dumps({"role": "user", "message": "private"}) + "\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_scanner_reads_metadata_for_all_supported_agents(self):
        with patch.object(dashboard.Path, "home", return_value=self.home):
            rows = dashboard._scan_native_sessions()

        self.assertEqual({row["agent"] for row in rows}, {
            "codex", "claude", "cursor",
        })
        codex = next(row for row in rows if row["agent"] == "codex")
        self.assertEqual(codex["cwd"], str(self.workspace))
        self.assertEqual(
            codex["native_key"],
            "codex:11111111-1111-4111-8111-111111111111",
        )
        self.assertNotIn("private", json.dumps(rows))

    def test_import_creates_only_orchestrator_index_metadata(self):
        with patch.object(dashboard.Path, "home", return_value=self.home):
            candidate = next(
                row for row in dashboard._scan_native_sessions()
                if row["agent"] == "codex"
            )
            imported = dashboard._import_native_session(self.outputs, candidate)
            indexed = dashboard._imported_native_keys(self.outputs)

        self.assertIn(candidate["native_key"], indexed)
        self.assertEqual(indexed[candidate["native_key"]], imported["run_id"])
        run_name = imported["run_id"].split("::", 1)[0]
        metadata = json.loads(
            (self.outputs / run_name / "session.json").read_text()
        )
        self.assertEqual(metadata["status"], "finished")
        self.assertEqual(metadata["import_source"], "native-history")
        self.assertEqual(metadata["resume_id"], candidate["resume_id"])
        self.assertEqual(self.codex_path.read_bytes(), self.codex_original)


class NativeSessionImportContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        project = Path(__file__).resolve().parents[1]
        cls.index = (project / "static" / "index.html").read_text()
        cls.backend = (
            project / "agent_orchestrator" / "dashboard.py"
        ).read_text()

    def test_new_session_modal_offers_import_mode(self):
        self.assertIn('<option value="import" data-ui-message=Import%20existing>Import existing</option>', self.index)
        self.assertIn('id="new-import-list"', self.index)
        self.assertIn('api("/api/native-sessions/import"', self.index)

    def test_backend_exposes_scan_and_import_endpoints(self):
        self.assertIn('@app.get("/api/native-sessions")', self.backend)
        self.assertIn('@app.post("/api/native-sessions/import")', self.backend)
        self.assertIn('explicit import confirmation is required', self.backend)


if __name__ == "__main__":
    unittest.main()
