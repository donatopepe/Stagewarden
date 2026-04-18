from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .config import AgentConfig
from .handoff import HandoffManager, format_run_model
from .memory import MemoryStore
from .modelprefs import ModelPreferences, extract_blocked_until
from .planner import PlanStep
from .prince2 import Prince2Assessment, Prince2Checklist, Prince2AgentPolicy
from .router import ModelRouter
from .textcodec import dumps_ascii, loads_text
from .tools.files import FileTool
from .tools.git import GitTool
from .tools.shell import ShellTool


@dataclass(slots=True)
class StepOutcome:
    ok: bool
    step_completed: bool
    model: str
    action_type: str
    observation: str
    error_type: str | None = None
    prince2_assessment: dict[str, Any] | None = None


class Executor:
    def __init__(
        self,
        *,
        config: AgentConfig,
        router: ModelRouter,
        handoff: HandoffManager,
        memory: MemoryStore,
    ) -> None:
        self.config = config
        self.router = router
        self.handoff = handoff
        self.memory = memory
        self.shell = ShellTool(config)
        self.files = FileTool(config)
        self.git = GitTool(config)
        self.prince2 = Prince2AgentPolicy()

    def execute_step(
        self,
        *,
        task: str,
        step: PlanStep,
        plan: list[PlanStep],
        iteration: int,
        last_observation: str,
        prince2_checklist: Prince2Checklist | None = None,
    ) -> StepOutcome:
        failure_count = self.memory.failure_count(step.id)
        model = self.router.choose_model(task, step.instruction, failure_count)
        prompt = self._build_prompt(task=task, step=step, plan=plan, last_observation=last_observation)

        result = self.handoff.execute(format_run_model(model, prompt))
        if not result.ok:
            self._record_model_block_if_present(model, result.error or result.output)
            fallback_model = self.router.fallback_for_api_failure(model)
            fallback = self.handoff.execute(format_run_model(fallback_model, prompt))
            if not fallback.ok:
                self._record_model_block_if_present(fallback_model, fallback.error or fallback.output)
                self.memory.record_attempt(
                    iteration=iteration,
                    step_id=step.id,
                    model=fallback_model,
                    action_type="model_error",
                    action_signature=f"handoff:{model}->{fallback_model}",
                    success=False,
                    observation=f"Primary model error: {result.error}\nFallback model error: {fallback.error}",
                    error_type="api_failure",
                )
                return StepOutcome(
                    ok=False,
                    step_completed=False,
                    model=fallback_model,
                    action_type="model_error",
                    observation=f"Primary model error: {result.error}\nFallback model error: {fallback.error}",
                    error_type="api_failure",
                    prince2_assessment=None,
                )
            result = fallback
            model = fallback_model

        parsed = self._parse_model_json(result.output)
        if not parsed["ok"]:
            self.memory.record_attempt(
                iteration=iteration,
                step_id=step.id,
                model=model,
                action_type="invalid_output",
                action_signature="invalid_json",
                success=False,
                observation=parsed["error"],
                error_type="invalid_output",
            )
            return StepOutcome(
                ok=False,
                step_completed=False,
                model=model,
                action_type="invalid_output",
                observation=parsed["error"],
                error_type="invalid_output",
                prince2_assessment=None,
            )

        action = parsed["action"]
        action_type = action.get("type", "").strip()
        observation = self._run_action(action)
        ok = observation["ok"]
        step_completed = bool(action_type == "complete" and ok)
        error_type = None if ok else observation.get("error_type", "execution_error")

        self.memory.record_attempt(
            iteration=iteration,
            step_id=step.id,
            model=model,
            action_type=action_type or "unknown",
            action_signature=dumps_ascii(action, sort_keys=True),
            success=ok,
            observation=observation["message"],
            error_type=error_type,
        )

        if ok and not step_completed:
            validator = self._check_validation(step, observation["message"], action_type=action_type)
            if validator:
                step_completed = True

        if ok and step_completed and not self._has_wet_run_evidence(action_type, observation["message"]):
            ok = False
            step_completed = False
            error_type = "wet_run_required"
            observation["message"] = (
                f"{observation['message']}\nWet-run gate failed: dry-run or narrative completion is not valid evidence."
            )

        prince2_assessment = None
        if ok and step_completed and prince2_checklist is not None:
            assessment = self.prince2.assess_completion(observation["message"], prince2_checklist)
            prince2_assessment = assessment.as_dict()
            if not assessment.allowed:
                ok = False
                step_completed = False
                error_type = "prince2_closure_failure"
                observation["message"] = (
                    f"{observation['message']}\nPRINCE2 closure gate failed: {'; '.join(assessment.reasons)}"
                )

        if not ok and self.memory.failure_count(step.id) >= self.config.max_retries_per_step:
            escalated_model = self.router.escalate(model)
            return StepOutcome(
                ok=False,
                step_completed=False,
                model=escalated_model,
                action_type=action_type,
                observation=observation["message"],
                error_type=error_type,
                prince2_assessment=prince2_assessment,
            )

        return StepOutcome(
            ok=ok,
            step_completed=step_completed,
            model=model,
            action_type=action_type,
            observation=observation["message"],
            error_type=error_type,
            prince2_assessment=prince2_assessment,
        )

    def _record_model_block_if_present(self, model: str, message: str) -> None:
        until = extract_blocked_until(message)
        if not until:
            return
        try:
            prefs = ModelPreferences.load(self.config.model_prefs_path)
            prefs.blocked_until_by_model = dict(prefs.blocked_until_by_model or {})
            prefs.blocked_until_by_model[model] = until
            if prefs.preferred_model == model:
                prefs.preferred_model = None
            prefs.save(self.config.model_prefs_path)
            self.router.configure(
                enabled_models=prefs.enabled_models,
                preferred_model=prefs.preferred_model,
                blocked_until_by_model=prefs.blocked_until_by_model,
            )
        except OSError:
            return

    def _build_prompt(
        self,
        *,
        task: str,
        step: PlanStep,
        plan: list[PlanStep],
        last_observation: str,
    ) -> str:
        plan_lines = "\n".join(
            f"- {item.id}: {item.title} [{item.status}] validation={item.validation} wet_run_required={item.wet_run_required}"
            for item in plan
        )
        memory_summary = self.memory.summarize()
        return f"""{self.config.system_prompt}

Task:
{task}

Current step:
id={step.id}
title={step.title}
instruction={step.instruction}
validation={step.validation}
wet_run_required={step.wet_run_required}

Plan:
{plan_lines}

Previous observation:
{last_observation or "None"}

Recent memory:
{memory_summary}

Validation policy:
- Always create or update relevant verification tests/checks for code or behavior changes.
- A dry-run is not a valid checkpoint by itself.
- A step may complete only after real wet-run evidence: executed tests, executed commands, observed files, or real tool output.
- If a wet-run is blocked, find a feasible alternative wet-run instead of accepting dry-run completion.
- Use complete only after the current step has real validation evidence.

Available actions and required fields:
1. shell -> {{"type":"shell","command":"...","cwd":"optional-relative-path"}}
2. shell_session_create -> {{"type":"shell_session_create","cwd":"optional-relative-path"}}
3. shell_session_send -> {{"type":"shell_session_send","session_id":"session id","command":"..."}}
4. shell_session_close -> {{"type":"shell_session_close","session_id":"session id"}}
5. read_file -> {{"type":"read_file","path":"relative/path"}}
6. write_file -> {{"type":"write_file","path":"relative/path","content":"full file contents"}}
7. apply_patch -> {{"type":"apply_patch","path":"relative/path","search":"old text","replace":"new text"}}
8. patch_file -> {{"type":"patch_file","path":"relative/path","diff":"unified diff for one file"}}
9. patch_files -> {{"type":"patch_files","diff":"unified diff with one or more files"}}
10. list_files -> {{"type":"list_files","base_path":"optional-relative-path","pattern":"glob pattern","limit":100}}
11. search_files -> {{"type":"search_files","pattern":"regex","base_path":"optional-relative-path","glob":"glob pattern","limit":50}}
12. git_status -> {{"type":"git_status"}}
13. git_diff -> {{"type":"git_diff"}}
14. git_log -> {{"type":"git_log","limit":20,"path":"optional-relative-path"}}
15. git_show -> {{"type":"git_show","revision":"HEAD","stat":true}}
16. git_file_history -> {{"type":"git_file_history","path":"relative/path","limit":20}}
17. git_commit -> {{"type":"git_commit","message":"commit message"}}
18. complete -> {{"type":"complete","message":"why the current step is done"}}

Respond with strict JSON:
{{
  "summary": "brief reasoning",
  "action": {{
    "type": "one action"
  }}
}}
"""

    def _parse_model_json(self, raw: str) -> dict[str, Any]:
        text = raw.strip()
        candidates = self._json_candidates(text)
        payload = None
        last_error: Exception | None = None
        for candidate in candidates:
            try:
                payload = loads_text(candidate)
                break
            except ValueError as exc:
                last_error = exc

        if payload is None:
            error = f"Model did not return valid JSON: {last_error}" if last_error else "No JSON object found."
            return {"ok": False, "error": error}

        action = payload.get("action")
        if not isinstance(action, dict) or "type" not in action:
            return {"ok": False, "error": "Model JSON is missing action.type."}
        return {"ok": True, "action": action, "payload": payload}

    def _json_candidates(self, text: str) -> list[str]:
        candidates: list[str] = []
        stripped = text.strip()
        if stripped:
            candidates.append(stripped)

        fenced = re.findall(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
        for block in fenced:
            block = block.strip()
            if block:
                candidates.append(block)

        extracted = self._extract_first_json_object(text)
        if extracted:
            candidates.append(extracted)

        unique: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        return unique

    def _extract_first_json_object(self, text: str) -> str | None:
        start = text.find("{")
        while start != -1:
            depth = 0
            in_string = False
            escape = False
            for index in range(start, len(text)):
                char = text[index]
                if in_string:
                    if escape:
                        escape = False
                    elif char == "\\":
                        escape = True
                    elif char == '"':
                        in_string = False
                    continue

                if char == '"':
                    in_string = True
                elif char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start : index + 1]
            start = text.find("{", start + 1)
        return None

    def _run_action(self, action: dict[str, Any]) -> dict[str, Any]:
        action_type = action.get("type")
        if action_type == "shell":
            result = self.shell.run(action.get("command", ""), cwd=action.get("cwd"))
            return {
                "ok": result.ok,
                "message": result.output_preview or result.error or "Shell command executed.",
                "error_type": "runtime_error",
            }

        if action_type == "shell_session_create":
            result = self.shell.create_session(cwd=action.get("cwd"))
            return {"ok": result.ok, "message": result.output_preview or result.error, "error_type": "runtime_error"}

        if action_type == "shell_session_send":
            result = self.shell.send_session(action.get("session_id", ""), action.get("command", ""))
            return {"ok": result.ok, "message": result.output_preview or result.error, "error_type": "runtime_error"}

        if action_type == "shell_session_close":
            result = self.shell.close_session(action.get("session_id", ""))
            return {"ok": result.ok, "message": result.output_preview or result.error, "error_type": "runtime_error"}

        if action_type == "read_file":
            result = self.files.read(action.get("path", ""))
            return {"ok": result.ok, "message": result.content or result.error or "File read.", "error_type": "file_error"}

        if action_type == "write_file":
            result = self.files.write(action.get("path", ""), action.get("content", ""))
            message = f"Wrote file {result.path}" if result.ok else result.error
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "apply_patch":
            result = self.files.apply_patch(
                action.get("path", ""),
                action.get("search", ""),
                action.get("replace", ""),
            )
            message = f"Patched file {result.path}" if result.ok else result.error
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "patch_file":
            result = self.files.patch(action.get("path", ""), action.get("diff", ""))
            message = f"Patched file {result.path}" if result.ok else result.error
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "patch_files":
            result = self.files.patch_files(action.get("diff", ""))
            message = f"Patched files:\n{result.content}" if result.ok else result.error
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "list_files":
            result = self.files.list_files(
                base_path=action.get("base_path", "."),
                pattern=action.get("pattern", "*"),
                limit=int(action.get("limit", 200)),
            )
            return {"ok": result.ok, "message": result.content or result.error or "No files found.", "error_type": "file_error"}

        if action_type == "search_files":
            result = self.files.search(
                pattern=action.get("pattern", ""),
                base_path=action.get("base_path", "."),
                glob=action.get("glob", "*"),
                limit=int(action.get("limit", 100)),
            )
            return {"ok": result.ok, "message": result.content or result.error or "No matches found.", "error_type": "file_error"}

        if action_type == "git_diff":
            result = self.git.diff()
            return {"ok": result.ok, "message": result.stdout or result.error or "No diff.", "error_type": "git_error"}

        if action_type == "git_status":
            result = self.git.status()
            return {"ok": result.ok, "message": result.stdout or result.error or "Clean working tree.", "error_type": "git_error"}

        if action_type == "git_log":
            result = self.git.log(limit=int(action.get("limit", 20)), path=action.get("path") or None)
            return {"ok": result.ok, "message": result.stdout or result.error or "No git history.", "error_type": "git_error"}

        if action_type == "git_show":
            result = self.git.show(revision=action.get("revision", "HEAD"), stat=bool(action.get("stat", False)))
            return {"ok": result.ok, "message": result.stdout or result.error or "No revision details.", "error_type": "git_error"}

        if action_type == "git_file_history":
            result = self.git.file_history(action.get("path", ""), limit=int(action.get("limit", 20)))
            return {"ok": result.ok, "message": result.stdout or result.error or "No file history.", "error_type": "git_error"}

        if action_type == "git_commit":
            result = self.git.commit(action.get("message", "Agent commit"))
            return {"ok": result.ok, "message": result.stdout or result.error or "Committed.", "error_type": "git_error"}

        if action_type == "complete":
            return {"ok": True, "message": action.get("message", "Step completed.")}

        return {"ok": False, "message": f"Unsupported action type: {action_type}", "error_type": "invalid_output"}

    def _check_validation(self, step: PlanStep, observation: str, *, action_type: str = "") -> bool:
        if not self._has_wet_run_evidence(action_type, observation):
            return False
        lower = observation.lower()
        if any(token in lower for token in ("error", "failed", "traceback", "not found", "denied")):
            return False
        if "exit_code=0" in lower:
            return True
        if step.validation.lower().startswith("a command") and observation:
            return True
        if "wrote file" in lower or "patched file" in lower:
            return True
        return False

    def _has_wet_run_evidence(self, action_type: str, observation: str) -> bool:
        lowered = observation.lower()
        if "dry-run" in lowered or "dry run" in lowered or "--dry-run" in lowered:
            return False
        if action_type in {
            "shell",
            "shell_session_send",
            "read_file",
            "write_file",
            "apply_patch",
            "patch_file",
            "patch_files",
            "list_files",
            "search_files",
            "git_status",
            "git_diff",
            "git_log",
            "git_show",
            "git_file_history",
            "git_commit",
        }:
            return True
        wet_markers = (
            "exit_code=0",
            "passed",
            "tests passed",
            "ran ",
            "wrote file",
            "patched file",
            "patched files",
            "found",
            "exists",
            "validated",
            "validazione completata",
            "validation completed",
        )
        return any(marker in lowered for marker in wet_markers)

    def simulation_snapshot(self) -> dict[str, Any]:
        return {
            "attempts_ljson": self.memory.attempts_as_ljson(),
            "failures_by_step": dict(self.memory.failures_by_step),
            "models_by_step": dict(self.memory.models_by_step),
        }
