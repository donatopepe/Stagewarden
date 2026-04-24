from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import tempfile
import threading
import unittest
from pathlib import Path

from stagewarden.config import AgentConfig
from stagewarden.permissions import PermissionPolicy, PermissionSettings
from stagewarden.runtime_env import select_shell_backend
from stagewarden.shell_compat import command_requires_posix_shell, prepare_command_for_shell, shell_env_reference, shell_path_literal, shell_quote
from stagewarden.tools.git import GitTool
from stagewarden.tools.external_io import ExternalIOTool
from stagewarden.tools.files import FileTool
from stagewarden.tools.shell import ShellTool
from stagewarden.textcodec import detect_confusables


class ToolTests(unittest.TestCase):
    def test_external_io_download_checksum_compress_and_verify(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                body = b"stagewarden external io wet-run\n"
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
                tool = ExternalIOTool(root, max_bytes=1024)
                url = f"http://127.0.0.1:{server.server_port}/artifact.txt"
                downloaded = tool.download(url, "artifacts/artifact.txt")
                self.assertTrue(downloaded.ok, downloaded.error)
                self.assertEqual(downloaded.bytes_written, len(b"stagewarden external io wet-run\n"))
                self.assertTrue(downloaded.sha256)

                checksum = tool.checksum("artifacts/artifact.txt")
                self.assertTrue(checksum.ok, checksum.error)
                self.assertEqual(checksum.sha256, downloaded.sha256)

                compressed = tool.gzip_compress("artifacts/artifact.txt")
                self.assertTrue(compressed.ok, compressed.error)
                self.assertTrue((root / "artifacts/artifact.txt.gz").exists())

                verified = tool.verify_archive("artifacts/artifact.txt.gz")
                self.assertTrue(verified.ok, verified.error)
                self.assertIn("uncompressed", verified.message)
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()

    def test_external_io_rejects_unsafe_url_and_workspace_escape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ExternalIOTool(Path(tmp_dir))
            blocked_url = tool.download("file:///etc/passwd", "passwd")
            self.assertFalse(blocked_url.ok)
            self.assertIn("Only http and https", blocked_url.error or "")
            blocked_path = tool.checksum("../outside.txt")
            self.assertFalse(blocked_path.ok)
            self.assertIn("inside the workspace", blocked_path.error or "")

    def test_external_io_web_search_parses_json_results(self) -> None:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                body = json.dumps({"results": [{"title": "Stagewarden", "url": "https://example.test", "snippet": "Agent"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        with tempfile.TemporaryDirectory() as tmp_dir:
            try:
                server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            except PermissionError as exc:
                self.skipTest(f"local HTTP bind unavailable: {exc}")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                result = ExternalIOTool(Path(tmp_dir)).web_search(
                    "stagewarden",
                    endpoint=f"http://127.0.0.1:{server.server_port}/search",
                )
                self.assertTrue(result.ok, result.error)
                self.assertEqual(result.items[0]["title"], "Stagewarden")
            finally:
                server.shutdown()
                thread.join(timeout=2)
                server.server_close()

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

    def test_git_tool_ignores_runtime_settings_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            tool = GitTool(AgentConfig(workspace_root=root))

            ensured = tool.ensure_runtime_ignores()

            self.assertTrue(ensured.ok, ensured.error)
            gitignore = (root / ".gitignore").read_text(encoding="utf-8")
            self.assertIn(".stagewarden_settings.json", gitignore)

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

    def test_file_tool_inspect_detects_encoding_and_reports_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sample = root / "sample.txt"
            sample.write_text("ciao\nseconda riga\n", encoding="utf-8")
            tool = FileTool(AgentConfig(workspace_root=root))

            result = tool.inspect("sample.txt")

            self.assertTrue(result.ok, result.error)
            self.assertEqual(result.report["encoding"], "utf-8")
            self.assertEqual(result.report["line_count"], 2)
            self.assertEqual(result.report["newline"], "\n")

    def test_file_tool_structured_edit_supports_dry_run_and_wet_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            sample = root / "sample.txt"
            sample.write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
            tool = FileTool(AgentConfig(workspace_root=root))

            preview = tool.search_replace("sample.txt", "two", "TWO", dry_run=True)
            self.assertTrue(preview.ok, preview.error)
            self.assertTrue(preview.report["dry_run"])
            self.assertTrue(preview.report["changed"])
            self.assertIn("-two", preview.report["preview"])
            self.assertEqual(sample.read_text(encoding="utf-8"), "one\ntwo\nthree\nfour\n")

            inserted = tool.insert_text("sample.txt", "one-point-five", line_number=1, position="after")
            self.assertTrue(inserted.ok, inserted.error)
            self.assertIn("one-point-five\n", sample.read_text(encoding="utf-8"))

            deleted = tool.delete_backward("sample.txt", 1, pattern="three", dry_run=False)
            self.assertTrue(deleted.ok, deleted.error)
            self.assertNotIn("TWO", sample.read_text(encoding="utf-8"))

            replaced = tool.replace_range("sample.txt", 2, 3, "middle-a\nmiddle-b", dry_run=False)
            self.assertTrue(replaced.ok, replaced.error)
            final_text = sample.read_text(encoding="utf-8")
            self.assertIn("middle-a\n", final_text)
            self.assertIn("middle-b\n", final_text)

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

    def test_shell_compat_formats_env_quote_and_paths(self) -> None:
        self.assertEqual(shell_env_reference("HOME", "powershell"), "$env:HOME")
        self.assertEqual(shell_env_reference("HOME", "cmd"), "%HOME%")
        self.assertEqual(shell_env_reference("HOME", "bash"), "$HOME")
        self.assertEqual(shell_quote("a'b", "powershell"), "'a''b'")
        self.assertEqual(shell_path_literal("src/main.py", "powershell", os_family="windows"), "'src\\main.py'")

    def test_shell_compat_translates_simple_windows_commands(self) -> None:
        translated, error = prepare_command_for_shell("pwd", "powershell")
        self.assertIsNone(error)
        self.assertEqual(translated, "Get-Location")

        translated, error = prepare_command_for_shell("cat README.md", "cmd")
        self.assertIsNone(error)
        self.assertEqual(translated, 'type "README.md"')

    def test_shell_compat_rejects_posix_only_windows_commands(self) -> None:
        translated, error = prepare_command_for_shell("sed -n 1p README.md", "powershell")
        self.assertIsNone(translated)
        self.assertIn("POSIX-only", error or "")

    def test_shell_compat_flags_bash_required_patterns_on_windows(self) -> None:
        self.assertTrue(command_requires_posix_shell("grep foo README.md", "powershell"))
        self.assertTrue(command_requires_posix_shell("python3 -c \"print(1)\" && pwd", "cmd"))
        self.assertFalse(command_requires_posix_shell("pwd", "powershell"))

    def test_shell_tool_auto_backend_uses_detected_posix_shell(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir), shell_backend="auto"))
            tool.is_windows = False
            tool.runtime_capabilities = {
                "os_family": "macos",
                "default_shell": "/bin/zsh",
                "recommended_shell": "zsh",
                "shells": {
                    "zsh": {"available": True, "path": "/bin/zsh", "version": "zsh 5.9"},
                    "bash": {"available": True, "path": "/bin/bash", "version": "bash 3.2"},
                },
            }

            self.assertEqual(tool._command_args("pwd"), ["/bin/zsh", "-lc", "pwd"])

    def test_shell_tool_rejects_missing_explicit_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir), shell_backend="bash"))
            tool.runtime_capabilities = {
                "os_family": "windows",
                "default_shell": "",
                "recommended_shell": "cmd",
                "shells": {
                    "bash": {"available": False, "path": None, "version": ""},
                    "zsh": {"available": False, "path": None, "version": ""},
                    "powershell": {"available": False, "path": None, "version": ""},
                    "cmd": {"available": True, "path": "cmd", "version": ""},
                },
            }

            result = tool.run("pwd")

            self.assertFalse(result.ok)
            self.assertIn("not available", result.error)

    def test_shell_tool_translates_windows_powershell_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir), shell_backend="powershell"))
            tool.is_windows = True
            tool.runtime_capabilities = {
                "os_family": "windows",
                "default_shell": "",
                "recommended_shell": "powershell",
                "shells": {
                    "powershell": {"available": True, "path": "powershell", "version": "5.1"},
                    "cmd": {"available": True, "path": "cmd", "version": ""},
                },
            }
            tool._windows_shell = lambda: "powershell"  # type: ignore[method-assign]

            args = tool._command_args("pwd")

            self.assertEqual(args[-1], "Get-Location")

    def test_shell_tool_rejects_posix_only_command_on_windows_backend(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir), shell_backend="powershell"))
            tool.is_windows = True
            tool.runtime_capabilities = {
                "os_family": "windows",
                "default_shell": "",
                "recommended_shell": "powershell",
                "shells": {
                    "powershell": {"available": True, "path": "powershell", "version": "5.1"},
                    "cmd": {"available": True, "path": "cmd", "version": ""},
                },
            }

            result = tool.run("sed -n 1p README.md")

            self.assertFalse(result.ok)
            self.assertIn("POSIX shell or bash-compatible backend", result.error)

    def test_runtime_selects_windows_powershell_by_default(self) -> None:
        capabilities = {
            "os_family": "windows",
            "default_shell": "",
            "recommended_shell": "powershell",
            "shells": {
                "powershell": {"available": True, "path": "pwsh", "version": "7.4.0"},
                "cmd": {"available": True, "path": "cmd", "version": ""},
                "bash": {"available": False, "path": None, "version": ""},
                "zsh": {"available": False, "path": None, "version": ""},
            },
        }

        selected = select_shell_backend("auto", capabilities)

        self.assertTrue(selected["available"])
        self.assertEqual(selected["selected"], "powershell")
        self.assertEqual(selected["executable"], "pwsh")

    def test_runtime_reports_missing_explicit_shell(self) -> None:
        capabilities = {
            "os_family": "windows",
            "default_shell": "",
            "recommended_shell": "cmd",
            "shells": {
                "powershell": {"available": False, "path": None, "version": ""},
                "cmd": {"available": True, "path": "cmd", "version": ""},
                "bash": {"available": False, "path": None, "version": ""},
                "zsh": {"available": False, "path": None, "version": ""},
            },
        }

        selected = select_shell_backend("bash", capabilities)

        self.assertFalse(selected["available"])
        self.assertEqual(selected["selected"], "bash")
        self.assertIn("not available", selected["reason"])

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

    def test_shell_tool_lists_persistent_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tool = ShellTool(AgentConfig(workspace_root=Path(tmp_dir)))
            empty = tool.list_sessions()
            self.assertTrue(empty.ok)
            self.assertIn("No active shell sessions", empty.output_preview)

            created = tool.create_session()
            self.assertTrue(created.ok)
            listed = tool.list_sessions()
            self.assertTrue(listed.ok)
            self.assertIn(created.session_id, listed.output_preview)
            self.assertIn("state=running", listed.output_preview)
            self.assertTrue(tool.close_session(created.session_id).ok)

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
            self.assertEqual(result.matches, ["update keep.txt", "add new.txt", "delete delete.txt"])
            self.assertIn("update keep.txt", result.content)
            self.assertIn("add new.txt", result.content)
            self.assertIn("delete delete.txt", result.content)
            self.assertEqual((root / "keep.txt").read_text(), "after\n")
            self.assertEqual((root / "new.txt").read_text(), "created\n")
            self.assertFalse((root / "delete.txt").exists())

    def test_file_tool_preview_patch_files_does_not_write_in_plan_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            PermissionSettings(default_mode="plan").save(root / ".stagewarden_settings.json")
            (root / "keep.txt").write_text("before\n")
            tool = FileTool(AgentConfig(workspace_root=root))
            diff = "\n".join(
                [
                    "--- a/keep.txt",
                    "+++ b/keep.txt",
                    "@@ -1,1 +1,1 @@",
                    "-before",
                    "+after",
                ]
            )

            preview = tool.preview_patch_files(diff)
            applied = tool.patch_files(diff)

            self.assertTrue(preview.ok, preview.error)
            self.assertEqual(preview.matches, ["update keep.txt"])
            self.assertEqual((root / "keep.txt").read_text(), "before\n")
            self.assertFalse(applied.ok)
            self.assertIn("Plan mode", applied.error)

    def test_file_tool_rejects_ambiguous_duplicate_patch_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "same.txt").write_text("one\n")
            tool = FileTool(AgentConfig(workspace_root=root))
            diff = "\n".join(
                [
                    "--- a/same.txt",
                    "+++ b/same.txt",
                    "@@ -1,1 +1,1 @@",
                    "-one",
                    "+two",
                    "--- a/same.txt",
                    "+++ b/same.txt",
                    "@@ -1,1 +1,1 @@",
                    "-one",
                    "+three",
                ]
            )

            result = tool.preview_patch_files(diff)

            self.assertFalse(result.ok)
            self.assertIn("Ambiguous patch target", result.error)

    def test_file_tool_preview_patch_files_rejects_failed_hunk(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "keep.txt").write_text("before\n")
            tool = FileTool(AgentConfig(workspace_root=root))
            diff = "\n".join(
                [
                    "--- a/keep.txt",
                    "+++ b/keep.txt",
                    "@@ -1,1 +1,1 @@",
                    "-missing",
                    "+after",
                ]
            )

            result = tool.preview_patch_files(diff)

            self.assertFalse(result.ok)
            self.assertIn("Unable to apply patch", result.error)

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
