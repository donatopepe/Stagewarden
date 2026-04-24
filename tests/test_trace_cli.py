from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import subprocess
import tempfile
import threading
import unittest
from io import StringIO
from pathlib import Path

from stagewarden.agent import Agent
from stagewarden.config import AgentConfig
from stagewarden.ljson import decode, load_file
from stagewarden.memory import MemoryStore
from stagewarden.main import _interactive_completion_candidates, _render_boundary, _render_handoff, run_interactive_shell
from stagewarden.modelprefs import ModelPreferences
from stagewarden.project_handoff import ProjectHandoff
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
            self.assertIn("Use `/help` or `/help <topic>`", rendered)
            self.assertIn("Topics:", rendered)
            self.assertIn("help models", rendered)
            self.assertIn("help accounts", rendered)
            self.assertIn("help permissions", rendered)
            self.assertIn("Fast examples:", rendered)
            self.assertIn("Provider configuration:", rendered)
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
            self.assertIn("- Runtime: os=", completed.stdout)
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
            self.assertIn("runtime", payload)
            self.assertIn(payload["runtime"]["os_family"], {"macos", "linux", "windows", "unknown"})
            self.assertIn("recommended_shell", payload["runtime"])
            self.assertIn("bash", payload["runtime"]["shells"])
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
            self.assertIn("focus", payload)
            self.assertEqual(payload["focus"]["task"], "fix failing tests")

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
            self.assertIn("active_route", payload)
            self.assertTrue(payload["resume_ready"])
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
            self.assertIn("provider_limits", payload)
            self.assertIn("permissions", payload)
            self.assertIn("runtime", payload)
            self.assertIn("shell_backend", payload)
            self.assertIn("focus", payload)
            self.assertEqual(payload["focus"]["task"], "fix failing tests")
            self.assertEqual(payload["focus"]["current_step"], "step-3")
            self.assertIn(payload["runtime"]["os_family"], {"macos", "linux", "windows", "unknown"})
            self.assertIn("recommended_shell", payload["runtime"])
            self.assertIn("remediations", payload)
            self.assertTrue(any(item["code"] == "roles" for item in payload["remediations"]))

    def test_status_full_cli_json_exposes_dashboard_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "local"]
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.last_limit_message_by_model = {"chatgpt": "Usage limit reached at 91%. Try again at 8:05 PM."}
            prefs.set_model_limit_snapshot(
                "chatgpt",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T18:30",
                    "rate_limit_type": "usage_limit",
                    "utilization": 91,
                    "captured_at": "2000-01-01T17:30",
                    "raw_message": "Usage limit reached at 91%. Try again at 8:05 PM.",
                },
            )
            prefs.save(root / ".stagewarden_models.json")
            completed = run_main_capture(root, "status", "--full", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "status")
            self.assertEqual(payload["view"], "full")
            self.assertIn("identity", payload)
            self.assertIn("limits", payload)
            self.assertIn("git", payload)
            self.assertIn("runtime", payload)
            self.assertIn("shell_backend", payload)
            self.assertIn("focus", payload)
            self.assertIn("recommended_shell", payload["runtime"])
            self.assertIn("quality_gates", payload)
            self.assertIn("remediations", payload)
            self.assertTrue(payload["quality_gates"]["wet_run_required"])
            self.assertFalse(payload["quality_gates"]["dry_run_valid_checkpoint"])
            limits = {item["provider"]: item for item in payload["limits"]}
            self.assertEqual(limits["chatgpt"]["utilization"], 91.0)
            self.assertEqual(limits["chatgpt"]["rate_limit_type"], "usage_limit")

    def test_status_full_cli_renders_remediations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "status", "--full")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Stagewarden full status:", completed.stdout)
            self.assertIn("Remediations:", completed.stdout)
            self.assertIn("roles", completed.stdout)

    def test_shell_backend_cli_can_set_and_report_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            set_completed = run_main_capture(root, "shell backend use zsh")

            self.assertEqual(set_completed.returncode, 0, set_completed.stderr)
            self.assertIn("Shell backend set to zsh.", set_completed.stdout)

            completed = run_main_capture(root, "shell backend", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "shell backend")
            self.assertEqual(payload["configured"], "zsh")
            self.assertEqual(payload["selected"], "zsh")

    def test_status_json_reports_configured_shell_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / ".stagewarden_settings.json").write_text(
                json.dumps({"shell": {"backend": "zsh"}}),
                encoding="utf-8",
            )

            completed = run_main_capture(root, "status", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertIn("shell_backend", payload)
            self.assertEqual(payload["shell_backend"]["configured"], "zsh")

    def test_status_surfaces_latest_handoff_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")
            handoff.record_action(
                phase="project_start_blocked",
                summary="Project start blocked until brief is complete.",
                task="project start",
                git_head="abc123",
                details={"missing_fields": ["scope", "expected_outputs"]},
            )
            handoff.save(root / ".stagewarden_handoff.json")

            completed = run_main_capture(root, "status")
            json_completed = run_main_capture(root, "status", "--json")
            statusline_completed = run_main_capture(root, "statusline", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("latest_handoff_action: phase=project_start_blocked", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            latest = payload["focus"]["latest_handoff_action"]
            self.assertEqual(latest["phase"], "project_start_blocked")
            self.assertEqual(latest["task"], "project start")
            self.assertEqual(latest["git_head"], "abc123")
            self.assertEqual(latest["details"]["missing_fields"], ["scope", "expected_outputs"])

            self.assertEqual(statusline_completed.returncode, 0, statusline_completed.stderr)
            statusline = json.loads(statusline_completed.stdout)
            self.assertEqual(statusline["latest_handoff_action"]["phase"], "project_start_blocked")

    def test_preflight_reports_windows_shell_readiness_warning(self) -> None:
        from unittest.mock import patch
        from stagewarden.main import _configure_readonly_agent_for_workspace, _preflight_report

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root)
            runtime = {
                "os_family": "windows",
                "platform_system": "Windows",
                "platform_release": "11",
                "platform_machine": "x86_64",
                "cwd": str(root),
                "default_shell": "powershell",
                "path_separator": "\\",
                "line_ending": "crlf",
                "shells": {
                    "bash": {"available": False, "path": None, "version": ""},
                    "zsh": {"available": False, "path": None, "version": ""},
                    "powershell": {"available": True, "path": "powershell", "version": "5.1"},
                    "cmd": {"available": True, "path": "cmd", "version": ""},
                },
                "recommended_shell": "powershell",
            }
            with patch("stagewarden.main.detect_runtime_capabilities", return_value=runtime):
                agent = _configure_readonly_agent_for_workspace(config)
                payload = _preflight_report(agent, config)

            codes = {item["code"] for item in payload["remediations"]}
            self.assertIn("windows_shell_readiness", codes)

    def test_statusline_cli_json_exposes_compact_runtime_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "claude", "local"]
            prefs.add_account("claude", "team")
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.set_model_limit_snapshot(
                "chatgpt",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T18:30",
                    "rate_limit_type": "usage_limit",
                    "utilization": 91,
                    "captured_at": "2000-01-01T17:30",
                    "raw_message": "Usage limit reached at 91%. Try again at 8:05 PM.",
                },
            )
            prefs.block_account("claude", "team", "2026-05-01T19:00")
            prefs.set_account_limit_snapshot(
                "claude",
                "team",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T19:00",
                    "rate_limit_type": "five_hour_sonnet",
                    "captured_at": "2026-05-01T18:00",
                    "raw_message": "Claude usage limited until 2026-05-01T19:00.",
                },
            )
            prefs.save(root / ".stagewarden_models.json")
            completed = run_main_capture(root, "statusline", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "statusline")
            self.assertIn("workspace", payload)
            self.assertIn("model", payload)
            self.assertIn("rate_limits", payload)
            self.assertIn("rate_limits_summary", payload)
            self.assertIn("context_window", payload)
            limits = {item["provider"]: item for item in payload["rate_limits"]}
            self.assertEqual(limits["chatgpt"]["used_percentage"], 91.0)
            self.assertEqual(limits["chatgpt"]["resets_at"], "2026-05-01T18:30")
            self.assertEqual(limits["chatgpt"]["rate_limit_type"], "usage_limit")
            self.assertTrue(limits["chatgpt"]["stale"])
            self.assertEqual(limits["claude"]["blocked_accounts"], 1)
            self.assertEqual(payload["rate_limits_summary"]["blocked_models"], ["chatgpt"])
            self.assertEqual(payload["rate_limits_summary"]["stale_models"], ["chatgpt"])
            self.assertEqual(payload["rate_limits_summary"]["blocked_accounts"], ["claude:team"])

    def test_statusline_cli_json_exposes_context_usage_from_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="chatgpt",
                action_type="complete",
                action_signature="{}",
                success=True,
                observation="ok",
                input_tokens=400,
                output_tokens=100,
                context_window_size=2000,
            )
            memory.save(root / ".stagewarden_memory.json")

            completed = run_main_capture(root, "statusline", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["context_window"]["total_input_tokens"], 400)
            self.assertEqual(payload["context_window"]["total_output_tokens"], 100)
            self.assertEqual(payload["context_window"]["current_usage"], 500)
            self.assertEqual(payload["context_window"]["used_percentage"], 25.0)

    def test_auth_status_chatgpt_uses_codex_without_token_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            codex = bin_dir / "codex"
            codex.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = login ] && [ \"$2\" = status ]; then\n"
                "  echo 'Logged in using ChatGPT' >&2\n"
                "  exit 0\n"
                "fi\n"
                "exit 2\n",
                encoding="utf-8",
            )
            codex.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
            try:
                completed = run_main_capture(root, "auth status chatgpt", "--json")
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["provider"], "chatgpt")
            self.assertTrue(payload["logged_in"])
            self.assertEqual(payload["auth_method"], "chatgpt")
            self.assertNotIn("token", completed.stdout.lower())

    def test_auth_status_claude_uses_json_status_without_token_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            claude = bin_dir / "claude"
            claude.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = auth ] && [ \"$2\" = status ]; then\n"
                "  printf '{\"loggedIn\":false,\"authMethod\":\"none\",\"apiProvider\":\"firstParty\"}'\n"
                "  exit 1\n"
                "fi\n"
                "exit 2\n",
                encoding="utf-8",
            )
            claude.chmod(0o755)
            old_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{bin_dir}{os.pathsep}{old_path}"
            try:
                completed = run_main_capture(root, "auth status claude", "--json")
            finally:
                os.environ["PATH"] = old_path

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["provider"], "claude")
            self.assertFalse(payload["logged_in"])
            self.assertEqual(payload["auth_method"], "none")
            self.assertEqual(payload["api_provider"], "firstParty")
            self.assertNotIn("token", completed.stdout.lower())

    def test_status_cli_json_reports_provider_limit_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "claude", "local"]
            prefs.preferred_model = "chatgpt"
            prefs.add_account("chatgpt", "work")
            prefs.add_account("claude", "team")
            prefs.set_active_account("chatgpt", "work")
            prefs.set_active_account("claude", "team")
            prefs.set_variant("chatgpt", "gpt-5.3-codex")
            prefs.set_variant("claude", "sonnet")
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.last_limit_message_by_model = {"chatgpt": "You've hit your usage limit. Try again at 8:05 PM."}
            prefs.set_model_limit_snapshot(
                "chatgpt",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T18:30",
                    "rate_limit_type": "usage_limit",
                    "utilization": 91,
                    "captured_at": "2000-01-01T17:30",
                    "raw_message": "You've hit your usage limit. Try again at 8:05 PM.",
                },
            )
            prefs.block_account("claude", "team", "2026-05-01T19:00")
            prefs.last_limit_message_by_account = {"claude:team": "Claude usage limited until 2026-05-01T19:00."}
            prefs.set_account_limit_snapshot(
                "claude",
                "team",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T19:00",
                    "primary_window": "five_hour",
                    "secondary_window": "sonnet",
                    "rate_limit_type": "five_hour_sonnet",
                    "captured_at": "2026-05-01T18:00",
                    "raw_message": "Claude usage limited until 2026-05-01T19:00.",
                },
            )
            prefs.save(root / ".stagewarden_models.json")
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-1",
                model="chatgpt",
                account="work",
                variant="gpt-5.3-codex",
                action_type="shell",
                action_signature="pytest",
                success=False,
                observation="usage limit hit",
                error_type="runtime",
            )
            memory.record_attempt(
                iteration=2,
                step_id="step-2",
                model="claude",
                account="team",
                variant="sonnet",
                action_type="write_file",
                action_signature="patch",
                success=True,
                observation="patch applied",
            )
            memory.save(root / ".stagewarden_memory.json")
            completed = run_main_capture(root, "status", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            providers = {item["provider"]: item for item in payload["provider_limits"]["providers"]}
            self.assertEqual(providers["chatgpt"]["blocked_until"], "2026-05-01T18:30")
            self.assertEqual(providers["chatgpt"]["active_account"], "work")
            self.assertEqual(providers["chatgpt"]["last_error_reason"], "usage_limit")
            self.assertIn("usage limit", providers["chatgpt"]["last_limit_message"].lower())
            self.assertEqual(providers["chatgpt"]["limit_snapshot"]["utilization"], 91.0)
            self.assertEqual(providers["chatgpt"]["limit_snapshot"]["rate_limit_type"], "usage_limit")
            self.assertEqual(providers["chatgpt"]["last_attempt"]["account"], "work")
            self.assertEqual(providers["claude"]["active_account"], "none")
            self.assertEqual(providers["claude"]["last_success"]["account"], "team")
            self.assertEqual(providers["claude"]["blocked_accounts"][0]["name"], "team")
            self.assertEqual(providers["claude"]["blocked_accounts"][0]["blocked_until"], "2026-05-01T19:00")
            self.assertEqual(providers["claude"]["blocked_accounts"][0]["last_limit_reason"], "usage_limit")
            self.assertIn("usage limited", providers["claude"]["blocked_accounts"][0]["last_limit_message"].lower())
            self.assertEqual(
                providers["claude"]["blocked_accounts"][0]["limit_snapshot"]["rate_limit_type"],
                "five_hour_sonnet",
            )
            self.assertIn("limits_summary", payload)
            self.assertEqual(payload["limits_summary"]["blocked_models"], ["chatgpt"])
            self.assertEqual(payload["limits_summary"]["stale_models"], ["chatgpt"])
            self.assertEqual(payload["limits_summary"]["blocked_accounts"], ["claude:team"])

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

    def test_model_limits_cli_json_outputs_persisted_snapshots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "claude"]
            prefs.add_account("claude", "team")
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.last_limit_message_by_model = {"chatgpt": "Usage limit reached at 91%. Try again at 8:05 PM."}
            prefs.set_model_limit_snapshot(
                "chatgpt",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T18:30",
                    "rate_limit_type": "usage_limit",
                    "utilization": 91,
                    "captured_at": "2000-01-01T17:30",
                    "raw_message": "Usage limit reached at 91%. Try again at 8:05 PM.",
                },
            )
            prefs.block_account("claude", "team", "2026-05-01T19:00")
            prefs.last_limit_message_by_account = {
                "claude:team": "Claude Sonnet five-hour usage limited until 2026-05-01T19:00."
            }
            prefs.set_account_limit_snapshot(
                "claude",
                "team",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T19:00",
                    "rate_limit_type": "five_hour_sonnet",
                    "captured_at": "2026-05-01T18:00",
                    "raw_message": "Claude Sonnet five-hour usage limited until 2026-05-01T19:00.",
                },
            )
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(root, "model limits", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "model limits")
            self.assertEqual(payload["summary"]["blocked_models"], ["chatgpt"])
            self.assertEqual(payload["summary"]["blocked_accounts"], ["claude:team"])
            providers = {item["provider"]: item for item in payload["providers"]}
            self.assertEqual(providers["chatgpt"]["utilization"], 91.0)
            self.assertEqual(providers["chatgpt"]["blocked_until"], "2026-05-01T18:30")
            self.assertTrue(providers["chatgpt"]["stale"])
            self.assertEqual(
                providers["claude"]["blocked_accounts"][0]["snapshot"]["rate_limit_type"],
                "five_hour_sonnet",
            )

    def test_model_limit_record_cli_persists_sanitized_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "local"]
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(
                root,
                "model limit-record chatgpt Usage limit reached until 2026-05-01T18:30.",
                "--json",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "model limit-record")
            loaded = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual((loaded.blocked_until_by_model or {})["chatgpt"], "2026-05-01T18:30")
            snapshot = (loaded.provider_limit_snapshot_by_model or {})["chatgpt"]
            self.assertEqual(snapshot["blocked_until"], "2026-05-01T18:30")
            self.assertEqual(snapshot["reason"], "usage_limit")
            self.assertNotIn("token", json.dumps(snapshot).lower())

            cleared = run_main_capture(root, "model limit-clear chatgpt", "--json")
            self.assertEqual(cleared.returncode, 0, cleared.stderr)
            reloaded = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertNotIn("chatgpt", reloaded.blocked_until_by_model or {})
            self.assertNotIn("chatgpt", reloaded.provider_limit_snapshot_by_model or {})

    def test_account_limit_record_cli_persists_sanitized_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["claude", "local"]
            prefs.add_account("claude", "team")
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(
                root,
                "account limit-record claude team Claude Sonnet five-hour usage limited until 2026-05-01T19:00.",
                "--json",
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "account limit-record")
            loaded = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertEqual((loaded.blocked_until_by_account or {})["claude:team"], "2026-05-01T19:00")
            snapshot = (loaded.provider_limit_snapshot_by_account or {})["claude:team"]
            self.assertEqual(snapshot["blocked_until"], "2026-05-01T19:00")
            self.assertEqual(snapshot["rate_limit_type"], "five_hour_sonnet")
            self.assertNotIn("token", json.dumps(snapshot).lower())

            cleared = run_main_capture(root, "account limit-clear claude team", "--json")
            self.assertEqual(cleared.returncode, 0, cleared.stderr)
            reloaded = ModelPreferences.load(root / ".stagewarden_models.json")
            self.assertNotIn("claude:team", reloaded.blocked_until_by_account or {})
            self.assertNotIn("claude:team", reloaded.provider_limit_snapshot_by_account or {})

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
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "local"]
            prefs.preferred_model = "chatgpt"
            prefs.add_account("chatgpt", "work")
            prefs.set_active_account("chatgpt", "work")
            prefs.set_variant("chatgpt", "gpt-5.3-codex")
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.last_limit_message_by_model = {"chatgpt": "You've hit your usage limit. Try again at 8:05 PM."}
            prefs.save(root / ".stagewarden_models.json")
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
                model="chatgpt",
                account="work",
                variant="gpt-5.3-codex",
                action_type="complete",
                action_signature="a",
                success=False,
                observation="usage limit hit",
                error_type="runtime",
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
            self.assertIn("provider_limits", payload)
            providers = {item["provider"]: item for item in payload["provider_limits"]["providers"]}
            self.assertEqual(providers["chatgpt"]["blocked_until"], "2026-05-01T18:30")
            self.assertEqual(providers["chatgpt"]["last_error_reason"], "usage_limit")
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

    def test_preflight_cli_json_output_is_machine_readable_and_read_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "preflight", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "preflight")
            self.assertIn("ready", payload)
            self.assertIn("doctor", payload)
            self.assertIn("runtime", payload)
            self.assertIn("git", payload)
            self.assertIn("roles_check", payload)
            self.assertIn("provider_limits", payload)
            self.assertIn("sources", payload)
            self.assertIn("remediations", payload)
            self.assertFalse((root / ".git").exists())

    def test_preflight_cli_renders_remediations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "preflight")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Stagewarden preflight:", completed.stdout)
            self.assertIn("- ready:", completed.stdout)
            self.assertIn("Remediations:", completed.stdout)
            self.assertIn("roles", completed.stdout)

    def test_report_cli_json_output_is_machine_readable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "claude"]
            prefs.preferred_model = "chatgpt"
            prefs.add_account("chatgpt", "work")
            prefs.set_active_account("chatgpt", "work")
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.last_limit_message_by_model = {"chatgpt": "You've hit your usage limit. Try again at 8:05 PM."}
            prefs.save(root / ".stagewarden_models.json")
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
                step_id="step-3",
                model="chatgpt",
                account="work",
                action_type="complete",
                action_signature="a",
                success=False,
                observation="usage limit hit",
                error_type="runtime",
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
            self.assertIn("provider_limits", payload)
            providers = {item["provider"]: item for item in payload["provider_limits"]["providers"]}
            self.assertEqual(providers["chatgpt"]["blocked_until"], "2026-05-01T18:30")
            self.assertEqual(providers["chatgpt"]["last_error_reason"], "usage_limit")
            self.assertIn("reuse the stable patch pattern", payload["recent_lessons"][0])
            self.assertIn("add release note", payload["backlog_preview"][0])
            self.assertIn("finalize smoke test", payload["backlog_preview"][1])

    def test_interactive_completion_candidates_include_core_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = AgentConfig(workspace_root=Path(tmp_dir))
            matches = _interactive_completion_candidates("/he", config)
            self.assertIn("/help", matches)
            self.assertIn("/health", matches)
            command_matches = _interactive_completion_candidates("/com", config)
            self.assertIn("/commands", command_matches)
            slash_matches = _interactive_completion_candidates("/sla", config)
            self.assertIn("/slash", slash_matches)

    def test_interactive_completion_candidates_include_contextual_provider_role_and_backend_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.accounts_by_model = {"openai": ["work", "personal"]}
            prefs.variant_by_model = {"chatgpt": "gpt-5.4"}
            prefs.save(root / ".stagewarden_models.json")
            config = AgentConfig(workspace_root=root)

            model_matches = _interactive_completion_candidates("/model choose ch", config)
            role_matches = _interactive_completion_candidates("/role configure pro", config)
            backend_matches = _interactive_completion_candidates("/shell backend use po", config)
            account_provider_matches = _interactive_completion_candidates("/account use op", config)
            account_name_matches = _interactive_completion_candidates("/account use openai wo", config)
            variant_matches = _interactive_completion_candidates("/model variant chatgpt gpt-5.", config)
            param_key_matches = _interactive_completion_candidates("/model param set chatgpt", config)
            param_value_matches = _interactive_completion_candidates("/model param set chatgpt reasoning_effort h", config)

            self.assertIn("/model choose chatgpt", model_matches)
            self.assertIn("/role configure project_manager", role_matches)
            self.assertIn("/role configure project_support", role_matches)
            self.assertIn("/shell backend use powershell", backend_matches)
            self.assertIn("/account use openai", account_provider_matches)
            self.assertIn("/account use openai work", account_name_matches)
            self.assertIn("/model variant chatgpt gpt-5.4", variant_matches)
            self.assertIn("/model param set chatgpt reasoning_effort ", param_key_matches)
            self.assertIn("/model param set chatgpt reasoning_effort high", param_value_matches)

    def test_interactive_shell_renders_slash_palette(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "openai"]
            prefs.accounts_by_model = {"openai": ["work"]}
            prefs.active_account_by_model = {"openai": "work"}
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.save(root / ".stagewarden_models.json")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("/slash mo\n/exit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Slash command palette:", rendered)
            self.assertIn("- prefix: /mo", rendered)
            self.assertIn("- enabled_providers: chatgpt, openai", rendered)
            self.assertIn("- active_accounts: openai=work", rendered)
            self.assertIn("- blocked_providers: chatgpt:2026-05-01T18:30", rendered)
            self.assertIn("/models", rendered)
            self.assertIn("/model use", rendered)
            self.assertIn("hint=providers[chatgpt, openai]", rendered)
            self.assertIn("hint=provider_models[chatgpt=provider-default,codex-mini-latest,gpt-5.1-codex; openai=provider-default,gpt-5.4,gpt-5.4-mini]", rendered)
            self.assertIn("hint=params[reasoning_effort]", rendered)

    def test_slash_palette_cli_json_exposes_reusable_context_and_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "openai"]
            prefs.accounts_by_model = {"openai": ["work"]}
            prefs.active_account_by_model = {"openai": "work"}
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(root, "slash mo", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "slash")
            self.assertEqual(payload["prefix"], "/mo")
            self.assertEqual(payload["context"]["enabled_providers"], ["chatgpt", "openai"])
            self.assertEqual(payload["context"]["active_accounts"], ["openai=work"])
            self.assertEqual(payload["context"]["blocked_providers"], ["chatgpt:2026-05-01T18:30"])
            entries = {item["name"]: item for item in payload["entries"]}
            self.assertIn("model variant", entries)
            self.assertIn("provider_models[chatgpt=", entries["model variant"]["hint"])
            self.assertEqual(entries["model param set"]["hint"], "params[reasoning_effort]")

    def test_slash_palette_uses_fuzzy_examples_and_returns_examples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            rendered = run_main_capture(root, "slash scarica", "--json")

            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            payload = json.loads(rendered.stdout)
            entries = {item["name"]: item for item in payload["entries"]}
            self.assertIn("download", entries)
            self.assertIn("scarica file", entries["download"]["examples"])

            completion_matches = _interactive_completion_candidates("/upg stg", AgentConfig(workspace_root=root))
            self.assertIn("/update apply", completion_matches)

    def test_extension_scaffold_and_discovery_are_read_only_safe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            scaffold = run_main_capture(root, "extension scaffold Local Tools", "--json")
            self.assertEqual(scaffold.returncode, 0, scaffold.stderr)
            payload = json.loads(scaffold.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["name"], "local-tools")
            self.assertTrue((root / ".stagewarden/extensions/local-tools/extension.json").exists())
            self.assertTrue((root / ".stagewarden/extensions/local-tools/commands").is_dir())
            self.assertTrue((root / ".stagewarden/extensions/local-tools/roles").is_dir())
            self.assertTrue((root / ".stagewarden/extensions/local-tools/skills").is_dir())
            self.assertTrue((root / ".stagewarden/extensions/local-tools/hooks").is_dir())
            self.assertTrue((root / ".stagewarden/extensions/local-tools/mcp").is_dir())

            discovered = run_main_capture(root, "extensions", "--json")
            self.assertEqual(discovered.returncode, 0, discovered.stderr)
            discovered_payload = json.loads(discovered.stdout)
            self.assertTrue(discovered_payload["ok"])
            self.assertEqual(discovered_payload["extensions"][0]["name"], "local-tools")
            self.assertEqual(discovered_payload["extensions"][0]["capabilities"], [])
            self.assertEqual(discovered_payload["extensions"][0]["schema_version"], "1")
            self.assertEqual(discovered_payload["extensions"][0]["execution"], "disabled-by-default")
            self.assertEqual(discovered_payload["extensions"][0]["missing_entrypoints"], [])
            self.assertEqual(discovered_payload["extensions"][0]["entrypoints"]["commands"], "commands/")

            actions = run_main_capture(root, "handoff actions", "3", "--json")
            phases = [entry["phase"] for entry in json.loads(actions.stdout)["entries"]]
            self.assertIn("extension_scaffold", phases)

    def test_extension_scaffold_rejects_unsafe_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            result = run_main_capture(root, "extension scaffold ../bad", "--json")
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])

    def test_extensions_discovery_flags_manifest_schema_and_missing_entrypoints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            extension_root = root / ".stagewarden" / "extensions" / "broken-tools"
            extension_root.mkdir(parents=True)
            manifest = extension_root / "extension.json"
            manifest.write_text(
                json.dumps(
                    {
                        "name": "broken-tools",
                        "schema_version": "1",
                        "version": "0.2.0",
                        "description": "Broken extension for validation.",
                        "capabilities": ["commands"],
                        "entrypoints": {
                            "commands": "commands/",
                            "roles": "roles/",
                            "skills": "skills/",
                            "hooks": "hooks/",
                            "mcp": "mcp/",
                        },
                        "execution": "disabled-by-default",
                    }
                ),
                encoding="utf-8",
            )
            (extension_root / "commands").mkdir()

            discovered = run_main_capture(root, "extensions", "--json")
            self.assertEqual(discovered.returncode, 0, discovered.stderr)
            payload = json.loads(discovered.stdout)
            self.assertFalse(payload["ok"])
            record = payload["extensions"][0]
            self.assertEqual(record["name"], "broken-tools")
            self.assertEqual(record["schema_version"], "1")
            self.assertEqual(record["execution"], "disabled-by-default")
            self.assertEqual(record["entrypoints"]["commands"], "commands/")
            self.assertIn("roles", record["missing_entrypoints"])
            self.assertEqual(record["message"], "missing entrypoints: roles, skills, hooks, mcp")

    def test_interactive_slash_choose_returns_selected_command_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("/slash choose upgrade\n1\n/exit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Choose slash command:", rendered)
            self.assertIn("Selected slash command: /update apply --yes", rendered)
            actions = run_main_capture(root, "handoff actions", "5", "--json")
            phases = [entry["phase"] for entry in json.loads(actions.stdout)["entries"]]
            self.assertNotIn("update_apply", phases)

    def test_cli_slash_choose_renders_candidates_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            rendered = run_main_capture(root, "slash choose upgrade")
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertIn("Slash chooser candidates:", rendered.stdout)
            self.assertIn("/update apply --yes", rendered.stdout)
            self.assertIn("use interactive /slash choose", rendered.stdout)

            json_rendered = run_main_capture(root, "slash choose upgrade", "--json")
            self.assertEqual(json_rendered.returncode, 0, json_rendered.stderr)
            payload = json.loads(json_rendered.stdout)
            self.assertEqual(payload["command"], "slash choose")
            names = [item["name"] for item in payload["entries"]]
            self.assertIn("update apply", names)

    def test_commands_catalog_cli_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            rendered = run_main_capture(root, "commands")
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertIn("Stagewarden command catalog:", rendered.stdout)
            self.assertIn("models:", rendered.stdout)
            self.assertIn("roles domains [--json]", rendered.stdout)
            self.assertIn("roles tree [--json]", rendered.stdout)
            self.assertIn("roles check [--json]", rendered.stdout)
            self.assertIn("roles flow [--json]", rendered.stdout)
            self.assertIn("roles matrix [--json]", rendered.stdout)
            self.assertIn("sources", rendered.stdout)
            self.assertIn("preflight [--json]", rendered.stdout)
            self.assertIn("shell backend", rendered.stdout)
            self.assertIn("commands [--json]", rendered.stdout)
            self.assertIn("file inspect <path> [--json]", rendered.stdout)
            self.assertIn("file stat <path> [--json]", rendered.stdout)
            self.assertIn("file copy <source> <destination> [--overwrite] [--dry-run] [--json]", rendered.stdout)

            completed = run_main_capture(root, "commands", "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "commands")
            by_name = {item["name"]: item for item in payload["commands"]}
            self.assertIn("commands", by_name)
            self.assertIn("preflight", by_name)
            self.assertIn("shell backend", by_name)
            self.assertIn("status", by_name)
            self.assertIn("roles domains", by_name)
            self.assertIn("roles tree", by_name)
            self.assertIn("roles check", by_name)
            self.assertIn("roles flow", by_name)
            self.assertIn("roles matrix", by_name)
            self.assertIn("sources", by_name)
            self.assertIn("file inspect", by_name)
            self.assertIn("file stat", by_name)
            self.assertIn("file copy", by_name)
            self.assertEqual(by_name["commands"]["group"], "core")
            self.assertTrue(by_name["commands"]["json"])
            self.assertTrue(by_name["preflight"]["json"])
            self.assertTrue(by_name["shell backend"]["json"])
            self.assertEqual(by_name["roles domains"]["handler"], "roles")
            self.assertEqual(by_name["roles tree"]["handler"], "roles")
            self.assertEqual(by_name["roles check"]["handler"], "roles")
            self.assertEqual(by_name["roles flow"]["handler"], "roles")
            self.assertEqual(by_name["roles matrix"]["handler"], "roles")
            self.assertEqual(by_name["file inspect"]["group"], "files")
            self.assertEqual(by_name["file copy"]["handler"], "files")

    def test_interactive_help_topics_use_registry_metadata_and_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("/help update\n/help io\n/help extension\n/help files\n/exit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Update commands", rendered)
            self.assertIn("update apply --yes", rendered)
            self.assertIn("External IO commands", rendered)
            self.assertIn("download https://example.com/file.txt", rendered)
            self.assertIn("Extension commands", rendered)
            self.assertIn("extension scaffold local-tools", rendered)
            self.assertIn("File commands", rendered)
            self.assertIn("file stat stagewarden", rendered)

    def test_interactive_help_overview_uses_topic_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("/help\n/exit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Topics:", rendered)
            self.assertIn("/help core: exit, reset, overview, health, report, status, preflight, stream, sessions, transcript", rendered)
            self.assertIn("/help models: provider routing, provider models, blocks aliases=model", rendered)
            self.assertIn("/help external_io: web search, download, checksum, compression, archive verify aliases=io,network,download", rendered)
            self.assertIn("/help caveman: Caveman aliases and modes", rendered)
            self.assertIn("/help ljson: encode, decode, benchmark", rendered)

    def test_help_cli_and_interactive_json_use_shared_topic_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            completed = run_main_capture(root, "help", "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            overview_payload = json.loads(completed.stdout)
            self.assertEqual(overview_payload["command"], "help")
            topics = {item["key"]: item for item in overview_payload["topics"]}
            self.assertIn("models", topics)
            self.assertIn("external_io", topics)
            self.assertIn("files", topics)
            self.assertIn("io", topics["external_io"]["aliases"])
            self.assertIn("fs", topics["files"]["aliases"])

            completed = run_main_capture(root, "help", "models", "--json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            topic_payload = json.loads(completed.stdout)
            self.assertTrue(topic_payload["ok"])
            self.assertEqual(topic_payload["topic"], "models")
            self.assertIn("model choose [local|cheap|chatgpt|openai|claude]", topic_payload["commands"])
            self.assertIn("model choose chatgpt", topic_payload["examples"])

            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("/help models --json\n/exit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn('"command": "help"', rendered)
            self.assertIn('"topic": "models"', rendered)
            self.assertIn('"ok": true', rendered)

            file_topic = run_main_capture(root, "help", "files", "--json")
            self.assertEqual(file_topic.returncode, 0, file_topic.stderr)
            file_topic_payload = json.loads(file_topic.stdout)
            self.assertTrue(file_topic_payload["ok"])
            self.assertEqual(file_topic_payload["topic"], "files")
            self.assertIn("file inspect <path> [--json]", file_topic_payload["commands"])
            self.assertIn("file copy README.md docs/README.copy.md --dry-run", file_topic_payload["examples"])

    def test_interactive_completion_candidates_expand_workspace_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "tracked.txt").write_text("hello\n", encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "notes.md").write_text("note\n", encoding="utf-8")
            config = AgentConfig(workspace_root=root)

            history_matches = _interactive_completion_candidates("/git history tr", config)
            patch_matches = _interactive_completion_candidates("/patch preview do", config)
            file_matches = _interactive_completion_candidates("/file inspect do", config)

            self.assertIn("/git history tracked.txt", history_matches)
            self.assertIn("/patch preview docs/", patch_matches)
            self.assertIn("/file inspect docs/", file_matches)

    def test_file_cli_commands_are_machine_readable_and_execute(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "data.txt").write_text("alpha\n", encoding="utf-8")

            stat_payload = json.loads(run_main_capture(root, "file stat data.txt", "--json").stdout)
            inspect_payload = json.loads(run_main_capture(root, "file inspect data.txt", "--json").stdout)
            copy_payload = json.loads(run_main_capture(root, "file copy data.txt copied.txt", "--json").stdout)

            self.assertTrue(stat_payload["ok"])
            self.assertEqual(stat_payload["report"]["command"], "file stat")
            self.assertEqual(stat_payload["report"]["kind"], "file")
            self.assertTrue(inspect_payload["ok"])
            self.assertEqual(inspect_payload["report"]["encoding"], "utf-8")
            self.assertTrue(copy_payload["ok"])
            self.assertTrue((root / "copied.txt").exists())

            chmod_payload = json.loads(run_main_capture(root, "file chmod copied.txt 0600", "--json").stdout)
            self.assertTrue(chmod_payload["ok"])
            self.assertEqual((root / "copied.txt").stat().st_mode & 0o777, 0o600)

            delete_preview_payload = json.loads(run_main_capture(root, "file delete copied.txt --dry-run", "--json").stdout)
            self.assertTrue(delete_preview_payload["ok"])
            self.assertTrue((root / "copied.txt").exists())

            delete_payload = json.loads(run_main_capture(root, "file delete copied.txt", "--json").stdout)
            self.assertTrue(delete_payload["ok"])
            self.assertFalse((root / "copied.txt").exists())

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
            self.assertIn("route: provider=cheap account=none provider_model=provider-default", rendered)
            self.assertIn("Agent result:", rendered)
            self.assertIn("Last step outcome:", rendered)
            self.assertIn("step: step-3", rendered)
            self.assertIn("action: shell", rendered)
            self.assertIn("evidence: tool=shell action=shell", rendered)
            self.assertIn("Shell progress (after):", rendered)
            self.assertIn("route: provider=cheap account=none provider_model=provider-default", rendered)
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
            self.assertIn("[model-stream cheap]", rendered)
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
            self.assertIn("Provider-model catalog for claude:", rendered)
            self.assertIn("Auth: anthropic_api_key_or_claude_code_credentials", rendered)
            self.assertIn("Browser login: no", rendered)
            self.assertIn("Login hint: Use ANTHROPIC_API_KEY", rendered)
            self.assertIn("opusplan", rendered)
            self.assertIn("provider_model=opus", rendered)

    def test_model_list_shows_provider_model_reasoning_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "model list chatgpt")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Provider-model catalog for chatgpt:", completed.stdout)
            self.assertIn("gpt-5.3-codex", completed.stdout)
            self.assertIn("reasoning_effort=[low,medium,high]", completed.stdout)

    def test_model_inspect_local_uses_dynamic_catalog_and_ai_synthesis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = root / "run_model_inspect_stub.py"
            stub.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "from __future__ import annotations",
                        "import json",
                        "import sys",
                        "",
                        "payload = {",
                        '  "models": [',
                        '    {"id": "qwen2.5-coder:7b", "summary": "Fast local coding model.", "strengths": ["good coding speed"], "weaknesses": ["smaller context"], "best_for": ["daily coding"], "agentic_fit": "high", "tool_support_risk": "medium"},',
                        '    {"id": "codestral:latest", "summary": "Needs explicit tool-support validation.", "strengths": ["strong code prior"], "weaknesses": ["tool support uncertain"], "best_for": ["manual comparison"], "agentic_fit": "low", "tool_support_risk": "high"}',
                        "  ],",
                        '  "global_recommendation": "Prefer qwen2.5-coder:7b for local agentic work."',
                        "}",
                        "print(json.dumps(payload))",
                        "raise SystemExit(0)",
                    ]
                ),
                encoding="utf-8",
            )
            stub.chmod(0o755)
            original_run_model = os.environ.get("RUN_MODEL_BIN")
            original_tags = os.environ.get("STAGEWARDEN_OLLAMA_TAGS_JSON")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = json.dumps(
                {
                    "models": [
                        {
                            "name": "qwen2.5-coder:7b",
                            "details": {"family": "qwen2", "parameter_size": "7.6B", "quantization_level": "Q4_K_M"},
                        },
                        {
                            "name": "codestral:latest",
                            "details": {"family": "llama", "parameter_size": "22.2B", "quantization_level": "Q4_0"},
                        },
                    ]
                }
            )
            self.addCleanup(lambda: os.environ.pop("RUN_MODEL_BIN", None) if original_run_model is None else os.environ.__setitem__("RUN_MODEL_BIN", original_run_model))
            self.addCleanup(lambda: os.environ.pop("STAGEWARDEN_OLLAMA_TAGS_JSON", None) if original_tags is None else os.environ.__setitem__("STAGEWARDEN_OLLAMA_TAGS_JSON", original_tags))

            json_completed = run_main_capture(root, "model inspect local", "--json")
            text_completed = run_main_capture(root, "model inspect local qwen2.5-coder:7b")

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            self.assertEqual(text_completed.returncode, 0, text_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "model inspect")
            self.assertEqual(payload["provider"], "local")
            self.assertTrue(payload["ai_analysis"]["attempted"])
            self.assertTrue(payload["ai_analysis"]["ok"])
            self.assertEqual(payload["ai_analysis"]["model"], "chatgpt")
            self.assertEqual(payload["global_recommendation"], "Prefer qwen2.5-coder:7b for local agentic work.")
            ids = {item["id"]: item for item in payload["models"]}
            self.assertEqual(ids["qwen2.5-coder:7b"]["agentic_fit"], "high")
            self.assertEqual(ids["codestral:latest"]["tool_support_risk"], "high")
            self.assertIn("Provider-model inspection for local:", text_completed.stdout)
            self.assertIn("qwen2.5-coder:7b", text_completed.stdout)

    def test_interactive_shell_persists_provider_model_param(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_stream = StringIO(
                "model variant chatgpt gpt-5.3-codex\n"
                "model param set chatgpt reasoning_effort high\n"
                "model params chatgpt\n"
                "models\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(AgentConfig(workspace_root=root, max_steps=1), input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")

            self.assertEqual(code, 0)
            self.assertEqual((prefs.params_by_model or {}).get("chatgpt", {}).get("reasoning_effort"), "high")
            self.assertIn("reasoning_effort_current: high", rendered)
            self.assertIn("params=reasoning_effort=high", rendered)

    def test_interactive_shell_applies_simplified_model_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_stream = StringIO(
                "model preset chatgpt deep\n"
                "model params chatgpt\n"
                "models\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(AgentConfig(workspace_root=root, max_steps=1), input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")

            self.assertEqual(code, 0)
            self.assertEqual((prefs.variant_by_model or {}).get("chatgpt"), "gpt-5.3-codex")
            self.assertEqual((prefs.params_by_model or {}).get("chatgpt", {}).get("reasoning_effort"), "high")
            self.assertIn("Applied preset deep to chatgpt: provider_model=gpt-5.3-codex", rendered)
            self.assertIn("reasoning_effort_current: high", rendered)

    def test_interactive_shell_guided_model_choice_for_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_stream = StringIO(
                "model choose chatgpt\n"
                "4\n"
                "2\n"
                "model params chatgpt\n"
                "models\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(AgentConfig(workspace_root=root, max_steps=1), input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")

            self.assertEqual(code, 0)
            self.assertEqual(prefs.preferred_model, "chatgpt")
            self.assertEqual((prefs.variant_by_model or {}).get("chatgpt"), "gpt-5.1-codex-mini")
            self.assertEqual((prefs.params_by_model or {}).get("chatgpt", {}).get("reasoning_effort"), "high")
            self.assertIn("Selection context:", rendered)
            self.assertIn("- selected_provider: chatgpt", rendered)
            self.assertIn("- current_provider_model: provider-default", rendered)
            self.assertIn("Choose provider-model for chatgpt:", rendered)
            self.assertIn("Choose reasoning_effort for chatgpt:gpt-5.1-codex-mini:", rendered)
            self.assertIn("Guided selection applied: provider=chatgpt provider_model=gpt-5.1-codex-mini reasoning_effort=high.", rendered)
            self.assertIn("reasoning_effort_current: high", rendered)

    def test_interactive_shell_guided_model_choice_can_select_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_stream = StringIO(
                "model choose\n"
                "3\n"
                "7\n"
                "2\n"
                "models\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(AgentConfig(workspace_root=root, max_steps=1), input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")

            self.assertEqual(code, 0)
            self.assertEqual(prefs.preferred_model, "chatgpt")
            self.assertEqual((prefs.variant_by_model or {}).get("chatgpt"), "gpt-5.4")
            self.assertEqual((prefs.params_by_model or {}).get("chatgpt", {}).get("reasoning_effort"), "medium")
            self.assertIn("Choose provider:", rendered)
            self.assertIn("- enabled_providers: local, cheap, chatgpt, openai, claude", rendered)
            self.assertIn("- selected_provider: chatgpt", rendered)
            self.assertIn("Guided selection applied: provider=chatgpt provider_model=gpt-5.4 reasoning_effort=medium.", rendered)

    def test_interactive_shell_model_preset_without_value_opens_model_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_stream = StringIO(
                "model preset chatgpt\n"
                "6\n"
                "3\n"
                "model params chatgpt\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(AgentConfig(workspace_root=root, max_steps=1), input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")

            self.assertEqual(code, 0)
            self.assertEqual(prefs.preferred_model, "chatgpt")
            self.assertEqual((prefs.variant_by_model or {}).get("chatgpt"), "gpt-5.3-codex")
            self.assertEqual((prefs.params_by_model or {}).get("chatgpt", {}).get("reasoning_effort"), "high")
            self.assertIn("Selection context:", rendered)
            self.assertIn("- selected_provider: chatgpt", rendered)
            self.assertIn("Choose provider-model for chatgpt:", rendered)
            self.assertIn("Guided selection applied: provider=chatgpt provider_model=gpt-5.3-codex reasoning_effort=high.", rendered)
            self.assertIn("reasoning_effort_current: high", rendered)

    def test_interactive_shell_roles_propose_persists_assignments_and_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_stream = StringIO("roles propose\nroles\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(AgentConfig(workspace_root=root, max_steps=1), input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")

            self.assertEqual(code, 0)
            self.assertIn("project_manager", prefs.prince2_roles or {})
            self.assertEqual((prefs.prince2_roles or {})["project_manager"]["provider"], "chatgpt")
            self.assertEqual((prefs.prince2_roles or {})["project_manager"]["provider_model"], "gpt-5.3-codex")
            self.assertEqual((handoff.prince2_roles or {})["project_manager"]["provider_model"], "gpt-5.3-codex")
            self.assertIn("PRINCE2 role assignments:", rendered)
            self.assertIn("Project Manager (project_manager): mode=auto", rendered)

    def test_roles_domains_shows_prince2_context_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "roles domains")
            json_completed = run_main_capture(root, "roles domains", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PRINCE2 role domains:", completed.stdout)
            self.assertIn("Project Executive (project_executive): responsibility=business justification", completed.stdout)
            self.assertIn("Team Manager (team_manager): responsibility=implementation and product delivery", completed.stdout)
            self.assertIn("context_scope=current work package, product delivery, quality criteria, and implementation lessons only", completed.stdout)
            self.assertIn("a role-assigned model receives only the context inside its PRINCE2 domain", completed.stdout)
            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles domains")
            domains = {item["role"]: item for item in payload["roles"]}
            self.assertEqual(domains["team_manager"]["context_scope"], "current work package, product delivery, quality criteria, and implementation lessons only")
            self.assertIn("context inside its PRINCE2 domain", payload["rule"])

    def test_roles_tree_shows_hierarchy_and_node_context_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            propose = run_main_capture(root, "roles propose")
            completed = run_main_capture(root, "roles tree")
            json_completed = run_main_capture(root, "roles tree", "--json")

            self.assertEqual(propose.returncode, 0, propose.stderr)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PRINCE2 role tree:", completed.stdout)
            self.assertIn("Project Executive [board.executive]", completed.stdout)
            self.assertIn("  - Project Manager [management.project_manager]", completed.stdout)
            self.assertIn("context=current work package, product delivery, quality criteria, and implementation lessons only", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles tree")
            self.assertIn("fallback routing must not widen context", payload["rule"])
            nodes = {item["node_id"]: item for item in payload["nodes"]}
            self.assertEqual(nodes["management.project_manager"]["parent_id"], "board.executive")
            self.assertEqual(nodes["delivery.team_manager"]["parent_id"], "management.project_manager")
            self.assertEqual(nodes["delivery.team_manager"]["context_rule"]["include"][0], "assigned_work_package")
            self.assertIn("business_case_detail", nodes["delivery.team_manager"]["context_rule"]["exclude"])
            self.assertEqual(nodes["management.project_manager"]["assignment"]["provider"], "chatgpt")
            self.assertEqual(nodes["assurance.project_assurance"]["level"], "assurance")

    def test_roles_check_validates_tree_readiness_limits_and_independence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            missing = run_main_capture(root, "roles check", "--json")
            self.assertEqual(missing.returncode, 0, missing.stderr)
            missing_payload = json.loads(missing.stdout)
            self.assertEqual(missing_payload["status"], "error")
            self.assertEqual(missing_payload["summary"]["unassigned"], 8)
            self.assertEqual(missing_payload["findings"][0]["code"], "missing_assignment")

            propose = run_main_capture(root, "roles propose")
            self.assertEqual(propose.returncode, 0, propose.stderr)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            team_assignment = dict((prefs.prince2_roles or {})["team_manager"])
            prefs.set_prince2_role_assignment(
                "project_assurance",
                mode="auto",
                provider=str(team_assignment["provider"]),
                provider_model=str(team_assignment["provider_model"]),
                params=dict(team_assignment.get("params", {})),
                account=team_assignment.get("account"),
                source="test_independence_warning",
            )
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(root, "roles check")
            json_completed = run_main_capture(root, "roles check", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PRINCE2 role tree check:", completed.stdout)
            self.assertIn("provider_blocked", completed.stdout)
            self.assertIn("assurance_delivery_same_model", completed.stdout)
            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles check")
            self.assertEqual(payload["status"], "error")
            codes = {item["code"] for item in payload["findings"]}
            self.assertIn("provider_blocked", codes)
            self.assertIn("assurance_delivery_same_model", codes)
            self.assertEqual(payload["summary"]["assigned"], 8)

    def test_roles_check_warns_for_assigned_nodes_without_explicit_flow_edge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.assertEqual(run_main_capture(root, "roles propose").returncode, 0)
            self.assertEqual(run_main_capture(root, "role add-child management.project_manager team_manager delivery.release_manager").returncode, 0)
            completed = run_main_capture(root, "roles check", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            codes = {item["code"] for item in payload["findings"]}
            self.assertIn("node_without_flow_edge", codes)
            self.assertEqual(payload["status"], "warning")

    def test_roles_flow_shows_prince2_node_transitions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "roles flow")
            json_completed = run_main_capture(root, "roles flow", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PRINCE2 role flow:", completed.stdout)
            self.assertIn("authorize.project: board.executive -> management.project_manager", completed.stdout)
            self.assertIn("issue.work_package: management.project_manager -> delivery.team_manager", completed.stdout)
            self.assertIn("escalate.stage_exception: management.project_manager -> authority.change_authority", completed.stdout)
            self.assertIn("context moves only along approved PRINCE2 flow edges", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles flow")
            self.assertIn("approved PRINCE2 flow edges", payload["rule"])
            edges = {item["edge_id"]: item for item in payload["edges"]}
            self.assertEqual(edges["issue.work_package"]["source_node"], "management.project_manager")
            self.assertEqual(edges["issue.work_package"]["target_node"], "delivery.team_manager")
            self.assertIn("assigned_work_package", edges["issue.work_package"]["payload_scope"])
            self.assertEqual(edges["assure.quality_risk"]["target_node"], "assurance.project_assurance")
            self.assertIn("independent", edges["assure.quality_risk"]["validation_condition"])
            self.assertEqual(edges["escalate.board_decision"]["target_node"], "board.executive")

    def test_roles_matrix_combines_tree_flow_assignments_and_limits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            propose = run_main_capture(root, "roles propose")
            self.assertEqual(propose.returncode, 0, propose.stderr)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(root, "roles matrix")
            json_completed = run_main_capture(root, "roles matrix", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PRINCE2 role matrix:", completed.stdout)
            self.assertIn("Project Manager [management.project_manager]", completed.stdout)
            self.assertIn("provider_blocked", completed.stdout)
            self.assertIn("provider_blocked_until=2026-05-01T18:30", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles matrix")
            self.assertEqual(payload["status"], "error")
            rows = {item["node_id"]: item for item in payload["rows"]}
            self.assertEqual(rows["management.project_manager"]["provider"], "chatgpt")
            self.assertEqual(rows["management.project_manager"]["provider_blocked_until"], "2026-05-01T18:30")
            self.assertIn("authorize.project", rows["management.project_manager"]["incoming_edges"])
            self.assertIn("issue.work_package", rows["management.project_manager"]["outgoing_edges"])
            self.assertIn("stage_plan", rows["management.project_manager"]["context_include"])
            self.assertIn("board_private_decision_context", rows["management.project_manager"]["context_exclude"])
            self.assertTrue(payload["flow_edges"])

    def test_roles_propose_preloads_local_execution_candidates_into_delivery_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = os.environ.get("STAGEWARDEN_OLLAMA_TAGS_JSON")
            os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = json.dumps(
                {
                    "models": [
                        {
                            "name": "qwen2.5-coder:7b",
                            "details": {"family": "qwen2", "parameter_size": "7.6B", "quantization_level": "Q4_K_M"},
                        },
                        {
                            "name": "deepseek-r1:14b",
                            "details": {"family": "qwen2", "parameter_size": "14.8B", "quantization_level": "Q4_K_M"},
                        },
                    ]
                }
            )
            try:
                propose = run_main_capture(root, "roles propose")
                baseline = run_main_capture(root, "roles baseline", "--json")
            finally:
                if original is None:
                    os.environ.pop("STAGEWARDEN_OLLAMA_TAGS_JSON", None)
                else:
                    os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = original

            self.assertEqual(propose.returncode, 0, propose.stderr)
            self.assertEqual(baseline.returncode, 0, baseline.stderr)
            payload = json.loads(baseline.stdout)
            tree = payload["baseline"]["tree"]
            nodes = {item["node_id"]: item for item in tree["nodes"]}
            team_node = nodes["delivery.team_manager"]
            self.assertEqual(team_node["assignment"]["provider"], "cheap")
            self.assertCountEqual(team_node["local_execution_candidates"], ["deepseek-r1:14b", "qwen2.5-coder:7b"])
            fallback_routes = team_node["assignment_pool"]["fallback"]
            self.assertTrue(all(item["provider"] == "local" for item in fallback_routes))
            fallback_by_model = {item["provider_model"]: item for item in fallback_routes}
            self.assertEqual(set(fallback_by_model), {"deepseek-r1:14b", "qwen2.5-coder:7b"})
            self.assertEqual(fallback_by_model["deepseek-r1:14b"]["params"]["reasoning_effort"], "high")
            self.assertEqual(fallback_by_model["qwen2.5-coder:7b"]["params"]["reasoning_effort"], "medium")
            self.assertEqual(payload["baseline"]["local_execution"]["status"], "ok")
            matrix_rows = {item["node_id"]: item for item in payload["baseline"]["matrix"]["rows"]}
            matrix_fallback_by_model = {
                item["provider_model"]: item for item in matrix_rows["delivery.team_manager"]["fallback_routes"]
            }
            self.assertEqual(set(matrix_fallback_by_model), {"deepseek-r1:14b", "qwen2.5-coder:7b"})

    def test_interactive_shell_role_configure_menu_persists_manual_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_stream = StringIO(
                "role configure project_manager\n"
                "manual\n"
                "3\n"
                "7\n"
                "2\n"
                "1\n"
                "roles\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(AgentConfig(workspace_root=root, max_steps=1), input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            assignment = (prefs.prince2_roles or {})["project_manager"]

            self.assertEqual(code, 0)
            self.assertEqual(assignment["mode"], "manual")
            self.assertEqual(assignment["provider"], "chatgpt")
            self.assertEqual(assignment["provider_model"], "gpt-5.4")
            self.assertEqual(assignment["params"]["reasoning_effort"], "medium")
            self.assertIsNone(assignment["account"])
            self.assertIn("PRINCE2 role context:", rendered)
            self.assertIn("- role: Project Manager (project_manager)", rendered)
            self.assertIn("- responsibility: planning, coordination, controlled execution, reporting, and stage boundary control", rendered)
            self.assertIn("Selection context:", rendered)
            self.assertIn("Choose provider for Project Manager:", rendered)
            self.assertIn("Assigned Project Manager: provider=chatgpt provider_model=gpt-5.4 account=none reasoning_effort=medium.", rendered)

    def test_interactive_shell_roles_setup_manual_can_approve_baseline_with_local_fallbacks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = os.environ.get("STAGEWARDEN_OLLAMA_TAGS_JSON")
            os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = json.dumps(
                {
                    "models": [
                        {
                            "name": "qwen2.5-coder:7b",
                            "details": {"family": "qwen2", "parameter_size": "7.6B", "quantization_level": "Q4_K_M"},
                        },
                        {
                            "name": "deepseek-r1:14b",
                            "details": {"family": "qwen2", "parameter_size": "14.8B", "quantization_level": "Q4_K_M"},
                        },
                    ]
                }
            )
            try:
                input_stream = StringIO(
                    "roles setup\n"
                    "manual\n"
                    "team_manager\n"
                    "auto\n"
                    "done\n"
                    "yes\n"
                    "exit\n"
                )
                output_stream = StringIO()
                code = run_interactive_shell(
                    AgentConfig(workspace_root=root, max_steps=1),
                    input_stream=input_stream,
                    output_stream=output_stream,
                )
            finally:
                if original is None:
                    os.environ.pop("STAGEWARDEN_OLLAMA_TAGS_JSON", None)
                else:
                    os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = original
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            baseline = prefs.prince2_role_tree_baseline or {}
            team_node = next(
                item
                for item in baseline.get("tree", {}).get("nodes", [])
                if isinstance(item, dict) and item.get("node_id") == "delivery.team_manager"
            )
            fallback_by_model = {
                item["provider_model"]: item
                for item in team_node.get("assignment_pool", {}).get("fallback", [])
                if isinstance(item, dict)
            }

            self.assertEqual(code, 0)
            self.assertIn("PRINCE2 role setup:", rendered)
            self.assertIn("Recommended local fallback candidates discovered:", rendered)
            self.assertIn("Approve baseline with recommended local delivery fallbacks now?", rendered)
            self.assertIn("Role setup completed with approved baseline and recommended local delivery fallbacks.", rendered)
            self.assertEqual(baseline.get("source"), "roles_setup_manual_local_fallbacks")
            self.assertIn("deepseek-r1:14b", fallback_by_model)
            self.assertIn("qwen2.5-coder:7b", fallback_by_model)
            self.assertIn("local_execution_candidates: ", rendered)

    def test_project_start_blocks_when_design_or_brief_has_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "project start")
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")

            self.assertEqual(completed.returncode, 1, completed.stdout)
            self.assertIn("Project startup design gate:", completed.stdout)
            self.assertIn("Project design packet:", completed.stdout)
            self.assertIn("Project tree proposal:", completed.stdout)
            self.assertIn("Project startup blocked:", completed.stdout)
            self.assertIn("missing_project_task", completed.stdout)
            self.assertEqual(prefs.prince2_role_tree_baseline, {})
            self.assertEqual(handoff.prince2_role_tree_baseline, {})
            self.assertIn("project_start_blocked", [entry.phase for entry in handoff.entries])

    def test_project_start_approves_ready_project_tree_proposal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")
            handoff.task = "build a governed CLI coding agent"
            handoff.save(root / ".stagewarden_handoff.json")
            self.assertEqual(run_main_capture(root, "project brief set objective Build a CLI coding agent").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set scope shell git model routing and browser login").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set expected_outputs CLI tests wet-run validation").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set delivery_mode hybrid").returncode, 0)

            completed = run_main_capture(root, "project start")
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Project startup design gate:", completed.stdout)
            self.assertIn("Project tree proposal:", completed.stdout)
            self.assertIn("Project tree approval:", completed.stdout)
            self.assertIn("delivery.implementation_team", completed.stdout)
            self.assertIn("project_executive", prefs.prince2_roles or {})
            self.assertIn("project_executive", handoff.prince2_roles or {})
            self.assertEqual((prefs.prince2_role_tree_baseline or {}).get("source"), "project_tree_approve")
            self.assertEqual((handoff.prince2_role_tree_baseline or {}).get("source"), "project_tree_approve")
            phases = [entry.phase for entry in handoff.entries]
            self.assertIn("project_tree_approval", phases)
            self.assertIn("project_start_approved", phases)
            self.assertIn("PRINCE2 role-tree baseline:", completed.stdout)

    def test_project_start_preloads_local_delivery_fallbacks_when_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = os.environ.get("STAGEWARDEN_OLLAMA_TAGS_JSON")
            os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = json.dumps(
                {
                    "models": [
                        {
                            "name": "qwen2.5-coder:7b",
                            "details": {"family": "qwen2", "parameter_size": "7.6B", "quantization_level": "Q4_K_M"},
                        },
                        {
                            "name": "deepseek-r1:14b",
                            "details": {"family": "qwen2", "parameter_size": "14.8B", "quantization_level": "Q4_K_M"},
                        },
                    ]
                }
            )
            try:
                handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")
                handoff.task = "build a governed CLI coding agent"
                handoff.save(root / ".stagewarden_handoff.json")
                self.assertEqual(run_main_capture(root, "project brief set objective Build a CLI coding agent").returncode, 0)
                self.assertEqual(run_main_capture(root, "project brief set scope shell git model routing and browser login").returncode, 0)
                self.assertEqual(run_main_capture(root, "project brief set expected_outputs CLI tests wet-run validation").returncode, 0)
                self.assertEqual(run_main_capture(root, "project brief set delivery_mode hybrid").returncode, 0)

                completed = run_main_capture(root, "project start")
            finally:
                if original is None:
                    os.environ.pop("STAGEWARDEN_OLLAMA_TAGS_JSON", None)
                else:
                    os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = original

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Project start local fallback preload:", completed.stdout)
            self.assertIn("deepseek-r1:14b", completed.stdout)
            self.assertIn("qwen2.5-coder:7b", completed.stdout)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            baseline = prefs.prince2_role_tree_baseline or {}
            team_node = next(
                item
                for item in baseline.get("tree", {}).get("nodes", [])
                if isinstance(item, dict) and item.get("node_id") == "delivery.team_manager"
            )
            fallback_by_model = {
                item["provider_model"]: item
                for item in team_node.get("assignment_pool", {}).get("fallback", [])
                if isinstance(item, dict)
            }
            self.assertIn("deepseek-r1:14b", fallback_by_model)
            self.assertIn("qwen2.5-coder:7b", fallback_by_model)
            self.assertEqual((baseline.get("local_execution") or {}).get("status"), "ok")

    def test_project_start_ai_persists_valid_ai_tree_patch_after_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = root / "run_model_ai_start_stub.py"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "from __future__ import annotations\n"
                "import json\n"
                "print(json.dumps({\n"
                "  'summary': 'Add release governance for start approval.',\n"
                "  'tree_patches': [{\n"
                "    'node_id': 'delivery.release_manager',\n"
                "    'role_type': 'team_manager',\n"
                "    'label': 'Release Team Manager',\n"
                "    'parent_id': 'management.project_manager',\n"
                "    'level': 'delivery',\n"
                "    'accountability_boundary': 'delegated release packaging and wet-run evidence inside stage tolerances',\n"
                "    'delegated_authority': 'coordinates release work packages and escalates forecast tolerance breaches'\n"
                "  }]\n"
                "}))\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")
            handoff.task = "build a governed CLI coding agent"
            handoff.save(root / ".stagewarden_handoff.json")
            self.assertEqual(run_main_capture(root, "project brief set objective Build a CLI coding agent").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set scope shell git model routing browser login and release packaging").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set expected_outputs CLI tests wet-run validation").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set delivery_mode hybrid").returncode, 0)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                completed = run_main_capture(root, "project start --ai")
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("delivery.release_manager", completed.stdout)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            baseline = prefs.prince2_role_tree_baseline or {}
            proposal = baseline.get("proposal", {})
            self.assertTrue(proposal.get("ai_requested"))
            self.assertIn("delivery.release_manager", proposal.get("added_nodes", []))
            node_ids = {item["node_id"] for item in baseline.get("tree", {}).get("nodes", [])}
            self.assertIn("delivery.release_manager", node_ids)

    def test_roles_tree_approve_persists_role_tree_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            propose = run_main_capture(root, "roles propose")
            completed = run_main_capture(root, "roles tree approve")
            baseline = run_main_capture(root, "roles baseline")
            json_completed = run_main_capture(root, "roles baseline", "--json")
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")

            self.assertEqual(propose.returncode, 0, propose.stderr)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(baseline.returncode, 0, baseline.stderr)
            self.assertIn("Approved PRINCE2 role-tree baseline.", completed.stdout)
            self.assertIn("PRINCE2 role-tree baseline:", baseline.stdout)
            self.assertIn("status: approved", baseline.stdout)
            self.assertIn("rule: this approved role tree is the governance baseline", baseline.stdout)
            self.assertEqual((prefs.prince2_role_tree_baseline or {}).get("source"), "roles_tree_approve")
            self.assertEqual((handoff.prince2_role_tree_baseline or {}).get("source"), "roles_tree_approve")

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles baseline")
            self.assertEqual(payload["status"], "approved")
            self.assertEqual(payload["baseline"]["tree"]["command"], "roles tree")
            self.assertEqual(payload["baseline"]["matrix"]["command"], "roles matrix")

    def test_role_add_child_and_assign_updates_role_tree_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            propose = run_main_capture(root, "roles propose")
            add_child = run_main_capture(
                root,
                "role add-child management.project_manager team_manager delivery.api_team",
            )
            assign = run_main_capture(
                root,
                "role assign delivery.api_team openai gpt-5.4-mini reasoning_effort=medium",
            )
            baseline = run_main_capture(root, "roles baseline", "--json")
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")

            self.assertEqual(propose.returncode, 0, propose.stderr)
            self.assertEqual(add_child.returncode, 0, add_child.stderr)
            self.assertEqual(assign.returncode, 0, assign.stderr)
            self.assertIn("Added delegated PRINCE2 role node delivery.api_team", add_child.stdout)
            self.assertIn("Assigned role node delivery.api_team: provider=openai provider_model=gpt-5.4-mini account=none pool=primary.", assign.stdout)
            self.assertEqual((prefs.prince2_role_tree_baseline or {}).get("source"), "role_assign")
            self.assertEqual((handoff.prince2_role_tree_baseline or {}).get("source"), "role_assign")

            self.assertEqual(baseline.returncode, 0, baseline.stderr)
            payload = json.loads(baseline.stdout)
            nodes = {
                item["node_id"]: item
                for item in payload["baseline"]["tree"]["nodes"]
                if isinstance(item, dict)
            }
            self.assertIn("delivery.api_team", nodes)
            self.assertEqual(nodes["delivery.api_team"]["parent_id"], "management.project_manager")
            self.assertEqual(nodes["delivery.api_team"]["role_type"], "team_manager")
            self.assertEqual(nodes["delivery.api_team"]["assignment"]["provider"], "openai")
            self.assertEqual(nodes["delivery.api_team"]["assignment"]["provider_model"], "gpt-5.4-mini")
            self.assertEqual(nodes["delivery.api_team"]["assignment"]["params"]["reasoning_effort"], "medium")

    def test_interactive_shell_guided_role_node_add_child_and_assign(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            input_stream = StringIO(
                "roles propose\n"
                "role add-child\n"
                "management.project_manager\n"
                "team_manager\n"
                "delivery.docs_team\n"
                "role assign\n"
                "delivery.docs_team\n"
                "primary\n"
                "openai\n"
                "gpt-5.4-mini\n"
                "medium\n"
                "1\n"
                "roles baseline\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(AgentConfig(workspace_root=root, max_steps=1), input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            nodes = {
                item["node_id"]: item
                for item in (prefs.prince2_role_tree_baseline or {})["tree"]["nodes"]
                if isinstance(item, dict)
            }

            self.assertEqual(code, 0)
            self.assertIn("PRINCE2 delegated node setup:", rendered)
            self.assertIn("Choose parent role-tree node:", rendered)
            self.assertIn("Choose delegated PRINCE2 role type:", rendered)
            self.assertIn("Added delegated PRINCE2 role node delivery.docs_team under management.project_manager.", rendered)
            self.assertIn("PRINCE2 role-tree node assignment:", rendered)
            self.assertIn("Choose role-tree node:", rendered)
            self.assertIn("Choose assignment pool for delivery.docs_team:", rendered)
            self.assertIn("Choose provider for delivery.docs_team:", rendered)
            self.assertIn("Node assignment context:", rendered)
            self.assertIn("Assigned role node delivery.docs_team: provider=openai provider_model=gpt-5.4-mini account=none reasoning_effort=medium pool=primary.", rendered)
            self.assertEqual(nodes["delivery.docs_team"]["assignment"]["provider"], "openai")
            self.assertEqual(nodes["delivery.docs_team"]["assignment"]["provider_model"], "gpt-5.4-mini")
            self.assertEqual(nodes["delivery.docs_team"]["assignment"]["params"]["reasoning_effort"], "medium")

    def test_interactive_shell_role_assign_prioritizes_local_fallback_candidates_for_delivery_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            original = os.environ.get("STAGEWARDEN_OLLAMA_TAGS_JSON")
            os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = json.dumps(
                {
                    "models": [
                        {
                            "name": "qwen2.5-coder:7b",
                            "details": {"family": "qwen2", "parameter_size": "7.6B", "quantization_level": "Q4_K_M"},
                        },
                        {
                            "name": "deepseek-r1:14b",
                            "details": {"family": "qwen2", "parameter_size": "14.8B", "quantization_level": "Q4_K_M"},
                        },
                    ]
                }
            )
            try:
                input_stream = StringIO(
                    "roles propose\n"
                    "role assign\n"
                    "delivery.team_manager\n"
                    "fallback\n"
                    "local\n"
                    "deepseek-r1:14b\n"
                    "2\n"
                    "1\n"
                    "roles baseline\n"
                    "exit\n"
                )
                output_stream = StringIO()
                code = run_interactive_shell(
                    AgentConfig(workspace_root=root, max_steps=1),
                    input_stream=input_stream,
                    output_stream=output_stream,
                )
            finally:
                if original is None:
                    os.environ.pop("STAGEWARDEN_OLLAMA_TAGS_JSON", None)
                else:
                    os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = original
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            nodes = {
                item["node_id"]: item
                for item in (prefs.prince2_role_tree_baseline or {})["tree"]["nodes"]
                if isinstance(item, dict)
            }
            fallback_routes = nodes["delivery.team_manager"]["assignment_pool"]["fallback"]
            fallback_by_model = {item["provider_model"]: item for item in fallback_routes}

            self.assertEqual(code, 0)
            self.assertIn("Node assignment context:", rendered)
            self.assertIn("recommended_local_fallbacks:", rendered)
            self.assertIn("deepseek-r1:14b(high)", rendered)
            self.assertIn("qwen2.5-coder:7b(medium)", rendered)
            self.assertIn("local | recommended for this node fallback", rendered)
            self.assertIn("deepseek-r1:14b | recommended local fallback reasoning=high", rendered)
            self.assertIn("Assigned role node delivery.team_manager: provider=local provider_model=deepseek-r1:14b account=none reasoning_effort=high pool=fallback.", rendered)
            self.assertEqual(fallback_by_model["deepseek-r1:14b"]["params"]["reasoning_effort"], "high")
            self.assertIn("local_execution_candidates: ", rendered)

    def test_role_assign_supports_reviewer_and_fallback_pools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.assertEqual(run_main_capture(root, "roles propose").returncode, 0)
            self.assertEqual(run_main_capture(root, "role add-child management.project_manager team_manager delivery.pool_team").returncode, 0)
            primary = run_main_capture(root, "role assign delivery.pool_team openai gpt-5.4-mini reasoning_effort=medium")
            reviewer = run_main_capture(root, "role assign delivery.pool_team cheap provider-default reasoning_effort=medium pool=reviewer")
            fallback = run_main_capture(root, "role assign delivery.pool_team local provider-default pool=fallback")
            baseline = run_main_capture(root, "roles baseline", "--json")

            self.assertEqual(primary.returncode, 0, primary.stderr)
            self.assertEqual(reviewer.returncode, 0, reviewer.stderr)
            self.assertEqual(fallback.returncode, 0, fallback.stderr)
            self.assertIn("pool=reviewer", reviewer.stdout)
            self.assertIn("pool=fallback", fallback.stdout)
            payload = json.loads(baseline.stdout)
            rows = {item["node_id"]: item for item in payload["baseline"]["matrix"]["rows"]}
            row = rows["delivery.pool_team"]
            self.assertEqual(row["provider"], "openai")
            self.assertEqual(row["reviewer_routes"][0]["provider"], "cheap")
            self.assertEqual(row["fallback_routes"][0]["provider"], "local")

    def test_roles_baseline_matrix_shows_delegated_nodes_and_route_pools(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.assertEqual(run_main_capture(root, "roles propose").returncode, 0)
            self.assertEqual(run_main_capture(root, "role add-child management.project_manager team_manager delivery.matrix_team").returncode, 0)
            self.assertEqual(run_main_capture(root, "role assign delivery.matrix_team local provider-default").returncode, 0)
            self.assertEqual(run_main_capture(root, "role assign delivery.matrix_team cheap provider-default reasoning_effort=medium pool=reviewer").returncode, 0)
            self.assertEqual(run_main_capture(root, "role assign delivery.matrix_team chatgpt gpt-5.1-codex-mini reasoning_effort=medium pool=fallback").returncode, 0)

            completed = run_main_capture(root, "roles baseline matrix")
            json_completed = run_main_capture(root, "roles baseline matrix", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PRINCE2 role matrix:", completed.stdout)
            self.assertIn("delivery.matrix_team", completed.stdout)
            self.assertIn("reviewers=1 fallbacks=1", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles baseline matrix")
            rows = {item["node_id"]: item for item in payload["rows"]}
            self.assertEqual(rows["delivery.matrix_team"]["provider"], "local")
            self.assertEqual(rows["delivery.matrix_team"]["reviewer_routes"][0]["provider"], "cheap")
            self.assertEqual(rows["delivery.matrix_team"]["fallback_routes"][0]["provider"], "chatgpt")

    def test_roles_runtime_materializes_node_runtime_from_approved_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.set_prince2_role_tree_baseline(
                {
                    "status": "approved",
                    "source": "unit_test",
                    "tree": {
                        "nodes": [
                            {
                                "node_id": "management.project_manager",
                                "role_type": "project_manager",
                                "label": "Project Manager",
                                "parent_id": "board.executive",
                                "level": "management",
                                "accountability_boundary": "day-to-day management",
                                "delegated_authority": "authorizes work packages",
                                "responsibility_domain": "planning and control",
                                "context_scope": "stage plan and registers",
                                "context_rule": {"expansion_events": ["escalation", "stage_boundary_review"]},
                                "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                            }
                        ]
                    },
                    "flow": {
                        "edges": [
                            {
                                "edge_id": "authorize.project",
                                "source_node": "board.executive",
                                "target_node": "management.project_manager",
                            }
                        ]
                    },
                }
            )
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(root, "roles runtime")
            json_completed = run_main_capture(root, "roles runtime", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PRINCE2 node runtime:", completed.stdout)
            self.assertIn("Project Manager [management.project_manager]", completed.stdout)
            self.assertIn("state=ready", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles runtime")
            self.assertEqual(payload["status"], "materialized")
            self.assertEqual(payload["summary"]["nodes"], 1)
            self.assertEqual(payload["summary"]["ready"], 1)
            self.assertEqual(payload["runtime"]["nodes"][0]["node_id"], "management.project_manager")
            self.assertEqual(payload["runtime"]["nodes"][0]["wake_triggers"], ["escalation", "stage_boundary_review"])

    def test_roles_active_and_queues_render_runtime_supervision_views(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.set_prince2_role_tree_baseline(
                {
                    "status": "approved",
                    "source": "unit_test",
                    "tree": {
                        "nodes": [
                            {
                                "node_id": "management.project_manager",
                                "role_type": "project_manager",
                                "label": "Project Manager",
                                "context_rule": {"expansion_events": ["escalation"]},
                                "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                            },
                            {
                                "node_id": "delivery.team_manager",
                                "role_type": "team_manager",
                                "label": "Team Manager",
                                "context_rule": {"expansion_events": ["message_received"]},
                                "assignment": {"provider": "local", "provider_model": "provider-default"},
                            },
                        ]
                    },
                    "flow": {
                        "edges": [
                            {
                                "edge_id": "issue.work_package",
                                "source_node": "management.project_manager",
                                "target_node": "delivery.team_manager",
                                "payload_scope": ["assigned_work_package"],
                            }
                        ]
                    },
                }
            )
            prefs.save(root / ".stagewarden_models.json")

            run_main_capture(
                root,
                "role message management.project_manager delivery.team_manager issue.work_package payload=assigned_work_package",
                "--json",
            )
            active_completed = run_main_capture(root, "roles active", "--json")
            queues_completed = run_main_capture(root, "roles queues", "--json")

            self.assertEqual(active_completed.returncode, 0, active_completed.stderr)
            self.assertEqual(queues_completed.returncode, 0, queues_completed.stderr)
            active_payload = json.loads(active_completed.stdout)
            queues_payload = json.loads(queues_completed.stdout)
            self.assertEqual(active_payload["command"], "roles active")
            self.assertEqual(active_payload["count"], 2)
            self.assertEqual(queues_payload["command"], "roles queues")
            self.assertEqual(queues_payload["summary"]["inbox_total"], 1)
            self.assertEqual(queues_payload["summary"]["nodes_with_outbox"], 1)

    def test_roles_control_renders_board_facing_runtime_decision(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.set_prince2_role_tree_baseline(
                {
                    "status": "approved",
                    "source": "unit_test",
                    "tree": {
                        "nodes": [
                            {
                                "node_id": "management.project_manager",
                                "role_type": "project_manager",
                                "label": "Project Manager",
                                "context_rule": {"expansion_events": ["message_received"]},
                                "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                            },
                            {
                                "node_id": "delivery.team_manager",
                                "role_type": "team_manager",
                                "label": "Team Manager",
                                "context_rule": {"expansion_events": ["message_received"]},
                                "assignment": {"provider": "local", "provider_model": "provider-default"},
                            },
                        ]
                    },
                    "flow": {
                        "edges": [
                            {
                                "edge_id": "issue.work_package",
                                "source_node": "management.project_manager",
                                "target_node": "delivery.team_manager",
                                "payload_scope": ["assigned_work_package"],
                            }
                        ]
                    },
                }
            )
            prefs.save(root / ".stagewarden_models.json")

            run_main_capture(
                root,
                "role wait delivery.team_manager reason=await_assignment wake=message_received",
                "--json",
            )
            run_main_capture(
                root,
                "role message management.project_manager delivery.team_manager issue.work_package payload=assigned_work_package",
                "--json",
            )
            json_completed = run_main_capture(root, "roles control", "--json")
            text_completed = run_main_capture(root, "roles control")

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            self.assertEqual(text_completed.returncode, 0, text_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles control")
            self.assertEqual(payload["decision"]["next_action"], "process_queued_work")
            self.assertEqual(payload["decision"]["board_signal"], "attention")
            self.assertEqual(payload["queue_summary"]["inbox_total"], 1)
            self.assertIn("delivery.team_manager", {item["node_id"] for item in payload["critical_nodes"]})
            self.assertIn("PRINCE2 control view:", text_completed.stdout)
            self.assertIn("next_action=process_queued_work", text_completed.stdout)

    def test_roles_context_exposes_node_ai_context_packet(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.set_prince2_role_tree_baseline(
                {
                    "status": "approved",
                    "source": "unit_test",
                    "tree": {
                        "nodes": [
                            {
                                "node_id": "management.project_manager",
                                "role_type": "project_manager",
                                "label": "Project Manager",
                                "parent_id": "board.executive",
                                "level": "management",
                                "accountability_boundary": "day-to-day management",
                                "delegated_authority": "authorizes work packages",
                                "responsibility_domain": "planning and control",
                                "context_scope": "stage plan and registers",
                                "context_rule": {
                                    "include": ["stage_plan", "registers"],
                                    "exclude": ["board_private_decision_context"],
                                    "expansion_events": ["escalation", "stage_boundary_review"],
                                },
                                "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                            }
                        ]
                    },
                    "flow": {
                        "edges": [
                            {
                                "edge_id": "authorize.project",
                                "source_node": "board.executive",
                                "target_node": "management.project_manager",
                                "payload_scope": ["business_justification", "approved_tolerances"],
                            }
                        ]
                    },
                }
            )
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(root, "roles context management.project_manager")
            json_completed = run_main_capture(root, "roles context management.project_manager", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("PRINCE2 node AI context:", completed.stdout)
            self.assertIn("Project Manager [management.project_manager]", completed.stdout)
            self.assertIn("responsibility_domain: planning and control", completed.stdout)
            self.assertIn("communication_commands:", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "roles context")
            self.assertEqual(payload["node_id"], "management.project_manager")
            self.assertEqual(payload["role_type"], "project_manager")
            self.assertTrue(payload["agent_capabilities"]["core_tools"]["files"])
            self.assertIn("inspect_file", payload["agent_capabilities"]["model_actions"])
            self.assertIn("inspect_metadata_file", payload["agent_capabilities"]["file_operations"])
            self.assertIn("copy_path_file", payload["agent_capabilities"]["file_operations"])
            self.assertIn("chmod_path_file", payload["agent_capabilities"]["file_operations"])
            self.assertEqual(payload["prince2_role_context"]["context_include"], ["stage_plan", "registers"])
            self.assertEqual(payload["communications"]["incoming_edges"][0]["edge_id"], "authorize.project")

    def test_role_message_queues_governed_node_message_and_reports_inboxes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.set_prince2_role_tree_baseline(
                {
                    "status": "approved",
                    "source": "unit_test",
                    "tree": {
                        "nodes": [
                            {
                                "node_id": "management.project_manager",
                                "role_type": "project_manager",
                                "label": "Project Manager",
                                "parent_id": "board.executive",
                                "level": "management",
                                "accountability_boundary": "day-to-day management",
                                "delegated_authority": "authorizes work packages",
                                "responsibility_domain": "planning and control",
                                "context_scope": "stage plan and registers",
                                "context_rule": {"expansion_events": ["escalation", "stage_boundary_review"]},
                                "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                            },
                            {
                                "node_id": "delivery.team_manager",
                                "role_type": "team_manager",
                                "label": "Team Manager",
                                "parent_id": "management.project_manager",
                                "level": "delivery",
                                "accountability_boundary": "delivery execution",
                                "delegated_authority": "executes work packages",
                                "responsibility_domain": "delivery",
                                "context_scope": "assigned work package",
                                "context_rule": {"expansion_events": ["delivery_checkpoint"]},
                                "assignment": {"provider": "local", "provider_model": "provider-default"},
                            },
                        ]
                    },
                    "flow": {
                        "edges": [
                            {
                                "edge_id": "issue.work_package",
                                "source_node": "management.project_manager",
                                "target_node": "delivery.team_manager",
                                "flow_type": "delegation",
                                "payload_scope": ["assigned_work_package", "quality_criteria"],
                                "expected_evidence": ["work_package_description"],
                                "validation_condition": "delivery scoped",
                                "decision_authority": "Project Manager",
                                "return_path": "checkpoint",
                            }
                        ]
                    },
                }
            )
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(
                root,
                "role message management.project_manager delivery.team_manager issue.work_package payload=assigned_work_package,quality_criteria evidence=wp-001 summary=issue_work_package",
            )
            json_completed = run_main_capture(
                root,
                "role message management.project_manager delivery.team_manager issue.work_package payload=assigned_work_package,quality_criteria evidence=wp-001 summary=issue_work_package",
                "--json",
            )
            inbox = run_main_capture(root, "roles messages delivery.team_manager", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Queued PRINCE2 node message", completed.stdout)
            self.assertIn("delivery.team_manager", completed.stdout)
            self.assertIn("payload=assigned_work_package,quality_criteria", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            message_payload = json.loads(json_completed.stdout)
            self.assertEqual(message_payload["messages"]["command"], "roles messages")
            self.assertEqual(message_payload["messages"]["nodes"][0]["node_id"], "delivery.team_manager")
            self.assertEqual(message_payload["messages"]["nodes"][0]["inbox"][0]["edge_id"], "issue.work_package")

            self.assertEqual(inbox.returncode, 0, inbox.stderr)
            inbox_payload = json.loads(inbox.stdout)
            self.assertEqual(inbox_payload["command"], "roles messages")
            self.assertEqual(inbox_payload["count"], 1)
            self.assertEqual(inbox_payload["nodes"][0]["inbox"][0]["payload_scope"], ["assigned_work_package", "quality_criteria"])

    def test_role_message_rejects_payload_widening(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.set_prince2_role_tree_baseline(
                {
                    "status": "approved",
                    "source": "unit_test",
                    "tree": {
                        "nodes": [
                            {
                                "node_id": "management.project_manager",
                                "role_type": "project_manager",
                                "label": "Project Manager",
                                "context_rule": {"expansion_events": ["escalation"]},
                                "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                            },
                            {
                                "node_id": "delivery.team_manager",
                                "role_type": "team_manager",
                                "label": "Team Manager",
                                "context_rule": {"expansion_events": ["delivery_checkpoint"]},
                                "assignment": {"provider": "local", "provider_model": "provider-default"},
                            },
                        ]
                    },
                    "flow": {
                        "edges": [
                            {
                                "edge_id": "issue.work_package",
                                "source_node": "management.project_manager",
                                "target_node": "delivery.team_manager",
                                "flow_type": "delegation",
                                "payload_scope": ["assigned_work_package"],
                                "expected_evidence": ["work_package_description"],
                                "validation_condition": "delivery scoped",
                                "decision_authority": "Project Manager",
                                "return_path": "checkpoint",
                            }
                        ]
                    },
                }
            )
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(
                root,
                "role message management.project_manager delivery.team_manager issue.work_package payload=assigned_work_package,business_case_detail",
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Payload scope exceeds authorized PRINCE2 flow edge", completed.stdout)

    def test_role_wait_wake_and_tick_drive_prince2_node_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.set_prince2_role_tree_baseline(
                {
                    "status": "approved",
                    "source": "unit_test",
                    "tree": {
                        "nodes": [
                            {
                                "node_id": "management.project_manager",
                                "role_type": "project_manager",
                                "label": "Project Manager",
                                "context_rule": {"expansion_events": ["escalation"]},
                                "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                            },
                            {
                                "node_id": "delivery.team_manager",
                                "role_type": "team_manager",
                                "label": "Team Manager",
                                "context_rule": {"expansion_events": ["delivery_checkpoint"]},
                                "assignment": {"provider": "local", "provider_model": "provider-default"},
                            },
                        ]
                    },
                    "flow": {
                        "edges": [
                            {
                                "edge_id": "issue.work_package",
                                "source_node": "management.project_manager",
                                "target_node": "delivery.team_manager",
                                "flow_type": "delegation",
                                "payload_scope": ["assigned_work_package"],
                                "expected_evidence": ["work_package_description"],
                                "validation_condition": "delivery scoped",
                                "decision_authority": "Project Manager",
                                "return_path": "checkpoint",
                            }
                        ]
                    },
                }
            )
            prefs.save(root / ".stagewarden_models.json")

            wait_completed = run_main_capture(
                root,
                "role wait delivery.team_manager reason=await_delivery_checkpoint wake=delivery_checkpoint,message_received",
                "--json",
            )
            message_completed = run_main_capture(
                root,
                "role message management.project_manager delivery.team_manager issue.work_package payload=assigned_work_package",
                "--json",
            )
            wake_completed = run_main_capture(
                root,
                "role wake delivery.team_manager trigger=message_received",
                "--json",
            )
            tick_completed = run_main_capture(
                root,
                "role tick delivery.team_manager",
                "--json",
            )

            self.assertEqual(wait_completed.returncode, 0, wait_completed.stderr)
            wait_payload = json.loads(wait_completed.stdout)
            self.assertEqual(wait_payload["runtime"]["summary"]["waiting"], 1)

            self.assertEqual(message_completed.returncode, 0, message_completed.stderr)
            message_payload = json.loads(message_completed.stdout)
            self.assertEqual(message_payload["messages"]["nodes"][0]["inbox"][0]["edge_id"], "issue.work_package")

            self.assertEqual(wake_completed.returncode, 0, wake_completed.stderr)
            wake_payload = json.loads(wake_completed.stdout)
            wake_rows = {
                item["node_id"]: item
                for item in wake_payload["runtime"]["runtime"]["nodes"]
            }
            self.assertEqual(wake_rows["delivery.team_manager"]["state"], "ready")

            self.assertEqual(tick_completed.returncode, 0, tick_completed.stderr)
            tick_payload = json.loads(tick_completed.stdout)
            tick_rows = {
                item["node_id"]: item
                for item in tick_payload["runtime"]["runtime"]["nodes"]
            }
            self.assertEqual(tick_rows["delivery.team_manager"]["state"], "running")

    def test_roles_tick_advances_runtime_in_batch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.set_prince2_role_tree_baseline(
                {
                    "status": "approved",
                    "source": "unit_test",
                    "tree": {
                        "nodes": [
                            {
                                "node_id": "management.project_manager",
                                "role_type": "project_manager",
                                "label": "Project Manager",
                                "context_rule": {"expansion_events": ["escalation"]},
                                "assignment": {"provider": "chatgpt", "provider_model": "gpt-5.4"},
                            },
                            {
                                "node_id": "delivery.team_manager",
                                "role_type": "team_manager",
                                "label": "Team Manager",
                                "context_rule": {"expansion_events": ["delivery_checkpoint", "message_received"]},
                                "assignment": {"provider": "local", "provider_model": "provider-default"},
                            },
                        ]
                    },
                    "flow": {
                        "edges": [
                            {
                                "edge_id": "issue.work_package",
                                "source_node": "management.project_manager",
                                "target_node": "delivery.team_manager",
                                "flow_type": "delegation",
                                "payload_scope": ["assigned_work_package"],
                                "expected_evidence": ["work_package_description"],
                                "validation_condition": "delivery scoped",
                                "decision_authority": "Project Manager",
                                "return_path": "checkpoint",
                            }
                        ]
                    },
                }
            )
            prefs.save(root / ".stagewarden_models.json")

            wait_completed = run_main_capture(
                root,
                "role wait delivery.team_manager reason=await_assignment wake=message_received",
                "--json",
            )
            message_completed = run_main_capture(
                root,
                "role message management.project_manager delivery.team_manager issue.work_package payload=assigned_work_package",
                "--json",
            )
            batch_completed = run_main_capture(root, "roles tick", "--json")

            self.assertEqual(wait_completed.returncode, 0, wait_completed.stderr)
            self.assertEqual(message_completed.returncode, 0, message_completed.stderr)
            self.assertEqual(batch_completed.returncode, 0, batch_completed.stderr)
            payload = json.loads(batch_completed.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["result"]["command"], "roles tick")
            self.assertEqual(payload["result"]["woken"], 0)
            self.assertEqual(payload["result"]["progressed"], 2)
            rows = {
                item["node_id"]: item
                for item in payload["runtime"]["runtime"]["nodes"]
            }
            self.assertEqual(rows["management.project_manager"]["state"], "completed")
            self.assertEqual(rows["delivery.team_manager"]["state"], "running")
            self.assertEqual(payload["messages"]["nodes"][0]["inbox"], [])

    def test_project_design_report_exposes_capability_spec_project_spec_and_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "project design")
            json_completed = run_main_capture(root, "project design", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Project design packet:", completed.stdout)
            self.assertIn("Agent capability specification:", completed.stdout)
            self.assertIn("Project specification:", completed.stdout)
            self.assertIn("Clarification gaps:", completed.stdout)
            self.assertIn("missing_project_task", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "project design")
            self.assertIn("agent_capability_specification", payload)
            self.assertIn("project_specification", payload)
            self.assertIn("clarification_gaps", payload)
            self.assertFalse(payload["ready_for_ai_design"])
            codes = {item["code"] for item in payload["clarification_gaps"]}
            self.assertIn("missing_project_task", codes)
            self.assertIn("missing_project_objective", codes)
            self.assertIn("missing_project_scope", codes)
            self.assertIn("missing_expected_outputs", codes)
            self.assertIn("missing_delivery_mode", codes)

    def test_project_brief_commands_persist_and_feed_project_design(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            self.assertEqual(run_main_capture(root, "project brief set objective Build a governed coding agent").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set scope CLI, shell, git, and model routing").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set expected_outputs Production-ready CLI plus tests").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set delivery_mode hybrid").returncode, 0)

            brief = run_main_capture(root, "project brief")
            json_brief = run_main_capture(root, "project brief", "--json")
            design_json = run_main_capture(root, "project design", "--json")

            self.assertEqual(brief.returncode, 0, brief.stderr)
            self.assertIn("Project brief:", brief.stdout)
            self.assertIn("- objective: Build a governed coding agent", brief.stdout)

            self.assertEqual(json_brief.returncode, 0, json_brief.stderr)
            brief_payload = json.loads(json_brief.stdout)
            self.assertEqual(brief_payload["command"], "project brief")
            self.assertEqual(brief_payload["fields"]["delivery_mode"], "hybrid")

            self.assertEqual(design_json.returncode, 0, design_json.stderr)
            design_payload = json.loads(design_json.stdout)
            self.assertEqual(design_payload["project_specification"]["brief"]["objective"], "Build a governed coding agent")
            codes = {item["code"] for item in design_payload["clarification_gaps"]}
            self.assertNotIn("missing_project_objective", codes)
            self.assertNotIn("missing_project_scope", codes)
            self.assertNotIn("missing_expected_outputs", codes)
            self.assertNotIn("missing_delivery_mode", codes)

    def test_project_tree_propose_builds_proportional_review_proposal_from_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)

            self.assertEqual(run_main_capture(root, "project brief set objective Build a CLI coding agent").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set scope shell git model routing and browser login").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set expected_outputs CLI tests wet-run validation").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set delivery_mode hybrid").returncode, 0)

            completed = run_main_capture(root, "project tree propose")
            json_completed = run_main_capture(root, "project tree propose", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Project tree proposal:", completed.stdout)
            self.assertIn("delivery.implementation_team", completed.stdout)
            self.assertIn("assurance.validation_assurance", completed.stdout)
            self.assertIn("board.user_acceptance", completed.stdout)
            self.assertIn("approval_rule:", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "project tree propose")
            self.assertEqual(payload["status"], "ready_for_review")
            self.assertIn("delivery.implementation_team", payload["added_nodes"])
            self.assertEqual(payload["approval_rule"], "proposal only; user or Project Board must approve before persistence")
            node_ids = {item["node_id"] for item in payload["tree"]["nodes"]}
            self.assertIn("assurance.validation_assurance", node_ids)
            self.assertEqual(payload["clarification_gaps"], [])

    def test_project_tree_propose_ai_attaches_local_execution_candidates_when_discovered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = root / "run_model_ai_tree_and_local_stub.py"
            stub.write_text(
                "\n".join(
                    [
                        "#!/usr/bin/env python3",
                        "from __future__ import annotations",
                        "import json",
                        "import sys",
                        "",
                        "prompt = sys.argv[2] if len(sys.argv) > 2 else ''",
                        "if 'evaluating dynamically discovered local ollama models' in prompt.lower():",
                        "    print(json.dumps({",
                        "      'models': [",
                        "        {",
                        "          'id': 'qwen2.5-coder:7b',",
                        "          'summary': 'Preferred local coding executor.',",
                        "          'strengths': ['good coding speed'],",
                        "          'weaknesses': ['smaller context'],",
                        "          'best_for': ['delivery node execution'],",
                        "          'agentic_fit': 'high',",
                        "          'tool_support_risk': 'medium'",
                        "        },",
                        "        {",
                        "          'id': 'codestral:latest',",
                        "          'summary': 'Requires explicit tool validation.',",
                        "          'strengths': ['code prior'],",
                        "          'weaknesses': ['tool support uncertain'],",
                        "          'best_for': ['manual comparison'],",
                        "          'agentic_fit': 'low',",
                        "          'tool_support_risk': 'high'",
                        "        }",
                        "      ],",
                        "      'global_recommendation': 'Prefer qwen2.5-coder:7b for bounded delivery execution.'",
                        "    }))",
                        "else:",
                        "    print(json.dumps({",
                        "      'summary': 'Add release governance.',",
                        "      'tree_patches': []",
                        "    }))",
                        "raise SystemExit(0)",
                    ]
                ),
                encoding="utf-8",
            )
            stub.chmod(0o755)
            self.assertEqual(run_main_capture(root, "project brief set objective Build a CLI coding agent").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set scope shell git model routing and browser login").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set expected_outputs CLI tests wet-run validation").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set delivery_mode hybrid").returncode, 0)
            original = os.environ.get("RUN_MODEL_BIN")
            original_tags = os.environ.get("STAGEWARDEN_OLLAMA_TAGS_JSON")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = json.dumps(
                {
                    "models": [
                        {
                            "name": "qwen2.5-coder:7b",
                            "details": {"family": "qwen2", "parameter_size": "7.6B", "quantization_level": "Q4_K_M"},
                        },
                        {
                            "name": "codestral:latest",
                            "details": {"family": "llama", "parameter_size": "22.2B", "quantization_level": "Q4_0"},
                        },
                    ]
                }
            )
            try:
                completed = run_main_capture(root, "project tree propose --ai", "--json")
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original
                if original_tags is None:
                    os.environ.pop("STAGEWARDEN_OLLAMA_TAGS_JSON", None)
                else:
                    os.environ["STAGEWARDEN_OLLAMA_TAGS_JSON"] = original_tags

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["local_execution"]["ai_analysis"]["model"], "chatgpt")
            self.assertEqual(payload["local_execution"]["candidates"][0]["id"], "qwen2.5-coder:7b")
            self.assertEqual(
                payload["local_execution"]["message"],
                "Prefer qwen2.5-coder:7b for bounded delivery execution.",
            )
            implementation = next(item for item in payload["tree"]["nodes"] if item["node_id"] == "delivery.implementation_team")
            self.assertIn("qwen2.5-coder:7b", implementation["local_execution_candidates"])

    def test_project_tree_propose_ai_merges_model_suggestions_without_approval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = root / "run_model_ai_tree_stub.py"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "from __future__ import annotations\n"
                "import json\n"
                "print(json.dumps({\n"
                "  'summary': 'Add release governance for cross-platform delivery.',\n"
                "  'assumptions': ['Release evidence needs independent coordination.'],\n"
                "  'tree_patches': [{\n"
                "    'node_id': 'delivery.release_manager',\n"
                "    'role_type': 'team_manager',\n"
                "    'label': 'Release Team Manager',\n"
                "    'parent_id': 'management.project_manager',\n"
                "    'level': 'delivery',\n"
                "    'accountability_boundary': 'delegated release packaging and wet-run evidence inside stage tolerances',\n"
                "    'delegated_authority': 'coordinates release work packages and escalates forecast tolerance breaches'\n"
                "  }]\n"
                "}))\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            self.assertEqual(run_main_capture(root, "project brief set objective Build a CLI coding agent").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set scope shell git model routing and browser login").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set expected_outputs CLI tests wet-run validation").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set delivery_mode hybrid").returncode, 0)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                completed = run_main_capture(root, "project tree propose --ai")
                json_completed = run_main_capture(root, "project tree propose --ai", "--json")
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("AI assistance:", completed.stdout)
            self.assertIn("delivery.release_manager", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertTrue(payload["ai_requested"])
            self.assertTrue(payload["ai_assistance"]["ok"])
            self.assertEqual(payload["ai_assistance"]["model"], "chatgpt")
            self.assertIn("delivery.release_manager", payload["ai_assistance"]["valid_added_nodes"])
            self.assertIn("delivery.release_manager", payload["added_nodes"])
            release_node = next(item for item in payload["tree"]["nodes"] if item["node_id"] == "delivery.release_manager")
            self.assertEqual(release_node["role_type"], "team_manager")
            self.assertEqual(ModelPreferences.load(root / ".stagewarden_models.json").prince2_role_tree_baseline, {})
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")
            self.assertIn("project_tree_proposal_ai", [entry.phase for entry in handoff.entries])

    def test_project_tree_propose_ai_accepts_context_and_validation_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            stub = root / "run_model_ai_context_stub.py"
            stub.write_text(
                "#!/usr/bin/env python3\n"
                "from __future__ import annotations\n"
                "import json\n"
                "print(json.dumps({\n"
                "  'summary': 'Add release governance with bounded context.',\n"
                "  'tree_patches': [{\n"
                "    'node_id': 'delivery.release_manager',\n"
                "    'role_type': 'team_manager',\n"
                "    'label': 'Release Team Manager',\n"
                "    'parent_id': 'management.project_manager',\n"
                "    'level': 'delivery',\n"
                "    'accountability_boundary': 'release work package accountability only',\n"
                "    'delegated_authority': 'coordinate release validation and escalate tolerance breaches',\n"
                "    'responsibility_domain': 'release packaging and rollout evidence',\n"
                "    'context_scope': 'release package, rollout checklist, and wet-run evidence only',\n"
                "    'context_include': ['release_package', 'rollout_checklist', 'wet_run_evidence'],\n"
                "    'context_exclude': ['business_case_detail', 'unrelated_registers'],\n"
                "    'tolerance_boundary': 'work package release tolerance',\n"
                "    'validation_condition': 'release wet-run evidence exists',\n"
                "    'open_questions': ['Who approves release rollback?']\n"
                "  }]\n"
                "}))\n",
                encoding="utf-8",
            )
            stub.chmod(0o755)
            self.assertEqual(run_main_capture(root, "project brief set objective Build a CLI coding agent").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set scope shell git model routing release packaging").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set expected_outputs CLI tests wet-run validation").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set delivery_mode hybrid").returncode, 0)
            original = os.environ.get("RUN_MODEL_BIN")
            os.environ["RUN_MODEL_BIN"] = str(stub)
            try:
                completed = run_main_capture(root, "project tree propose --ai", "--json")
            finally:
                if original is None:
                    os.environ.pop("RUN_MODEL_BIN", None)
                else:
                    os.environ["RUN_MODEL_BIN"] = original

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            release_node = next(item for item in payload["tree"]["nodes"] if item["node_id"] == "delivery.release_manager")
            self.assertEqual(release_node["responsibility_domain"], "release packaging and rollout evidence")
            self.assertEqual(release_node["context_rule"]["include"], ["release_package", "rollout_checklist", "wet_run_evidence"])
            self.assertEqual(release_node["context_rule"]["exclude"], ["business_case_detail", "unrelated_registers"])
            self.assertEqual(release_node["tolerance_boundary"], "work package release tolerance")
            self.assertEqual(release_node["validation_condition"], "release wet-run evidence exists")
            self.assertEqual(release_node["open_questions"], ["Who approves release rollback?"])

    def test_project_tree_propose_reports_missing_brief_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "project tree propose", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["status"], "needs_clarification")
            codes = {item["code"] for item in payload["clarification_gaps"]}
            self.assertIn("missing_objective", codes)
            self.assertIn("missing_scope", codes)

    def test_project_tree_approve_blocks_until_brief_is_complete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            completed = run_main_capture(root, "project tree approve", "--json")

            self.assertEqual(completed.returncode, 1, completed.stdout)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["command"], "project tree approve")
            self.assertEqual(payload["status"], "blocked")
            codes = {item["code"] for item in payload["clarification_gaps"]}
            self.assertIn("missing_objective", codes)
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")
            self.assertEqual(prefs.prince2_role_tree_baseline, {})
            self.assertIn("project_tree_approval_blocked", [entry.phase for entry in handoff.entries])

    def test_project_tree_approve_persists_reviewed_proposal_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            self.assertEqual(run_main_capture(root, "project brief set objective Build a CLI coding agent").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set scope shell git model routing and browser login").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set expected_outputs CLI tests wet-run validation").returncode, 0)
            self.assertEqual(run_main_capture(root, "project brief set delivery_mode hybrid").returncode, 0)

            completed = run_main_capture(root, "project tree approve")
            json_completed = run_main_capture(root, "roles baseline", "--json")
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Project tree approval:", completed.stdout)
            self.assertIn("- status: approved", completed.stdout)
            self.assertIn("delivery.implementation_team", completed.stdout)
            self.assertEqual((prefs.prince2_role_tree_baseline or {}).get("source"), "project_tree_approve")
            self.assertEqual((handoff.prince2_role_tree_baseline or {}).get("source"), "project_tree_approve")
            self.assertIn("project_tree_approval", [entry.phase for entry in handoff.entries])
            proposal = (prefs.prince2_role_tree_baseline or {}).get("proposal", {})
            self.assertIn("delivery.implementation_team", proposal.get("added_nodes", []))
            node_ids = {item["node_id"] for item in (prefs.prince2_role_tree_baseline or {})["tree"]["nodes"]}
            self.assertIn("delivery.implementation_team", node_ids)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["baseline"]["source"], "project_tree_approve")

    def test_handoff_actions_renders_action_entries_and_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            handoff = ProjectHandoff.load(root / ".stagewarden_handoff.json")
            handoff.record_action(
                phase="project_tree_approval",
                summary="Project tree approved.",
                task="project tree approve",
                git_head="abc123",
                details={"forced": False, "added_nodes": ["delivery.implementation_team"]},
            )
            handoff.record_action(
                phase="project_start_blocked",
                summary="Project start blocked.",
                task="project start",
                git_head="def456",
                details={"proposal_status": "needs_clarification"},
            )
            handoff.save(root / ".stagewarden_handoff.json")

            completed = run_main_capture(root, "handoff actions")
            json_completed = run_main_capture(root, "handoff actions 1", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("Handoff actions:", completed.stdout)
            self.assertIn("project_tree_approval", completed.stdout)
            self.assertIn("project_start_blocked", completed.stdout)

            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertEqual(payload["command"], "handoff actions")
            self.assertEqual(payload["count"], 2)
            self.assertEqual(payload["limit"], 1)
            self.assertEqual(len(payload["entries"]), 1)
            self.assertEqual(payload["entries"][0]["phase"], "project_start_blocked")

    def test_sources_status_reports_external_reference_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            source_root = root / "external_sources" / "codex"
            docs = root / "docs"
            docs.mkdir()
            source_root.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=source_root, capture_output=True, text=True, check=True)
            subprocess.run(["git", "remote", "add", "origin", "https://github.com/openai/codex"], cwd=source_root, capture_output=True, text=True, check=True)
            (source_root / "README.md").write_text("reference\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=source_root, capture_output=True, text=True, check=True)
            subprocess.run(
                ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init"],
                cwd=source_root,
                capture_output=True,
                text=True,
                check=True,
            )
            (docs / "source_references.md").write_text(
                "\n".join(
                    [
                        "| Project | Local path | Upstream | Purpose | License/source note |",
                        "| --- | --- | --- | --- | --- |",
                        "| OpenAI Codex CLI | `external_sources/codex` | `https://github.com/openai/codex` | Study. | Public. |",
                    ]
                ),
                encoding="utf-8",
            )

            completed = run_main_capture(root, "sources status")
            json_completed = run_main_capture(root, "sources status", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("External source references:", completed.stdout)
            self.assertIn("OpenAI Codex CLI: OK ok", completed.stdout)
            self.assertIn("upstream=https://github.com/openai/codex", completed.stdout)
            self.assertEqual(json_completed.returncode, 0, json_completed.stderr)
            payload = json.loads(json_completed.stdout)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["items"][0]["project"], "OpenAI Codex CLI")

    def test_sources_status_strict_and_update_fast_forward(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            remote = root / "remote.git"
            source_root = root / "external_sources" / "codex"
            seed = root / "seed"
            docs = root / "docs"
            docs.mkdir()
            subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True, text=True, check=True)
            subprocess.run(["git", "clone", str(remote), str(seed)], capture_output=True, text=True, check=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=seed, capture_output=True, text=True, check=True)
            (seed / "README.md").write_text("v1\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "v1"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=remote, capture_output=True, text=True, check=True)
            subprocess.run(["git", "clone", str(remote), str(source_root)], capture_output=True, text=True, check=True)
            (docs / "source_references.md").write_text(
                "\n".join(
                    [
                        "| Project | Local path | Upstream | Purpose | License/source note |",
                        "| --- | --- | --- | --- | --- |",
                        f"| OpenAI Codex CLI | `external_sources/codex` | `{remote}` | Study. | Public. |",
                    ]
                ),
                encoding="utf-8",
            )

            strict = run_main_capture(root, "sources status --strict", "--json")
            self.assertEqual(strict.returncode, 0, strict.stderr)
            self.assertTrue(json.loads(strict.stdout)["ok"])

            (seed / "README.md").write_text("v2\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "v2"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=seed, capture_output=True, text=True, check=True)

            updated = run_main_capture(root, "sources update", "--json")
            self.assertEqual(updated.returncode, 0, updated.stderr)
            payload = json.loads(updated.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["items"][0]["updated"])
            self.assertEqual((source_root / "README.md").read_text(encoding="utf-8"), "v2\n")

            actions = run_main_capture(root, "handoff actions", "3", "--json")
            phases = [entry["phase"] for entry in json.loads(actions.stdout)["entries"]]
            self.assertIn("sources_update", phases)

    def test_update_status_check_and_apply_fast_forward(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            remote = root / "remote.git"
            seed = root / "seed"
            work = root / "work"
            subprocess.run(["git", "init", "--bare", str(remote)], capture_output=True, text=True, check=True)
            subprocess.run(["git", "clone", str(remote), str(seed)], capture_output=True, text=True, check=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=seed, capture_output=True, text=True, check=True)
            (seed / "README.md").write_text("v1\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "v1"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=remote, capture_output=True, text=True, check=True)
            subprocess.run(["git", "clone", str(remote), str(work)], capture_output=True, text=True, check=True)

            status = run_main_capture(work, "update status", "--json")
            self.assertEqual(status.returncode, 0, status.stderr)
            status_payload = json.loads(status.stdout)
            self.assertFalse(status_payload["update_available"])
            self.assertEqual(status_payload["behind"], 0)

            (seed / "README.md").write_text("v2\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "v2"], cwd=seed, capture_output=True, text=True, check=True)
            subprocess.run(["git", "push", "origin", "main"], cwd=seed, capture_output=True, text=True, check=True)

            check = run_main_capture(work, "update check --json")
            self.assertEqual(check.returncode, 0, check.stderr)
            check_payload = json.loads(check.stdout)
            self.assertTrue(check_payload["update_available"])
            self.assertEqual(check_payload["behind"], 1)

            blocked = run_main_capture(work, "update apply", "--json")
            self.assertNotEqual(blocked.returncode, 0)
            blocked_payload = json.loads(blocked.stdout)
            self.assertTrue(blocked_payload["needs_confirmation"])

            applied = run_main_capture(work, "update apply --yes", "--json")
            self.assertEqual(applied.returncode, 0, applied.stderr)
            applied_payload = json.loads(applied.stdout)
            self.assertTrue(applied_payload["ok"])
            self.assertTrue(applied_payload["applied"])
            self.assertEqual((work / "README.md").read_text(encoding="utf-8"), "v2\n")

            actions = run_main_capture(work, "handoff actions", "3", "--json")
            phases = [entry["phase"] for entry in json.loads(actions.stdout)["entries"]]
            self.assertIn("update_apply", phases)

    def test_update_apply_refuses_dirty_worktree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            subprocess.run(["git", "init"], cwd=root, capture_output=True, text=True, check=True)
            subprocess.run(["git", "branch", "-M", "main"], cwd=root, capture_output=True, text=True, check=True)
            (root / "README.md").write_text("dirty\n", encoding="utf-8")
            result = run_main_capture(root, "update apply --yes", "--json")
            self.assertNotEqual(result.returncode, 0)
            payload = json.loads(result.stdout)
            self.assertFalse(payload["ok"])

    def test_external_io_cli_download_records_evidence(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                body = b"downloaded by stagewarden\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            try:
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            except PermissionError as exc:
                self.skipTest(f"local HTTP bind unavailable: {exc}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_port}/artifact.txt"
                downloaded = run_main_capture(root, "download", url, "artifacts/artifact.txt", "--json")
                self.assertEqual(downloaded.returncode, 0, downloaded.stderr)
                payload = json.loads(downloaded.stdout)
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["path"], "artifacts/artifact.txt")
                self.assertTrue(payload["sha256"])
                self.assertTrue((root / "artifacts/artifact.txt").exists())

                checksum = run_main_capture(root, "checksum", "artifacts/artifact.txt", "--json")
                self.assertEqual(checksum.returncode, 0, checksum.stderr)
                checksum_payload = json.loads(checksum.stdout)
                self.assertEqual(checksum_payload["sha256"], payload["sha256"])

                actions = run_main_capture(root, "handoff actions", "5", "--json")
                self.assertEqual(actions.returncode, 0, actions.stderr)
                action_payload = json.loads(actions.stdout)
                phases = [entry["phase"] for entry in action_payload["entries"]]
                self.assertIn("download_file", phases)
                self.assertIn("checksum_file", phases)

                transcript = run_main_capture(root, "transcript", "--json")
                self.assertEqual(transcript.returncode, 0, transcript.stderr)
                transcript_payload = json.loads(transcript.stdout)
                self.assertGreaterEqual(transcript_payload["report"]["count"], 2)
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()

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

    def test_interactive_shell_guided_account_choice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO(
                "account add openai lavoro OPENAI_API_KEY_WORK\n"
                "account add openai personale OPENAI_API_KEY_PERSONAL\n"
                "account choose openai\n"
                "2\n"
                "accounts\n"
                "exit\n"
            )
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()
            prefs = ModelPreferences.load(root / ".stagewarden_models.json")

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("openai"), "personale")
            self.assertIn("Choose account for openai:", rendered)
            self.assertIn("Active account for openai set to personale.", rendered)
            self.assertIn("account personale:", rendered)
            self.assertIn("active-account", rendered)

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

                original_run = main_module.CodexBrowserLoginFlow.run

                def fake_run(self):  # noqa: ANN001
                    from stagewarden.auth import AuthResult

                    return AuthResult(
                        True,
                        "Logged in using ChatGPT",
                        secret_payload='{"auth_source":"codex","login_method":"browser","model":"chatgpt","account":"personale"}',
                    )

                main_module.CodexBrowserLoginFlow.run = fake_run
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account login chatgpt personale\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                prefs = ModelPreferences.load(root / ".stagewarden_models.json")
                from stagewarden.secrets import SecretStore

                loaded = SecretStore().load_token("chatgpt", "personale")
            finally:
                main_module.CodexBrowserLoginFlow.run = original_run
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

            self.assertEqual(code, 0)
            self.assertEqual((prefs.active_account_by_model or {}).get("chatgpt"), "personale")
            self.assertTrue(loaded.ok, loaded.message)
            self.assertIn('"auth_source":"codex"', loaded.secret)
            self.assertIn("Logged in using ChatGPT", rendered)
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

    def test_interactive_shell_logs_out_chatgpt_account_via_codex_and_clears_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = root / "secrets"
            original_store = os.environ.get("STAGEWARDEN_SECRET_STORE_DIR")
            os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = str(store)
            try:
                import stagewarden.main as main_module

                original_logout = main_module.CodexBrowserLogoutFlow.run

                def fake_logout(self):  # noqa: ANN001
                    from stagewarden.auth import AuthResult

                    return AuthResult(True, "Logged out.")

                prefs = ModelPreferences.default()
                prefs.add_account("chatgpt", "personale")
                prefs.set_active_account("chatgpt", "personale")
                prefs.save(root / ".stagewarden_models.json")
                SecretStore().save_token("chatgpt", "personale", '{"auth_source":"codex"}')

                main_module.CodexBrowserLogoutFlow.run = fake_logout
                config = AgentConfig(workspace_root=root, max_steps=1)
                input_stream = StringIO("account logout chatgpt personale\naccounts\nexit\n")
                output_stream = StringIO()
                code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
                rendered = output_stream.getvalue()
                loaded = SecretStore().load_token("chatgpt", "personale")
            finally:
                main_module.CodexBrowserLogoutFlow.run = original_logout
                if original_store is None:
                    os.environ.pop("STAGEWARDEN_SECRET_STORE_DIR", None)
                else:
                    os.environ["STAGEWARDEN_SECRET_STORE_DIR"] = original_store

            self.assertEqual(code, 0)
            self.assertFalse(loaded.ok)
            self.assertIn("Logged out.", rendered)

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
            memory = MemoryStore()
            memory.record_attempt(
                iteration=3,
                step_id="step-3",
                model="chatgpt",
                account="work",
                variant="gpt-5.3-codex",
                action_type="shell",
                action_signature="python3 -m unittest",
                success=False,
                observation="usage limit encountered, retry needed",
                error_type="runtime",
            )
            memory.record_tool_transcript(
                iteration=3,
                step_id="step-3",
                tool="shell",
                action_type="shell",
                success=False,
                summary="tests blocked by provider limit",
                duration_ms=555,
                error_type="runtime",
            )
            memory.save(root / ".stagewarden_memory.json")
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
                "entries": [
                    {
                        "phase": "git_snapshot",
                        "iteration": 3,
                        "step_id": "step-3",
                        "step_status": "failed",
                        "model": "chatgpt",
                        "action_type": "git_snapshot",
                        "summary": "stagewarden: step step-3 failed [stage=at_risk boundary=review]",
                        "detail": "",
                        "git_head": "ff22aa9",
                        "timestamp": "2026-04-18T18:32:00+00:00",
                    }
                ],
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
            self.assertIn("PRINCE2 roles:", rendered)
            self.assertIn("prince2_role_baseline: missing", rendered)
            self.assertIn("Provider limit status:", rendered)
            self.assertIn("chatgpt: enabled active provider_model=automatic-by-task selection=automatic active_account=none", rendered)
            self.assertIn("last_attempt: step=step-3 status=failed:runtime account=work provider_model=gpt-5.3-codex", rendered)
            self.assertIn("Resume context:", rendered)
            self.assertIn("latest_model_attempt: step=step-3 action=shell status=failed:runtime", rendered)
            self.assertIn("latest_route: provider=chatgpt account=work provider_model=gpt-5.3-codex", rendered)
            self.assertIn("latest_tool_evidence: tool=shell action=shell status=failed:runtime duration_ms=555", rendered)
            self.assertIn("latest_git_snapshot: ff22aa9 :: stagewarden: step step-3 failed [stage=at_risk boundary=review]", rendered)
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
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "local"]
            prefs.preferred_model = "chatgpt"
            prefs.add_account("chatgpt", "work")
            prefs.set_active_account("chatgpt", "work")
            prefs.set_variant("chatgpt", "gpt-5.3-codex")
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.save(root / ".stagewarden_models.json")
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
            memory = MemoryStore()
            memory.record_attempt(
                iteration=1,
                step_id="step-3",
                model="chatgpt",
                account="work",
                variant="gpt-5.3-codex",
                action_type="shell",
                action_signature="pytest",
                success=False,
                observation="usage limit hit",
                error_type="runtime",
            )
            memory.save(root / ".stagewarden_memory.json")
            config = AgentConfig(workspace_root=root, max_steps=1)
            input_stream = StringIO("overview\nboard\nreport\nexit\n")
            output_stream = StringIO()
            code = run_interactive_shell(config, input_stream=input_stream, output_stream=output_stream)
            rendered = output_stream.getvalue()

            self.assertEqual(code, 0)
            self.assertIn("Workspace overview:", rendered)
            self.assertIn("recommended_authorization: review", rendered)
            self.assertIn("provider_limits: providers=2 blocked_models=chatgpt", rendered)
            self.assertIn("Board review:", rendered)
            self.assertIn("Project report:", rendered)
            self.assertIn("provider_limits: providers=2 blocked_models=chatgpt stale_models=none", rendered)
            self.assertIn("boundary_decision: continue_current_stage", rendered)

    def test_status_full_reports_limit_summary_and_stale_remediation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            prefs = ModelPreferences.default()
            prefs.enabled_models = ["chatgpt", "local"]
            prefs.blocked_until_by_model = {"chatgpt": "2026-05-01T18:30"}
            prefs.set_model_limit_snapshot(
                "chatgpt",
                {
                    "status": "blocked",
                    "reason": "usage_limit",
                    "blocked_until": "2026-05-01T18:30",
                    "rate_limit_type": "usage_limit",
                    "captured_at": "2000-01-01T17:30",
                    "raw_message": "Usage limit reached at 91%. Try again at 8:05 PM.",
                },
            )
            prefs.save(root / ".stagewarden_models.json")

            completed = run_main_capture(root, "status", "--full", "--json")

            self.assertEqual(completed.returncode, 0, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["limits_summary"]["blocked_models"], ["chatgpt"])
            self.assertEqual(payload["limits_summary"]["stale_models"], ["chatgpt"])
            remediation_codes = {item["code"] for item in payload["remediations"]}
            self.assertIn("provider_limits_stale", remediation_codes)

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
            self.assertIn("- active_route: provider=", rendered)
            self.assertIn("- resume_ready: true", rendered)
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
            self.assertIn("- boundary_decision:", rendered)
            self.assertIn("- active_route: provider=", rendered)
            self.assertIn("- latest_model_attempt: step=step-7 action=write_file status=failed:invalid_output", rendered)
            self.assertIn("- latest_route: provider=openai account=work provider_model=gpt-5.4-mini", rendered)
            self.assertIn("- latest_tool_evidence: tool=files action=write_file status=failed:invalid_output duration_ms=245", rendered)
            self.assertIn("- latest_git_snapshot: ff00aa1 :: stagewarden: step step-7 failed [stage=at_risk boundary=review]", rendered)
            self.assertIn("- resume_ready: true", rendered)

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
            self.assertIn("- latest_route: provider=openai account=work provider_model=gpt-5.4-mini", exported)
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
