from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.ljson import decode, load_file
from stagewarden.memory import MemoryStore
from stagewarden.main import _interactive_completion_candidates, _render_boundary, _render_handoff, run_interactive_shell
from stagewarden.modelprefs import ModelPreferences
from stagewarden.secrets import SecretStore


ROOT = Path(__file__).resolve().parents[1]


def write_success_stub(root: Path) -> Path:
    path = root / "run_model_success_stub.py"
    path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "import json",
                "import re",
                "import sys",
                "",
                "def extract(prompt: str, field: str) -> str:",
                '    match = re.search(rf"^{re.escape(field)}=(.+)$", prompt, re.MULTILINE)',
                "    return match.group(1).strip() if match else ''",
                "",
                "def detect_target_file(text: str) -> str | None:",
                '    match = re.search(r\"file named ([A-Za-z0-9._/\\\\-]+)\", text, re.IGNORECASE)',
                "    return match.group(1) if match else None",
                "",
                "def main() -> int:",
                "    if len(sys.argv) < 3:",
                "        print(json.dumps({'error': 'usage: stub <model> <prompt>'}))",
                "        return 1",
                "    prompt = sys.argv[2]",
                "    instruction = extract(prompt, 'instruction').lower()",
                "    task_match = re.search(r'Task:\\n(.+?)\\n\\nImplicit project handoff context:', prompt, re.DOTALL)",
                "    task = task_match.group(1).strip() if task_match else ''",
                "    if instruction.startswith('analyze') or instruction.startswith('inspect'):",
                "        action = {'type': 'complete', 'message': 'analysis validated exit_code=0'}",
                "    elif 'implement' in instruction or 'create' in instruction or 'build' in instruction or 'continue from persisted handoff context' in instruction:",
                "        target = detect_target_file(f'{instruction} {task}') or 'stub_output.txt'",
                "        action = {'type': 'write_file', 'path': target, 'content': 'created by test stub\\n'}",
                "    else:",
                "        action = {'type': 'complete', 'message': 'validation completed exit_code=0'}",
                "    print(json.dumps({'summary': 'stub response', 'action': action}))",
                "    return 0",
                "",
                "if __name__ == '__main__':",
                "    raise SystemExit(main())",
            ]
        ),
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def run_main_in_cwd(cwd: Path, *args: str) -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        ["python3", "-m", "stagewarden.main", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.returncode


def run_main_capture(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    return subprocess.run(
        ["python3", "-m", "stagewarden.main", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


class TraceAndCliTests(unittest.TestCase):
    def test_agent_writes_ljson_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            agent = Agent(AgentConfig(workspace_root=root, max_steps=1))
            agent.run("simple task")
            self.assertTrue((root / ".stagewarden_trace.ljson").exists())
            self.assertTrue((root / ".stagewarden_handoff.json").exists())
            payload = json.loads((root / ".stagewarden_trace.ljson").read_text())
            self.assertIn("_fields", payload)
            self.assertGreaterEqual(len(decode(payload)), 1)
            handoff_payload = json.loads((root / ".stagewarden_handoff.json").read_text())
            self.assertEqual(handoff_payload.get("_format"), "stagewarden_project_handoff")
            self.assertIn("entries", handoff_payload)

    def test_load_file_roundtrip_from_dumped_ljson(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sample = root / "sample.ljson"
            sample.write_text(json.dumps({"_version": 1, "_fields": ["id"], "data": [[1], [2]]}))
            self.assertEqual(load_file(sample), [{"id": 1}, {"id": 2}])

    def test_ljson_cli_uses_clear_default_gzip_suffixes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source = root / "records.json"
            source.write_text(json.dumps([{"id": 1, "name": "Mario"}]), encoding="utf-8")

            encoded_code = run_main_in_cwd(root, "--ljson-encode", str(source), "--ljson-gzip")
            encoded = root / "records.ljson.gz"
            self.assertEqual(encoded_code, 0)
            self.assertTrue(encoded.exists())

            decoded_code = run_main_in_cwd(root, "--ljson-decode", str(encoded))
            decoded = root / "records.json"
            self.assertEqual(decoded_code, 0)
            self.assertEqual(json.loads(decoded.read_text(encoding="utf-8")), [{"id": 1, "name": "Mario"}])

    def test_interactive_shell_handles_help_and_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO("help\nmodels\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Stagewarden interactive shell", rendered)
            self.assertIn("Use `help <topic>`", rendered)
            self.assertIn("Topics:", rendered)
            self.assertIn("help models", rendered)
            self.assertIn("help accounts", rendered)
            self.assertIn("help permissions", rendered)
            self.assertIn("Fast examples:", rendered)
            self.assertIn("Model configuration:", rendered)
            self.assertIn("Session closed.", rendered)

    def test_doctor_cli_reports_prerequisites_without_initializing_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "doctor")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Stagewarden doctor:", completed.stdout)
            self.assertIn("- Python: OK", completed.stdout)
            self.assertIn("- Git: OK", completed.stdout)
            self.assertIn("- PATH launcher:", completed.stdout)
            self.assertIn("Provider capabilities:", completed.stdout)
            self.assertIn("- chatgpt: auth=chatgpt_plan_oauth", completed.stdout)
            self.assertIn("- openai: auth=openai_api_key", completed.stdout)
            self.assertIn("- claude: auth=anthropic_api_key_or_claude_code_credentials", completed.stdout)
            self.assertIn("no prerequisites are installed silently", completed.stdout)
            self.assertFalse((root / ".git").exists())

    def test_doctor_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "doctor", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "doctor")
            self.assertEqual(payload["python"]["status"], "OK")
            self.assertTrue(payload["git"]["ok"])
            self.assertIn("silent_install", payload["policy"])
            self.assertFalse(payload["policy"]["silent_install"])
            providers = {entry["provider"]: entry for entry in payload["providers"]}
            self.assertIn("chatgpt", providers)
            self.assertEqual(providers["chatgpt"]["auth"], "chatgpt_plan_oauth")
            self.assertIn("default_model", providers["openai"])
            self.assertFalse((root / ".git").exists())

    def test_models_usage_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="local",
                action_type="complete",
                action_signature="a",
                success=True,
                observation="ok",
            )
            memory.record_attempt(
                iteration=2,
                step_id="step-2",
                model="cheap",
                action_type="complete",
                action_signature="b",
                success=False,
                observation="quota",
                error_type="api_failure",
            )
            memory.save(root / ".stagewarden_memory.json")
            completed = run_main_capture(root, "models usage", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "models usage")
            self.assertEqual(payload["report"]["totals"]["calls"], 2)
            self.assertEqual(payload["report"]["totals"]["failures"], 1)
            self.assertEqual(payload["report"]["totals"]["escalation_path"], "local -> cheap")
            self.assertIn("routing_budget", payload["policy"])

    def test_transcript_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            memory = MemoryStore()
            memory.record_tool_transcript(
                iteration=1,
                step_id="step-1",
                tool="shell",
                action_type="shell",
                success=True,
                summary="pwd",
                detail="exit_code=0",
                duration_ms=10,
            )
            memory.save(root / ".stagewarden_memory.json")
            completed = run_main_capture(root, "transcript", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "transcript")
            self.assertEqual(payload["report"]["count"], 1)
            self.assertEqual(payload["report"]["entries"][0]["tool"], "shell")
            self.assertEqual(payload["report"]["entries"][0]["summary"], "pwd")

    def test_handoff_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_title": "Validate result",
                "current_step_status": "in_progress",
                "latest_observation": "wet-run pending",
                "plan_status": "step-1:completed,step-2:completed,step-3:in_progress",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            completed = run_main_capture(root, "handoff", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "handoff")
            self.assertEqual(payload["handoff"]["task"], "fix failing tests")
            self.assertEqual(payload["stage_view"]["boundary_decision"], "continue_current_stage")
            self.assertEqual(payload["next_action"], "continue step-3")

    def test_resume_show_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-7",
                "current_step_title": "Validate",
                "current_step_status": "in_progress",
                "latest_observation": "wet-run pending",
                "plan_status": "step-7:in_progress",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            completed = run_main_capture(root, "resume --show", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "resume --show")
            self.assertEqual(payload["task"], "fix failing tests")
            self.assertEqual(payload["current_step"], "step-7")
            self.assertEqual(payload["current_step_status"], "in_progress")
            self.assertEqual(payload["next_action"], "continue step-7")

    def test_resume_context_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=4,
                step_id="step-7",
                model="claude",
                account="work",
                variant="sonnet",
                action_type="shell",
                action_signature="python3 -m unittest",
                success=True,
                observation="wet-run completed",
            )
            memory.record_tool_transcript(
                iteration=4,
                step_id="step-7",
                tool="shell",
                action_type="shell",
                success=True,
                summary="tests passed",
                duration_ms=789,
            )
            memory.save(root / ".stagewarden_memory.json")
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-7",
                "current_step_title": "Validate",
                "current_step_status": "in_progress",
                "latest_observation": "wet-run pending",
                "plan_status": "step-7:in_progress",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "entries": [
                    {
                        "phase": "git_snapshot",
                        "iteration": 4,
                        "step_id": "step-7",
                        "step_status": "completed",
                        "model": "claude",
                        "action_type": "git_snapshot",
                        "summary": "stagewarden: step step-7 completed [stage=stable boundary=continue]",
                        "detail": "",
                        "git_head": "ff77aa2",
                        "timestamp": "2026-04-20T10:30:00+00:00",
                    }
                ],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            completed = run_main_capture(root, "resume context", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "resume context")
            self.assertEqual(payload["task"], "fix failing tests")
            self.assertEqual(payload["current_step"], "step-7")
            self.assertEqual(payload["latest_model_attempt"]["route"]["model"], "claude")
            self.assertEqual(payload["latest_model_attempt"]["route"]["account"], "work")
            self.assertEqual(payload["latest_model_attempt"]["route"]["variant"], "sonnet")
            self.assertEqual(payload["latest_tool_evidence"]["tool"], "shell")
            self.assertEqual(payload["latest_tool_evidence"]["duration_ms"], 789)
            self.assertEqual(payload["latest_git_snapshot"]["git_head"], "ff77aa2")

    def test_handoff_export_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "HANDOFF.md").write_text("# Stagewarden Handoff\n", encoding="utf-8")
            completed = run_main_capture(root, "handoff export", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "handoff export")
            self.assertEqual(payload["target"], "HANDOFF.md")
            self.assertTrue(payload["updated"])
            self.assertIn("Exported runtime handoff", payload["message"])

    def test_resume_clear_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-7",
                "current_step_status": "in_progress",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            completed = run_main_capture(root, "resume --clear", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "resume --clear")
            self.assertTrue(payload["archived"])
            self.assertTrue(str(payload["archive_path"]).startswith(".stagewarden_handoff.archive."))

    def test_status_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_title": "Validate result",
                "current_step_status": "in_progress",
                "latest_observation": "wet-run pending",
                "plan_status": "step-1:completed,step-2:completed,step-3:in_progress",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            completed = run_main_capture(root, "status", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "status")
            self.assertEqual(payload["mode"], "normal")
            self.assertEqual(payload["handoff"]["stage_view"]["boundary_decision"], "continue_current_stage")
            self.assertIn("models", payload)
            self.assertIn("permissions", payload)

    def test_models_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.preferred_model = "cheap"
            prefs.enabled_models = ["local", "cheap"]
            prefs.set_variant("cheap", "provider-default")
            prefs.save(root / ".stagewarden_models.json")
            completed = run_main_capture(root, "models", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "models")
            self.assertEqual(payload["preferred_model"], "cheap")
            models = {item["model"]: item for item in payload["models"]}
            self.assertTrue(models["cheap"]["enabled"])
            self.assertTrue(models["cheap"]["preferred"])

    def test_accounts_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                prefs = ModelPreferences.default()
                prefs.add_account("openai", "lavoro", "OPENAI_API_KEY_WORK")
                prefs.set_active_account("openai", "lavoro")
                prefs.save(root / ".stagewarden_models.json")
                SecretStore().save_token("openai", "lavoro", "secret-token")
                completed = run_main_capture(root, "accounts", "--json")
            finally:
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "accounts")
            self.assertEqual(payload["models"][0]["model"], "openai")
            self.assertEqual(payload["models"][0]["accounts"][0]["name"], "lavoro")
            self.assertTrue(payload["models"][0]["accounts"][0]["active"])
            self.assertTrue(payload["models"][0]["accounts"][0]["token_stored"])

    def test_permissions_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            settings = {
                "permissions": {
                    "defaultMode": "plan",
                    "allow": ["shell:git status"],
                    "ask": ["file:secret.txt"],
                    "deny": ["shell:rm"],
                }
            }
            (root / ".stagewarden_settings.json").write_text(json.dumps(settings), encoding="utf-8")
            completed = run_main_capture(root, "permissions", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "permissions")
            self.assertEqual(payload["report"]["workspace"]["mode"], "plan")
            self.assertEqual(payload["report"]["workspace"]["allow"], ["shell:git status"])
            self.assertEqual(payload["report"]["workspace"]["ask"], ["file:secret.txt"])
            self.assertEqual(payload["report"]["workspace"]["deny"], ["shell:rm"])

    def test_overview_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_status": "in_progress",
                "plan_status": "step-1:completed,step-2:completed,step-3:in_progress",
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "validation pending", "status": "open"}],
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="local",
                action_type="complete",
                action_signature="a",
                success=True,
                observation="ok",
            )
            memory.record_tool_transcript(
                iteration=1,
                step_id="step-1",
                tool="shell",
                action_type="shell",
                success=True,
                summary="pwd",
                detail="exit_code=0",
                duration_ms=10,
            )
            memory.save(root / ".stagewarden_memory.json")
            completed = run_main_capture(root, "overview", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "overview")
            self.assertEqual(payload["board"]["recommended_authorization"], "review")
            self.assertEqual(payload["model_usage"]["report"]["totals"]["calls"], 1)
            self.assertEqual(payload["transcript"]["report"]["count"], 1)
            self.assertEqual(payload["handoff"]["handoff"]["task"], "fix failing tests")

    def test_health_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_status": "in_progress",
                "plan_status": "step-1:completed,step-2:completed,step-3:in_progress",
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "validation pending", "status": "open"}],
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="local",
                action_type="complete",
                action_signature="a",
                success=False,
                observation="failed",
            )
            memory.record_tool_transcript(
                iteration=1,
                step_id="step-1",
                tool="shell",
                action_type="shell",
                success=True,
                summary="pwd",
                detail="exit_code=0",
                duration_ms=10,
            )
            memory.save(root / ".stagewarden_memory.json")
            completed = run_main_capture(root, "health", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "health")
            self.assertFalse(payload["ready"])
            self.assertEqual(payload["recommended_authorization"], "review")
            self.assertEqual(payload["open_issues"], 1)
            self.assertEqual(payload["model_failures"], 1)
            self.assertEqual(payload["transcript_entries"], 1)

    def test_report_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_status": "in_progress",
                "plan_status": "step-1:completed,step-2:completed,step-3:in_progress",
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "validation pending", "status": "open"}],
                "implementation_backlog": [
                    {"step_id": "next-step", "title": "add release note", "status": "ready", "validation": "release note written"},
                    {"step_id": "later-step", "title": "finalize smoke test", "status": "planned", "validation": "smoke test passed"},
                ],
                "lessons_log": [
                    {"type": "success", "step_id": "step-2", "lesson": "reuse the stable patch pattern"},
                ],
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="local",
                action_type="complete",
                action_signature="a",
                success=True,
                observation="ok",
            )
            memory.record_tool_transcript(
                iteration=1,
                step_id="step-1",
                tool="shell",
                action_type="shell",
                success=True,
                summary="pwd",
                detail="exit_code=0",
                duration_ms=10,
            )
            memory.save(root / ".stagewarden_memory.json")
            completed = run_main_capture(root, "report", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "report")
            self.assertEqual(payload["task"], "fix failing tests")
            self.assertEqual(payload["recommended_authorization"], "review")
            self.assertEqual(payload["open_issues"], 1)
            self.assertEqual(payload["model_calls"], 1)
            self.assertIn("reuse the stable patch pattern", payload["recent_lessons"][0])
            self.assertIn("add release note", payload["backlog_preview"][0])
            self.assertIn("finalize smoke test", payload["backlog_preview"][1])

    def test_interactive_completion_candidates_include_core_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir))
            matches = _interactive_completion_candidates("he", config)
            self.assertIn("help", matches)
            self.assertIn("health", matches)

    def test_interactive_completion_candidates_expand_workspace_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "tracked.txt").write_text("hello\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "notes.md").write_text("note\n", encoding="utf-8")
            config = AgentConfig(workspace_root=root)

            history_matches = _interactive_completion_candidates("git history tr", config)
            patch_matches = _interactive_completion_candidates("patch preview do", config)

            self.assertIn("git history tracked.txt", history_matches)
            self.assertIn("patch preview docs/", patch_matches)

    def test_git_cli_json_outputs_are_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(["git", "-C", str(root), "init"], capture_output=True, text=True, check=False)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "Stagewarden Test"], capture_output=True, text=True, check=False)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "stagewarden@example.com"], capture_output=True, text=True, check=False)
            (root / "tracked.txt").write_text("hello\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "tracked.txt"], capture_output=True, text=True, check=False)
            subprocess.run(["git", "-C", str(root), "commit", "-m", "add tracked"], capture_output=True, text=True, check=False)

            status = json.loads(run_main_capture(root, "git status", "--json").stdout)
            log_payload = json.loads(run_main_capture(root, "git log 5", "--json").stdout)
            history = json.loads(run_main_capture(root, "git history tracked.txt 5", "--json").stdout)
            show = json.loads(run_main_capture(root, "git show --stat HEAD", "--json").stdout)

            self.assertEqual(status["command"], "git status")
            self.assertTrue(status["ok"])
            self.assertIsInstance(status["lines"], list)
            self.assertEqual(log_payload["command"], "git log")
            self.assertTrue(log_payload["ok"])
            self.assertEqual(log_payload["limit"], 5)
            self.assertEqual(log_payload["commits"][0]["subject"], "add tracked")
            self.assertEqual(history["command"], "git history")
            self.assertEqual(history["path"], "tracked.txt")
            self.assertEqual(history["commits"][0]["subject"], "add tracked")
            self.assertEqual(show["command"], "git show")
            self.assertTrue(show["stat"])
            self.assertEqual(show["revision"], "HEAD")

    def test_sessions_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "sessions", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "sessions")
            self.assertEqual(payload["count"], 0)
            self.assertEqual(payload["items"], [])

    def test_boundary_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "exception",
                "current_step_id": "step-3",
                "current_step_title": "Validate result",
                "current_step_status": "failed",
                "latest_observation": "validation failed",
                "plan_status": "step-1:completed,step-2:completed,step-3:failed",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "exception_plan": ["review boundary for step-3"],
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            completed = run_main_capture(root, "boundary", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "boundary")
            self.assertEqual(payload["stage_view"]["boundary_decision"], "review_boundary:exception_plan")
            self.assertEqual(payload["stage_view"]["recovery_state"], "exception_active")

    def test_register_cli_json_outputs_are_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_status": "in_progress",
                "risk_register": [{"risk": "Regression from patch execution", "status": "open"}],
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "validation pending", "status": "open"}],
                "quality_register": [{"step_id": "step-2", "status": "passed", "evidence": "file updated"}],
                "lessons_log": [{"step_id": "step-2", "type": "success", "lesson": "file update pattern is reusable"}],
                "exception_plan": ["review boundary for step-3"],
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect tests", "status": "done", "validation": "Real command output captured."}
                ],
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            risks = json.loads(run_main_capture(root, "risks", "--json").stdout)
            issues = json.loads(run_main_capture(root, "issues", "--json").stdout)
            quality = json.loads(run_main_capture(root, "quality", "--json").stdout)
            exception = json.loads(run_main_capture(root, "exception", "--json").stdout)
            lessons = json.loads(run_main_capture(root, "lessons", "--json").stdout)
            todo = json.loads(run_main_capture(root, "todo", "--json").stdout)

            self.assertEqual(risks["command"], "risks")
            self.assertEqual(risks["count"], 1)
            self.assertEqual(risks["items"][0]["risk"], "Regression from patch execution")
            self.assertEqual(issues["command"], "issues")
            self.assertEqual(issues["items"][0]["summary"], "validation pending")
            self.assertEqual(quality["command"], "quality")
            self.assertEqual(quality["items"][0]["evidence"], "file updated")
            self.assertEqual(exception["command"], "exception")
            self.assertEqual(exception["items"][0], "review boundary for step-3")
            self.assertEqual(lessons["command"], "lessons")
            self.assertEqual(lessons["items"][0]["lesson"], "file update pattern is reusable")
            self.assertEqual(todo["command"], "todo")
            self.assertEqual(todo["items"][0]["title"], "Inspect tests")

    def test_interactive_shell_doctor_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO("doctor\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Stagewarden doctor:", rendered)
            self.assertIn("- Python: OK", rendered)
            self.assertIn("- Git: OK", rendered)
            self.assertIn("Provider capabilities:", rendered)

    def test_interactive_shell_supports_category_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO(
                "help models\n"
                "help accounts\n"
                "help permissions\n"
                "help handoff\n"
                "help git\n"
                "help ljson\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Model commands", rendered)
            self.assertIn("model variant <provider> <variant>", rendered)
            self.assertIn("Account commands", rendered)
            self.assertIn("account login-device <chatgpt|openai> <name>", rendered)
            self.assertIn("Permission commands", rendered)
            self.assertIn("permission session allow <rule>", rendered)
            self.assertIn("Handoff and PRINCE2 commands", rendered)
            self.assertIn("handoff export | handoff md", rendered)
            self.assertIn("Git commands", rendered)
            self.assertIn("git history <path> [limit]", rendered)
            self.assertIn("LJSON commands", rendered)
            self.assertIn("--ljson-benchmark", rendered)

    def test_interactive_shell_executes_task(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/Stagewarden/run_model_stub"
            try:
                config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=6)
                input_stream = StringIO("create a file named hello.txt\ntranscript\nquit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            self.assertEqual(code, 0)
            self.assertTrue((Path(tmp_dir) / "hello.txt").exists())
            rendered = output_stream.getvalue()
            self.assertIn("Running task: create a file named hello.txt", rendered)
            self.assertIn("Shell progress (before):", rendered)
            self.assertIn("route: model=local account=none variant=provider-default", rendered)
            self.assertIn("Agent result:", rendered)
            self.assertIn("Last step outcome:", rendered)
            self.assertIn("step: step-3", rendered)
            self.assertIn("action: shell", rendered)
            self.assertIn("evidence: tool=shell action=shell", rendered)
            self.assertIn("Shell progress (after):", rendered)
            self.assertIn("route: model=local account=none variant=provider-default", rendered)
            self.assertIn("git_snapshot:", rendered)
            self.assertRegex(rendered, r"git_snapshot: [0-9a-f]{7,40} ::")
            self.assertIn("Tool transcript:", rendered)
            self.assertIn("tool=files", rendered)
            self.assertIn("action=write_file", rendered)

    def test_interactive_shell_streams_model_output_live(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = root / "run_model_stream_stub.py"
            stub.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import sys",
                        "sys.stdout.write('{\"summary\":\"ok\",')",
                        "sys.stdout.flush()",
                        "sys.stdout.write('\"action\":{\"type\":\"complete\",\"message\":\"validation completed exit_code=0\"}}')",
                        "sys.stdout.flush()",
                    ]
                ),
                encoding="utf-8",
            )
            stub.chmod(0o755)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                config = AgentConfig(workspace_root=root, max_steps=4)
                input_stream = StringIO("analyze repo structure\nquit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Running task: analyze repo structure", rendered)
            self.assertIn("Shell progress (before):", rendered)
            self.assertIn("Agent result:", rendered)
            self.assertIn("Last step outcome:", rendered)
            self.assertIn("evidence: none", rendered)
            self.assertIn("Shell progress (after):", rendered)
            self.assertIn("[model-stream local]", rendered)
            self.assertIn('"summary":"ok"', rendered)

    def test_interactive_shell_can_toggle_stream_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("stream status\nstream off\nstream status\nstream on\nstream status\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Model streaming is on.", rendered)
            self.assertIn("Model streaming disabled for this session.", rendered)
            self.assertIn("Model streaming is off.", rendered)
            self.assertIn("Model streaming enabled for this session.", rendered)

    def test_interactive_shell_stream_off_suppresses_live_model_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = root / "run_model_stream_stub.py"
            stub.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "import sys",
                        "print('{\"summary\":\"ok\",\"action\":{\"type\":\"complete\",\"message\":\"validation completed exit_code=0\"}}')",
                    ]
                ),
                encoding="utf-8",
            )
            stub.chmod(0o755)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                config = AgentConfig(workspace_root=root, max_steps=4)
                input_stream = StringIO("stream off\nanalyze repo structure\nquit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Model streaming disabled for this session.", rendered)
            self.assertNotIn("[model-stream local]", rendered)

    def test_interactive_shell_permission_ask_can_be_approved_for_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/Stagewarden/run_model_stub"
            try:
                config = AgentConfig(workspace_root=root, max_steps=6)
                input_stream = StringIO(
                    "permission ask file:hello.txt\n"
                    "create a file named hello.txt\n"
                    "session\n"
                    "permissions\n"
                    "quit\n"
                )
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertTrue((root / "hello.txt").exists())
            self.assertIn("Permission approval required:", rendered)
            self.assertIn("Permission approved for this session: file:hello.txt", rendered)
            self.assertIn("session allow: file:hello.txt", rendered)
            payload = json.loads((root / ".stagewarden_settings.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["permissions"]["ask"], ["file:hello.txt"])
            self.assertEqual(payload["permissions"]["allow"], [])

    def test_interactive_shell_permission_ask_can_be_persisted_as_always_allow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = "/Users/donato/Stagewarden/run_model_stub"
            try:
                config = AgentConfig(workspace_root=root, max_steps=6)
                input_stream = StringIO(
                    "permission ask file:hello.txt\n"
                    "create a file named hello.txt\n"
                    "always\n"
                    "permissions\n"
                    "quit\n"
                )
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertTrue((root / "hello.txt").exists())
            self.assertIn("Permission persisted as allow rule: file:hello.txt", rendered)
            self.assertIn("workspace allow: file:hello.txt", rendered)
            payload = json.loads((root / ".stagewarden_settings.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["permissions"]["allow"], ["file:hello.txt"])
            self.assertEqual(payload["permissions"]["ask"], [])

    def test_agent_resets_system_prompt_each_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            agent = Agent(AgentConfig(workspace_root=Path(tmp_dir), max_steps=1))
            base = agent.base_system_prompt
            agent.run("simple task")
            first_prompt = agent.executor.config.system_prompt
            agent.run("simple task")
            second_prompt = agent.executor.config.system_prompt
            self.assertIn("PRINCE2 agent policy", first_prompt)
            self.assertIn("PRINCE2 agent policy", second_prompt)
            self.assertEqual(second_prompt.count("PRINCE2 agent policy"), 1)
            self.assertEqual(base, agent.base_system_prompt)

    def test_interactive_shell_persists_model_preference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("model use cheap\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            self.assertEqual(code, 0)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual(prefs.preferred_model, "cheap")
            self.assertIn("cheap", prefs.enabled_models)

    def test_interactive_shell_persists_provider_model_variant(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("model variant claude opus\nmodel list claude\nmodels\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")

            self.assertEqual(code, 0)
            self.assertEqual((prefs.variant_by_model or {}).get("claude"), "opus")
            self.assertIn("Available variants for claude:", rendered)
            self.assertIn("Auth: anthropic_api_key_or_claude_code_credentials", rendered)
            self.assertIn("Browser login: no", rendered)
            self.assertIn("Login hint: Use ANTHROPIC_API_KEY", rendered)
            self.assertIn("opusplan", rendered)
            self.assertIn("variant=opus", rendered)

    def test_interactive_shell_model_list_uses_provider_registry_for_login_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("model list chatgpt\nmodel list openai\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Auth: chatgpt_plan_oauth", rendered)
            self.assertIn("API key: no", rendered)
            self.assertIn("Use account login chatgpt <profile>", rendered)
            self.assertIn("Auth: openai_api_key", rendered)
            self.assertIn("API key: yes", rendered)
            self.assertIn("Prefer OPENAI_API_KEY", rendered)

    def test_interactive_shell_manages_persistent_shell_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "sessions\n"
                "session create\n"
                "session list\n"
                "session send last pwd\n"
                "session close last\n"
                "session list\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("No active shell sessions.", rendered)
            self.assertIn("shell_session_created id=", rendered)
            self.assertIn("state=running", rendered)
            self.assertIn("session_id=", rendered)
            self.assertIn("exit_code=0", rendered)
            self.assertIn(str(root), rendered)
            self.assertIn("shell_session_closed id=", rendered)

    def test_interactive_shell_enforces_permission_inside_shell_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "permission session mode plan\n"
                "session create\n"
                "session send last python3 -c \"open('out.txt','w').write('x')\"\n"
                "session close last\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Session permission mode set to plan.", rendered)
            self.assertIn("Plan mode allows analysis only.", rendered)
            self.assertFalse((root / "out.txt").exists())

    def test_interactive_shell_previews_patch_file_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "target.txt").write_text("before\n", encoding="utf-8")
            (root / "changes.diff").write_text(
                "\n".join(
                    [
                        "--- a/target.txt",
                        "+++ b/target.txt",
                        "@@ -1,1 +1,1 @@",
                        "-before",
                        "+after",
                    ]
                ),
                encoding="utf-8",
            )
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("permission session mode plan\npatch preview changes.diff\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Patch preview:", rendered)
            self.assertIn("update target.txt", rendered)
            self.assertEqual((root / "target.txt").read_text(encoding="utf-8"), "before\n")

    def test_interactive_shell_renders_model_usage_and_cost_alias(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="local",
                action_type="read_file",
                action_signature='{"type":"read_file"}',
                success=True,
                observation="ok",
            )
            memory.record_attempt(
                iteration=2,
                step_id="step-2",
                model="claude",
                action_type="complete",
                action_signature='{"type":"complete"}',
                success=False,
                observation="failed",
                error_type="api_failure",
            )
            memory.save(config.memory_path)
            input_stream = StringIO("models usage\ncost\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("local: calls=1 failures=0", rendered)
            self.assertIn("claude: calls=1 failures=1", rendered)
            self.assertIn("totals: calls=2 failures=1 steps=2 failure_rate=50.00%", rendered)
            self.assertIn("routing: last_model=claude highest_tier=high/fallback highest_model=claude escalation_path=local -> claude", rendered)
            self.assertGreaterEqual(rendered.count("Model usage:"), 2)

    def test_interactive_shell_manages_model_accounts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "account add openai lavoro OPENAI_API_KEY_WORK\n"
                "account add openai personale OPENAI_API_KEY_PERSONAL\n"
                "account use openai personale\n"
                "account block openai lavoro until 2026-05-01T18:30\n"
                "accounts\n"
                "models\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("openai"), "personale")
            self.assertEqual((prefs.env_var_by_account or {}).get("openai:lavoro"), "OPENAI_API_KEY_WORK")
            self.assertIn("openai:lavoro", prefs.blocked_until_by_account or {})
            self.assertIn("account personale:", rendered)
            self.assertIn("active-account", rendered)
            self.assertIn("env=OPENAI_API_KEY_WORK", rendered)

    def test_interactive_shell_logs_in_account_and_saves_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                import stagewarden.main as main_module

                original_run = main_module.OpenAIDeviceCodeFlow.run

                def fake_run(self):  # noqa: ANN001
                    from stagewarden.auth import AuthResult

                    return AuthResult(
                        True,
                        "Device code login completed.",
                        token="access-token-123",
                        secret_payload='{"access_token":"access-token-123","refresh_token":"refresh-token-123"}',
                    )

                main_module.OpenAIDeviceCodeFlow.run = fake_run
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login openai lavoro\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("openai", "lavoro")
            finally:
                main_module.OpenAIDeviceCodeFlow.run = original_run
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("openai"), "lavoro")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertIn('"refresh_token":"refresh-token-123"', loaded.secret)
            self.assertIn("Device code login completed.", rendered)
            self.assertIn("token=stored", rendered)

    def test_interactive_shell_logs_in_chatgpt_account_and_saves_session_token(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                import stagewarden.main as main_module

                original_run = main_module.OpenAIDeviceCodeFlow.run

                def fake_run(self):  # noqa: ANN001
                    from stagewarden.auth import AuthResult

                    return AuthResult(
                        True,
                        "Device code login completed.",
                        token="access-token-123",
                        secret_payload='{"access_token":"access-token-123","refresh_token":"refresh-token-123","id_token":"id-token-123"}',
                    )

                main_module.OpenAIDeviceCodeFlow.run = fake_run
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login chatgpt personale\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("chatgpt", "personale")
            finally:
                main_module.OpenAIDeviceCodeFlow.run = original_run
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("chatgpt"), "personale")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertIn('"id_token":"id-token-123"', loaded.secret)
            self.assertIn("Device code login completed.", rendered)
            self.assertIn("token=stored", rendered)

    def test_interactive_shell_logs_in_openai_account_with_device_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            original_client = os.environ.get("STAGEWARDEN_OPENAI_CLIENT_ID")
            original_browser = os.environ.get("STAGEWARDEN_SKIP_BROWSER")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            os.environ["STAGEWARDEN_OPENAI_CLIENT_ID"] = "client-id"
            os.environ["STAGEWARDEN_SKIP_BROWSER"] = "1"
            try:
                import stagewarden.main as main_module

                original_run = main_module.OpenAIDeviceCodeFlow.run

                def fake_run(self):  # noqa: ANN001
                    from stagewarden.auth import AuthResult

                    return AuthResult(
                        True,
                        "Device code login completed.",
                        token="access-token-123",
                        secret_payload='{"access_token":"access-token-123","refresh_token":"refresh-token-123"}',
                    )

                main_module.OpenAIDeviceCodeFlow.run = fake_run
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login-device openai lavoro\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("openai", "lavoro")
            finally:
                main_module.OpenAIDeviceCodeFlow.run = original_run
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store
                if original_client is None:
                    os.environ.pop("STAGEWARDEN_OPENAI_CLIENT_ID", None)
                else:
                    os.environ["STAGEWARDEN_OPENAI_CLIENT_ID"] = original_client
                if original_browser is None:
                    os.environ.pop("STAGEWARDEN_SKIP_BROWSER", None)
                else:
                    os.environ["STAGEWARDEN_SKIP_BROWSER"] = original_browser

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("openai"), "lavoro")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertIn('"refresh_token":"refresh-token-123"', loaded.secret)
            self.assertIn("Device code login completed.", rendered)

    def test_interactive_shell_rejects_interactive_claude_login(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("account login claude lavoro\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Interactive login is not supported for model 'claude'.", rendered)
            self.assertIn("Use ANTHROPIC_API_KEY", rendered)

    def test_interactive_shell_can_import_claude_credentials_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            credentials = root / ".credentials.json"
            credentials.write_text('{"auth_token":"claude-subscription-token","api_key":"console-key"}', encoding="utf-8")
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO(f"account import claude lavoro {credentials}\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("claude", "lavoro")
            finally:
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("claude"), "lavoro")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertIn('"auth_token":"claude-subscription-token"', loaded.secret)
            self.assertIn("Imported credentials for claude:lavoro", rendered)

    def test_interactive_shell_supports_caveman_alias_help(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO("caveman help\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Caveman commands:", rendered)
            self.assertIn("/caveman review", rendered)

    def test_interactive_shell_caveman_help_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir), max_steps=1)
            input_stream = StringIO("help caveman\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Caveman commands:", rendered)
            self.assertIn("/caveman [lite|full|ultra|wenyan-lite|wenyan|wenyan-ultra]", rendered)
            self.assertIn("$caveman ...", rendered)
            self.assertIn("@caveman ...", rendered)
            self.assertIn("/caveman help", rendered)
            self.assertIn("/caveman commit", rendered)
            self.assertIn("/caveman review", rendered)
            self.assertIn("/caveman compress <file>", rendered)
            self.assertIn("stop caveman", rendered)
            self.assertIn("talk like caveman", rendered)

    def test_interactive_shell_persists_model_block_until_datetime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("model block openai until 2026-05-01T18:30\nmodels\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual((prefs.blocked_until_by_model or {}).get("openai"), "2026-05-01T18:30")
            self.assertIn("blocked-until=2026-05-01T18:30", rendered)

    def test_interactive_shell_status_and_mode_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_title": "Resume 3. Validate result",
                "current_step_status": "in_progress",
                "latest_observation": "implementation completed, wet-run pending",
                "plan_status": "step-1:completed,step-2:completed,step-3:in_progress",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "risk_register": [{"risk": "Regression from patch execution", "status": "open"}],
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "validation pending"}],
                "quality_register": [{"step_id": "step-2", "status": "passed", "evidence": "file updated"}],
                "lessons_log": [{"step_id": "step-2", "type": "success", "lesson": "file update pattern is reusable"}],
                "exception_plan": ["review boundary for step-3", "prepare corrective action"],
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect tests", "status": "completed", "validation": "Real command output captured."},
                    {"step_id": "step-2", "title": "Patch implementation", "status": "completed", "validation": "Files changed and verified."},
                    {"step_id": "step-3", "title": "Validate result", "status": "in_progress", "validation": "Wet-run tests pass."},
                ],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "status\nhandoff\ntodo\nboundary\nrisks\nissues\nquality\nexception\nlessons\n"
                "mode caveman ultra\nstatus\nmode normal\nstatus\nexit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Stagewarden status:", rendered)
            self.assertIn("mode: normal", rendered)
            self.assertIn("Permission settings:", rendered)
            self.assertIn("workspace mode: default", rendered)
            self.assertIn("effective mode: default", rendered)
            self.assertIn("handoff: .stagewarden_handoff.json", rendered)
            self.assertIn("Handoff summary:", rendered)
            self.assertIn("Operational posture:", rendered)
            self.assertIn("governance=residual", rendered)
            self.assertIn("stage_health: at_risk", rendered)
            self.assertIn("recovery_state: none", rendered)
            self.assertIn("next_action: continue step-3", rendered)
            self.assertIn("active_stage: step-3 [in_progress]", rendered)
            self.assertIn("implementation_backlog_open: 1", rendered)
            self.assertIn("implementation_backlog_blocked: 0", rendered)
            self.assertIn("git_boundary: baseline=abc123 current=def456", rendered)
            self.assertIn("boundary_decision: continue_current_stage", rendered)
            self.assertIn("Project handoff:", rendered)
            self.assertIn("Stage view:", rendered)
            self.assertIn("Implementation backlog:", rendered)
            self.assertIn("closed_stages: step-1, step-2", rendered)
            self.assertIn("active_stage: step-3 [in_progress]", rendered)
            self.assertIn("git_boundary: baseline=abc123 current=def456", rendered)
            self.assertIn("pid_boundary: project_status=executing", rendered)
            self.assertIn("stage_health: at_risk", rendered)
            self.assertIn("recovery_state: none", rendered)
            self.assertIn("boundary_decision: continue_current_stage", rendered)
            self.assertIn("next_action: continue step-3", rendered)
            self.assertIn("registers: risks=1 issues=1 quality=1 lessons=1 backlog=3", rendered)
            self.assertIn("register_status: risks_open=1 risks_closed=0 issues_open=1 issues_closed=0 quality_open=1 quality_accepted=0", rendered)
            self.assertIn("backlog_status: ready=0 planned=0 in_progress=1 blocked=0 done=2", rendered)
            self.assertIn("[done] step-1 :: Inspect tests | validation=Real command output captured.", rendered)
            self.assertIn("[done] step-2 :: Patch implementation | validation=Files changed and verified.", rendered)
            self.assertIn("[in_progress] step-3 :: Validate result | validation=Wet-run tests pass.", rendered)
            self.assertIn("Boundary recommendation:", rendered)
            self.assertIn("Risk register:", rendered)
            self.assertIn("Issue register:", rendered)
            self.assertIn("Quality register:", rendered)
            self.assertIn("Exception plan:", rendered)
            self.assertIn("Lessons log:", rendered)
            self.assertIn("Regression from patch execution", rendered)
            self.assertIn("validation pending", rendered)
            self.assertIn("file updated", rendered)
            self.assertIn("review boundary for step-3", rendered)
            self.assertIn("file update pattern is reusable", rendered)
            self.assertIn("Caveman mode active. Level: ultra.", rendered)
            self.assertIn("mode: caveman ultra", rendered)
            self.assertIn("Caveman mode disabled.", rendered)
            self.assertFalse((root / ".stagewarden_caveman.json").exists())

    def test_interactive_shell_renders_overview_and_board_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_title": "Validate result",
                "current_step_status": "in_progress",
                "latest_observation": "wet-run pending",
                "plan_status": "step-1:completed,step-2:completed,step-3:in_progress",
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "validation pending", "status": "open"}],
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("overview\nboard\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Workspace overview:", rendered)
            self.assertIn("recommended_authorization: review", rendered)
            self.assertIn("Board review:", rendered)
            self.assertIn("boundary_decision: continue_current_stage", rendered)

    def test_interactive_shell_renders_health_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "closed",
                "current_step_id": "step-3",
                "current_step_title": "Validate result",
                "current_step_status": "completed",
                "latest_observation": "wet-run passed",
                "plan_status": "step-1:completed,step-2:completed,step-3:completed",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("health\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Health check:", rendered)
            self.assertIn("ready: true", rendered)
            self.assertIn("recommended_authorization: close", rendered)

    def test_interactive_shell_renders_report_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-3",
                "current_step_title": "Validate result",
                "current_step_status": "in_progress",
                "latest_observation": "wet-run pending",
                "plan_status": "step-1:completed,step-2:completed,step-3:in_progress",
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "validation pending", "status": "open"}],
                "implementation_backlog": [
                    {"step_id": "next-step", "title": "add release note", "status": "ready", "validation": "release note written"},
                ],
                "lessons_log": [
                    {"type": "success", "step_id": "step-2", "lesson": "reuse the stable patch pattern"},
                ],
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("report\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Project report:", rendered)
            self.assertIn("recommended_authorization: review", rendered)
            self.assertIn("Backlog preview:", rendered)
            self.assertIn("add release note", rendered)

    def test_interactive_shell_resume_show_uses_current_handoff_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-7",
                "current_step_title": "Validate",
                "current_step_status": "in_progress",
                "latest_observation": "wet-run pending",
                "plan_status": "step-7:in_progress",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("resume --show\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Resume target:", rendered)
            self.assertIn("- task: fix failing tests", rendered)
            self.assertIn("- current_step: step-7", rendered)
            self.assertIn("active_stage: step-7 [in_progress]", rendered)

    def test_interactive_shell_resume_context_shows_latest_execution_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=5,
                step_id="step-7",
                model="openai",
                account="work",
                variant="gpt-5.4-mini",
                action_type="write_file",
                action_signature="write patch",
                success=False,
                observation="needs retry after validation mismatch",
                error_type="invalid_output",
            )
            memory.record_tool_transcript(
                iteration=5,
                step_id="step-7",
                tool="files",
                action_type="write_file",
                success=False,
                summary="patch validation failed",
                duration_ms=245,
                error_type="invalid_output",
            )
            memory.save(root / ".stagewarden_memory.json")
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-7",
                "current_step_title": "Validate",
                "current_step_status": "in_progress",
                "latest_observation": "wet-run pending",
                "plan_status": "step-7:in_progress",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "entries": [
                    {
                        "phase": "git_snapshot",
                        "iteration": 5,
                        "step_id": "step-7",
                        "step_status": "failed",
                        "model": "openai",
                        "action_type": "git_snapshot",
                        "summary": "stagewarden: step step-7 failed [stage=at_risk boundary=review]",
                        "detail": "",
                        "git_head": "ff00aa1",
                        "timestamp": "2026-04-20T10:45:00+00:00",
                    }
                ],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("resume context\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Resume context:", rendered)
            self.assertIn("- task: fix failing tests", rendered)
            self.assertIn("- latest_model_attempt: step=step-7 action=write_file status=failed:invalid_output", rendered)
            self.assertIn("- latest_route: model=openai account=work variant=gpt-5.4-mini", rendered)
            self.assertIn("- latest_tool_evidence: tool=files action=write_file status=failed:invalid_output duration_ms=245", rendered)
            self.assertIn("- latest_git_snapshot: ff00aa1 :: stagewarden: step step-7 failed [stage=at_risk boundary=review]", rendered)

    def test_interactive_shell_resume_clear_archives_handoff_without_git_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-7",
                "current_step_status": "in_progress",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("resume --clear\nhandoff\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            archives = list(root.glob(".stagewarden_handoff.archive.*.json"))

            self.assertEqual(code, 0)
            self.assertEqual(len(archives), 1)
            self.assertIn("Archived handoff", rendered)
            self.assertIn("No active handoff context.", rendered)
            archived = json.loads(archives[0].read_text(encoding="utf-8"))
            self.assertEqual(archived.get("current_step_id"), "step-7")

    def test_interactive_shell_resume_executes_wet_run_from_persisted_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = write_success_stub(root)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "create a file named resumed.txt",
                "status": "executing",
                "current_step_id": "step-2",
                "current_step_title": "2. Implement create a file named resumed.txt",
                "current_step_status": "in_progress",
                "latest_observation": "inspection completed, implementation pending",
                "plan_status": "step-1:completed,step-2:in_progress,step-3:planned",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                config = AgentConfig(workspace_root=root, max_steps=10)
                input_stream = StringIO("resume\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            rendered = output_stream.getvalue()
            updated = json.loads((root / ".stagewarden_handoff.json").read_text(encoding="utf-8"))
            self.assertEqual(code, 0)
            self.assertTrue((root / "resumed.txt").exists())
            self.assertIn("Resumed from handoff step step-2.", rendered)
            self.assertIn("Agent run completed.", rendered)
            self.assertIn("Cost and budget:", rendered)
            self.assertEqual(updated.get("status"), "closed")

    def test_interactive_shell_exports_runtime_handoff_markdown_with_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "HANDOFF.md").write_text("# Stagewarden Handoff\n\nManual roadmap stays.\n", encoding="utf-8")
            memory = MemoryStore()
            memory.record_attempt(
                iteration=2,
                step_id="step-2",
                model="openai",
                account="work",
                variant="gpt-5.4-mini",
                action_type="shell",
                action_signature="pytest -q",
                success=False,
                observation="auth_token=secret-should-be-redacted after command failure",
                error_type="runtime",
            )
            memory.record_tool_transcript(
                iteration=2,
                step_id="step-2",
                tool="shell",
                action_type="shell",
                success=False,
                summary="pytest failed",
                detail="Bearer abcdefghijklmnopqrstuvwxyz123456 should be redacted",
                duration_ms=4321,
                error_type="runtime",
            )
            memory.save(root / ".stagewarden_memory.json")
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-2",
                "current_step_title": "2. Implement fix",
                "current_step_status": "in_progress",
                "latest_observation": "access_token=secret-token-123 should not leak",
                "plan_status": "step-1:completed,step-2:in_progress,step-3:planned",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect", "status": "done", "validation": "checked"},
                    {"step_id": "step-2", "title": "Implement", "status": "in_progress", "validation": "wet-run"},
                ],
                "issue_register": [{"step_id": "step-2", "severity": "medium", "summary": "Bearer abcdefghijklmnopqrstuvwxyz123456 should be redacted", "status": "open"}],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [
                    {
                        "phase": "git_snapshot",
                        "iteration": 2,
                        "step_id": "step-2",
                        "step_status": "failed",
                        "model": "openai",
                        "action_type": "git_snapshot",
                        "summary": "stagewarden: step step-2 failed [stage=exception boundary=escalate]",
                        "detail": "",
                        "git_head": "ff00aa1",
                        "timestamp": "2026-04-18T18:35:00+00:00",
                    }
                ],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("handoff export\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Exported runtime handoff to HANDOFF.md.", rendered)
            exported = (root / "HANDOFF.md").read_text(encoding="utf-8")
            self.assertIn("Manual roadmap stays.", exported)
            self.assertIn("<!-- STAGEWARDEN_RUNTIME_HANDOFF_START -->", exported)
            self.assertIn("## Runtime Handoff Export", exported)
            self.assertIn("- task: fix failing tests", exported)
            self.assertIn("- recovery_state: none", exported)
            self.assertIn("### Execution Resume Context", exported)
            self.assertIn("- latest_model_attempt: step=step-2 action=shell status=failed:runtime", exported)
            self.assertIn("- latest_route: model=openai account=work variant=gpt-5.4-mini", exported)
            self.assertIn("- latest_tool_evidence: tool=shell action=shell status=failed:runtime duration_ms=4321", exported)
            self.assertIn("- latest_git_snapshot: ff00aa1 :: stagewarden: step step-2 failed [stage=exception boundary=escalate]", exported)
            self.assertIn("Implementation backlog:", exported)
            self.assertNotIn("secret-token-123", exported)
            self.assertNotIn("secret-should-be-redacted", exported)
            self.assertNotIn("abcdefghijklmnopqrstuvwxyz123456", exported)
            self.assertIn("Bearer [REDACTED]", exported)

    def test_interactive_shell_manages_permission_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "permission mode plan\n"
                "permission allow shell:git status\n"
                "permission ask file:secret.txt\n"
                "permission deny shell:rm\n"
                "permissions\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Permission mode set to plan.", rendered)
            self.assertIn("Added allow rule: shell:git status", rendered)
            self.assertIn("Added ask rule: file:secret.txt", rendered)
            self.assertIn("Added deny rule: shell:rm", rendered)
            self.assertIn("workspace mode: plan", rendered)
            self.assertIn("workspace allow: shell:git status", rendered)
            self.assertIn("workspace ask: file:secret.txt", rendered)
            self.assertIn("workspace deny: shell:rm", rendered)
            self.assertIn("effective mode: plan", rendered)
            payload = json.loads((root / ".stagewarden_settings.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["permissions"]["defaultMode"], "plan")

    def test_interactive_shell_mode_aliases_manage_permission_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "mode plan\n"
                "status\n"
                "mode auto\n"
                "mode accept-edits\n"
                "mode dont-ask\n"
                "mode default\n"
                "permissions\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Permission mode set to plan.", rendered)
            self.assertIn("Permission mode set to auto.", rendered)
            self.assertIn("Permission mode set to accept_edits.", rendered)
            self.assertIn("Permission mode set to dont_ask.", rendered)
            self.assertIn("Permission mode set to default.", rendered)
            self.assertIn("effective mode: plan", rendered)
            self.assertIn("Permission settings:", rendered)
            self.assertIn("workspace mode: default", rendered)
            self.assertIn("effective mode: default", rendered)
            payload = json.loads((root / ".stagewarden_settings.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["permissions"]["defaultMode"], "default")

    def test_interactive_shell_manages_session_permission_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "permission session mode plan\n"
                "permission session allow shell:git status\n"
                "permissions\n"
                "permission session reset\n"
                "permissions\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            self.assertEqual(code, 0)
            self.assertIn("Session permission mode set to plan.", rendered)
            self.assertIn("Added session allow rule: shell:git status", rendered)
            self.assertIn("session mode: plan", rendered)
            self.assertIn("session allow: shell:git status", rendered)
            self.assertIn("effective mode: plan", rendered)
            self.assertIn("Session permission settings reset.", rendered)
            self.assertIn("session mode: none", rendered)
            self.assertIn("effective mode: default", rendered)
            self.assertFalse((root / ".stagewarden_settings.json").exists())

    def test_boundary_uses_exception_plan_when_project_is_in_exception(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "exception",
                "current_step_id": "step-2",
                "current_step_title": "Resume 2. Implement fix",
                "current_step_status": "exception",
                "latest_observation": "tests still failing after patch",
                "plan_status": "step-1:completed,step-2:exception,step-3:pending",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "issue_register": [{"step_id": "step-2", "severity": "high", "summary": "tests still failing", "status": "open"}],
                "exception_plan": ["review failing tests", "prepare corrective patch"],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_boundary(config)
            self.assertIn("stage_health: exception", rendered)
            self.assertIn("recovery_state: exception_active", rendered)
            self.assertIn("next_action: execute exception plan and re-baseline the current stage", rendered)
            self.assertIn("review_boundary:exception_plan", rendered)

    def test_handoff_marks_backlog_as_blocked_when_high_severity_issue_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "step-2",
                "current_step_title": "Resume 2. Implement fix",
                "current_step_status": "failed",
                "latest_observation": "test environment still blocked",
                "plan_status": "step-1:completed,step-2:failed,step-3:pending",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "issue_register": [{"step_id": "step-2", "severity": "high", "summary": "critical blocker remains", "status": "open"}],
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect tests", "status": "done", "validation": "Real command output captured."},
                    {"step_id": "step-2", "title": "Patch implementation", "status": "blocked", "validation": "Blocking issue resolved and wet-run passes."},
                    {"step_id": "step-3", "title": "Validate result", "status": "planned", "validation": "Wet-run tests pass."},
                ],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_handoff(config)
            self.assertIn("stage_health: exception", rendered)
            self.assertIn("recovery_state: exception_active", rendered)
            self.assertIn("next_action: execute exception plan and re-baseline the current stage", rendered)
            self.assertIn("implementation_backlog_blocked: 1", rendered)
            self.assertIn("backlog_status: ready=0 planned=1 in_progress=0 blocked=1 done=1", rendered)
            self.assertIn("[blocked] step-2 :: Patch implementation | validation=Blocking issue resolved and wet-run passes.", rendered)

    def test_boundary_marks_recovery_lane_as_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "exception",
                "current_step_id": "recovery-step-1",
                "current_step_title": "Recovery 1. Review failing tests",
                "current_step_status": "in_progress",
                "latest_observation": "reviewing corrective action",
                "plan_status": "step-1:completed,step-2:failed,recovery-step-1:in_progress,recovery-step-2:planned,step-3:planned",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "exception_plan": ["review failing tests", "prepare corrective patch"],
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect tests", "status": "done", "validation": "Real command output captured."},
                    {"step_id": "step-2", "title": "Patch implementation", "status": "blocked", "validation": "Blocking issue resolved."},
                    {"step_id": "recovery-step-1", "title": "Recovery 1", "status": "in_progress", "validation": "Wet-run confirms recovery."},
                    {"step_id": "recovery-step-2", "title": "Recovery 2", "status": "planned", "validation": "Wet-run confirms recovery."},
                    {"step_id": "step-3", "title": "Validate result", "status": "planned", "validation": "Wet-run tests pass."},
                ],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_boundary(config)
            self.assertIn("recovery_state: recovery_active", rendered)
            self.assertIn("next_action: execute recovery lane and confirm wet-run before re-baseline", rendered)

    def test_boundary_marks_recovery_lane_as_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "executing",
                "current_step_id": "recovery-step-2",
                "current_step_title": "Recovery 2. Prepare corrective patch",
                "current_step_status": "completed",
                "latest_observation": "recovery wet-run completed",
                "plan_status": "step-1:completed,step-2:failed,recovery-step-1:completed,recovery-step-2:completed,step-3:ready",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "implementation_backlog": [
                    {"step_id": "step-1", "title": "Inspect tests", "status": "done", "validation": "Real command output captured."},
                    {"step_id": "step-2", "title": "Patch implementation", "status": "blocked", "validation": "Blocking issue resolved."},
                    {"step_id": "recovery-step-1", "title": "Recovery 1", "status": "done", "validation": "Wet-run confirms recovery."},
                    {"step_id": "recovery-step-2", "title": "Recovery 2", "status": "done", "validation": "Wet-run confirms recovery."},
                    {"step_id": "step-3", "title": "Validate result", "status": "ready", "validation": "Wet-run tests pass."},
                ],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_boundary(config)
            self.assertIn("recovery_state: recovery_cleared", rendered)
            self.assertIn("next_action: clear exception controls and resume planned stages", rendered)

    def test_boundary_blocks_project_close_when_open_issues_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "closed",
                "current_step_id": "step-3",
                "current_step_title": "3. Validate",
                "current_step_status": "completed",
                "latest_observation": "tests passed but one release issue remains open",
                "plan_status": "step-1:completed,step-2:completed,step-3:completed",
                "git_head": "def456",
                "git_head_baseline": "abc123",
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "release note missing", "status": "open"}],
                "updated_at": "2026-04-18T18:30:00+00:00",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            config = AgentConfig(workspace_root=root, max_steps=1)
            rendered = _render_boundary(config)
            self.assertIn("review_boundary:open_issues", rendered)
            self.assertIn("issues_open=1 issues_closed=0", rendered)

    def test_board_review_recommends_close_for_clean_closed_project(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "release project",
                "status": "closed",
                "current_step_id": "step-3",
                "current_step_status": "completed",
                "plan_status": "step-1:completed,step-2:completed,step-3:completed",
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            completed = run_main_capture(root, "board", "--json")
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["recommended_authorization"], "close")

    def test_board_review_recommends_review_when_open_issues_remain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "release project",
                "status": "closed",
                "current_step_id": "step-3",
                "current_step_status": "completed",
                "plan_status": "step-1:completed,step-2:completed,step-3:completed",
                "issue_register": [{"step_id": "step-3", "severity": "medium", "summary": "release note missing", "status": "open"}],
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            completed = run_main_capture(root, "stage review", "--json")
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["recommended_authorization"], "review")

    def test_board_review_recommends_recover_when_recovery_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = {
                "_format": "stagewarden_project_handoff",
                "_version": 1,
                "task": "fix failing tests",
                "status": "exception",
                "current_step_id": "recovery-step-1",
                "current_step_status": "in_progress",
                "plan_status": "step-1:completed,step-2:failed,recovery-step-1:in_progress",
                "exception_plan": ["review failing tests"],
                "entries": [],
            }
            (root / ".stagewarden_handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
            completed = run_main_capture(root, "board", "--json")
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["recommended_authorization"], "recover")

    def test_interactive_shell_can_query_git_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            agent = Agent(config)
            (root / "tracked.txt").write_text("tracked\n")
            self.assertTrue(agent.git.commit_if_changed("test: tracked").ok)

            input_stream = StringIO("git status\ngit log 5\ngit history tracked.txt 5\ngit show --stat HEAD\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("test: tracked", rendered)
            self.assertIn("tracked.txt", rendered)
            self.assertIn("Session closed.", rendered)


if __name__ == "__main__":
    unittest.main()
