from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stagewarden.config import AgentConfig
from stagewarden.permissions import PermissionPolicy, PermissionSettings
from stagewarden.tools.git import GitTool
from stagewarden.tools.files import FileTool
from stagewarden.tools.shell import ShellTool
from stagewarden.textcodec import detect_confusables


class ToolTests(unittest.TestCase):
    def test_git_tool_initializes_repository_and_commits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tool = GitTool(AgentConfig(workspace_root=root))
            ready = tool.ensure_ready()
            self.assertTrue(ready.ok, ready.error)
            self.assertTrue((root / ".git").exists())

            (root / "hello.txt").write_text("hello\n", encoding="utf-8")
            committed = tool.commit_if_changed("test: commit hello")
            self.assertTrue(committed.ok, committed.error)
            self.assertFalse(tool.has_changes())

    def test_git_tool_exposes_status_log_show_and_file_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tool = GitTool(AgentConfig(workspace_root=root))
            self.assertTrue(tool.ensure_ready().ok)

            (root / "hello.txt").write_text("hello\n", encoding="utf-8")
            first = tool.commit_if_changed("test: first")
            self.assertTrue(first.ok, first.error)
            (root / "hello.txt").write_text("hello again\n", encoding="utf-8")
            second = tool.commit_if_changed("test: second")
            self.assertTrue(second.ok, second.error)

            status = tool.status()
            log = tool.log(limit=5)
            show = tool.show(revision="HEAD", stat=True)
            history = tool.file_history("hello.txt", limit=5)

            self.assertTrue(status.ok, status.error)
            self.assertIn("##", status.stdout)
            self.assertTrue(log.ok, log.error)
            self.assertIn("test: second", log.stdout)
            self.assertTrue(show.ok, show.error)
            self.assertIn("hello.txt", show.stdout)
            self.assertTrue(history.ok, history.error)
            self.assertIn("test: first", history.stdout)

    def test_file_tool_search_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "src").mkdir()
            (root / "src" / "main.py").write_text("print('hello')\nname = 'x'\n")
            (root / "README.md").write_text("hello\n")
            tool = FileTool(AgentConfig(workspace_root=root))

            listed = tool.list_files(pattern="*.py")
            self.assertTrue(listed.ok)
            self.assertIn("src/main.py", listed.content)

            found = tool.search("hello", glob="*.md")
            self.assertTrue(found.ok)
            self.assertIn("README.md:1:hello", found.content)

    def test_shell_tool_returns_preview_and_duration(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir)))
            result = tool.run("python3 -c \"print('ok')\"")
            self.assertTrue(result.ok)
            self.assertIn("exit_code=0", result.output_preview)
            self.assertGreaterEqual(result.duration_ms, 0)

    def test_shell_tool_resolves_relative_cwd_inside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "sub").mkdir()
            tool = ShellTool(AgentConfig(workspace_root=root))
            result = tool.run("pwd", cwd="sub")
            self.assertTrue(result.ok, result.error)
            self.assertEqual(Path(result.stdout).resolve(), (root / "sub").resolve())

    def test_shell_tool_rejects_cwd_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir)))
            result = tool.run("pwd", cwd="..")
            self.assertFalse(result.ok)
            self.assertIn("outside the workspace", result.error)

    def test_shell_tool_builds_windows_command_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir)))
            tool.is_windows = True
            tool._windows_shell = lambda: "powershell"  # type: ignore[method-assign]
            args = tool._command_args("python --version")
            self.assertEqual(args[:5], ["powershell", "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy"])
            self.assertIn("-Command", args)
            self.assertEqual(args[-1], "python --version")

    def test_shell_tool_builds_windows_cmd_args(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir)))
            tool.is_windows = True
            tool._windows_shell = lambda: "cmd"  # type: ignore[method-assign]
            self.assertEqual(tool._command_args("dir"), ["cmd", "/d", "/s", "/c", "dir"])

    def test_shell_tool_builds_unix_session_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir)))
            tool.is_windows = False
            payload = tool._session_payload("pwd", "MARK").decode()
            self.assertIn("printf 'MARK:%s", payload)

    def test_shell_tool_persistent_session(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir)))
            created = tool.create_session()
            self.assertTrue(created.ok)
            session_id = created.session_id

            first = tool.send_session(session_id, "pwd")
            self.assertTrue(first.ok)
            self.assertIn("session_id=", first.output_preview)

            second = tool.send_session(session_id, "python3 -c \"print('alive')\"")
            self.assertTrue(second.ok)
            self.assertIn("alive", second.stdout)

            closed = tool.close_session(session_id)
            self.assertTrue(closed.ok)

    def test_file_tool_patch_files_add_update_delete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "keep.txt").write_text("before\n")
            (root / "delete.txt").write_text("old\n")
            tool = FileTool(AgentConfig(workspace_root=root))
            diff = "\n".join(
                [
                    "--- a/keep.txt",
                    "+++ b/keep.txt",
                    "@@ -1,1 +1,1 @@",
                    "-before",
                    "+after",
                    "--- /dev/null",
                    "+++ b/new.txt",
                    "@@ -0,0 +1,1 @@",
                    "+created",
                    "--- a/delete.txt",
                    "+++ /dev/null",
                    "@@ -1,1 +0,0 @@",
                    "-old",
                ]
            )
            result = tool.patch_files(diff)
            self.assertTrue(result.ok)
            self.assertEqual((root / "keep.txt").read_text(), "after\n")
            self.assertEqual((root / "new.txt").read_text(), "created\n")
            self.assertFalse((root / "delete.txt").exists())

    def test_file_tool_writes_ascii_safe_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tool = FileTool(AgentConfig(workspace_root=root, strict_ascii_output=True))
            result = tool.write("unicode.txt", "Màrio Привет 你好 Ω")
            self.assertTrue(result.ok)
            content = (root / "unicode.txt").read_text(encoding="utf-8")
            self.assertEqual(content, r"M\xe0rio \u041f\u0440\u0438\u0432\u0435\u0442 \u4f60\u597d \u03a9")

    def test_file_tool_can_allow_unicode_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tool = FileTool(AgentConfig(workspace_root=root, strict_ascii_output=False))
            result = tool.write("unicode.data", "Màrio Привет 你好 Ω")
            self.assertTrue(result.ok)
            content = (root / "unicode.data").read_text(encoding="utf-8")
            self.assertEqual(content, "Màrio Привет 你好 Ω")

    def test_sensitive_file_forces_ascii_even_when_unicode_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tool = FileTool(AgentConfig(workspace_root=root, strict_ascii_output=False))
            result = tool.write(".state.json", "Привет")
            self.assertTrue(result.ok)
            self.assertIn("sensitive_file_ascii_forced", result.warnings or [])
            content = (root / ".state.json").read_text(encoding="utf-8")
            self.assertEqual(content, r"\u041f\u0440\u0438\u0432\u0435\u0442")

    def test_shell_output_is_ascii_safe_in_strict_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir), strict_ascii_output=True))
            result = tool.run("python3 -c \"print('Привет Ω')\"")
            self.assertTrue(result.ok)
            self.assertIn(r"\u041f\u0440\u0438\u0432\u0435\u0442", result.stdout)
            self.assertIn(r"\u03a9", result.stdout)

    def test_confusable_detection_warns_on_mixed_scripts(self) -> None:
        warnings = detect_confusables("AΑ pр")
        self.assertTrue(any(item.startswith("mixed_scripts:") for item in warnings))

    def test_permission_policy_plan_mode_blocks_write_capabilities(self) -> None:
        policy = PermissionPolicy(PermissionSettings(default_mode="plan"))
        self.assertTrue(policy.decide("shell:read", "git status").allowed)
        self.assertFalse(policy.decide("shell:write", "python3 -c print(1)").allowed)
        self.assertFalse(policy.decide("file:write", "notes.txt").allowed)

    def test_permission_policy_explicit_allow_overrides_dont_ask_for_specific_capability(self) -> None:
        policy = PermissionPolicy(
            PermissionSettings(
                default_mode="dont_ask",
                allow=["shell:python3 -c", "file:allowed.txt"],
            )
        )
        self.assertTrue(policy.decide("shell:write", "python3 -c \"print('ok')\"").allowed)
        self.assertTrue(policy.decide("file:write", "allowed.txt").allowed)
        self.assertFalse(policy.decide("file:write", "blocked.txt").allowed)

    def test_permission_policy_explicit_allow_overrides_matching_ask_rule(self) -> None:
        policy = PermissionPolicy(
            PermissionSettings(
                allow=["file:allowed.txt"],
                ask=["file:allowed.txt"],
            )
        )
        self.assertTrue(policy.decide("file:write", "allowed.txt").allowed)

    def test_shell_tool_enforces_plan_mode_from_settings_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            PermissionSettings(default_mode="plan").save(root / ".stagewarden_settings.json")
            tool = ShellTool(AgentConfig(workspace_root=root))
            result = tool.run("python3 -c \"print('blocked')\"")
            self.assertFalse(result.ok)
            self.assertIn("Plan mode", result.error)

    def test_shell_tool_allows_read_only_git_commands_in_plan_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            PermissionSettings(default_mode="plan").save(root / ".stagewarden_settings.json")
            tool = ShellTool(AgentConfig(workspace_root=root))
            result = tool.run("git status")
            self.assertFalse(result.ok)
            self.assertNotIn("Plan mode", result.error)

    def test_shell_tool_blocks_write_git_commands_in_plan_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            PermissionSettings(default_mode="plan").save(root / ".stagewarden_settings.json")
            tool = ShellTool(AgentConfig(workspace_root=root))
            result = tool.run("git add README.md")
            self.assertFalse(result.ok)
            self.assertIn("Plan mode", result.error)

    def test_shell_tool_blocks_redirection_in_plan_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            PermissionSettings(default_mode="plan").save(root / ".stagewarden_settings.json")
            tool = ShellTool(AgentConfig(workspace_root=root))
            result = tool.run("echo hi > out.txt")
            self.assertFalse(result.ok)
            self.assertIn("Plan mode", result.error)

    def test_shell_tool_blocks_package_install_in_plan_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            PermissionSettings(default_mode="plan").save(root / ".stagewarden_settings.json")
            tool = ShellTool(AgentConfig(workspace_root=root))
            result = tool.run("npm install left-pad")
            self.assertFalse(result.ok)
            self.assertIn("Plan mode", result.error)

    def test_file_tool_enforces_ask_rule_from_settings_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            PermissionSettings(ask=["file:secret.txt"]).save(root / ".stagewarden_settings.json")
            tool = FileTool(AgentConfig(workspace_root=root))
            result = tool.write("secret.txt", "classified\n")
            self.assertFalse(result.ok)
            self.assertIn("requires approval", result.error)


if __name__ == "__main__":
    unittest.main()
