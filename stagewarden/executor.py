from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .config import AgentConfig
from .handoff import HandoffManager, format_run_model
from .memory import MemoryStore
from .modelprefs import ModelPreferences, classify_limit_reason, extract_blocked_until, limit_snapshot_from_message
from .planner import PlanStep
from .prince2 import Prince2Assessment, Prince2Checklist, Prince2AgentPolicy
from .project_handoff import ProjectHandoff
from .router import ModelRouter
from .role_tree import build_prince2_role_flow
from .roles import PRINCE2_ROLE_AUTOMATION_RULES, PRINCE2_ROLE_SCOPE_DESCRIPTIONS
from .runtime_env import detect_runtime_capabilities
from .textcodec import dumps_ascii, loads_text
from .tools.files import FileTool
from .tools.git import GitTool
from .tools.shell import ShellTool
from .executor_quality import ResponseQualityAssessment, assess_response_quality
from . import executor_prompting as _executor_prompting


@dataclass(slots=True)
class StepOutcome:
    ok: bool
    step_completed: bool
    model: str
    action_type: str
    observation: str
    account: str | None = None
    variant: str | None = None
    git_head_before: str | None = None
    git_head_after: str | None = None
    error_type: str | None = None
    prince2_assessment: dict[str, Any] | None = None
    prince2_role: str | None = None
    response_quality: dict[str, Any] | None = None


@dataclass(slots=True)
class PromptSection:
    title: str
    body: str

    def as_dict(self) -> dict[str, str]:
        return {"title": self.title, "body": self.body}


@dataclass(slots=True)
class PromptTranscriptItem:
    item_type: str
    body: str

    def as_dict(self) -> dict[str, str]:
        return {"item_type": self.item_type, "body": self.body}


@dataclass(slots=True)
class ModelCommunicationPacket:
    system_prompt: str
    sections: list[PromptSection]
    transcript_items: list[PromptTranscriptItem]
    contract_sections: list[PromptSection]
    telemetry: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "sections": [section.as_dict() for section in self.sections],
            "transcript_items": [item.as_dict() for item in self.transcript_items],
            "contract_sections": [section.as_dict() for section in self.contract_sections],
            "telemetry": self.telemetry,
        }


ALLOWED_MODEL_ACTIONS = {
    "shell",
    "shell_session_create",
    "shell_session_send",
    "shell_session_close",
    "read_file",
    "inspect_file",
    "inspect_metadata_file",
    "write_file",
    "apply_patch",
    "search_replace_file",
    "insert_text_file",
    "delete_range_file",
    "delete_backward_file",
    "replace_range_file",
    "convert_encoding_file",
    "normalize_line_endings_file",
    "copy_path_file",
    "move_path_file",
    "delete_path_file",
    "chmod_path_file",
    "chown_path_file",
    "patch_file",
    "patch_files",
    "preview_patch_files",
    "list_files",
    "search_files",
    "git_status",
    "git_diff",
    "git_log",
    "git_show",
    "git_file_history",
    "git_commit",
    "complete",
}

MODEL_ACTION_SCHEMAS: dict[str, dict[str, Any]] = {
    "shell": {"tool": "shell", "required": ["command"], "optional": ["cwd"], "mutates": "depends_on_command"},
    "shell_session_create": {"tool": "shell", "required": [], "optional": ["cwd"], "mutates": False},
    "shell_session_send": {"tool": "shell", "required": ["session_id", "command"], "optional": [], "mutates": "depends_on_command"},
    "shell_session_close": {"tool": "shell", "required": ["session_id"], "optional": [], "mutates": False},
    "read_file": {"tool": "files", "required": ["path"], "optional": [], "mutates": False},
    "inspect_file": {"tool": "files", "required": ["path"], "optional": [], "mutates": False},
    "inspect_metadata_file": {"tool": "files", "required": ["path"], "optional": [], "mutates": False},
    "write_file": {"tool": "files", "required": ["path", "content"], "optional": [], "mutates": True},
    "apply_patch": {"tool": "files", "required": ["path", "search", "replace"], "optional": [], "mutates": True},
    "search_replace_file": {"tool": "files", "required": ["path", "search", "replace"], "optional": ["count", "dry_run"], "mutates": "unless_dry_run"},
    "insert_text_file": {"tool": "files", "required": ["path", "content"], "optional": ["line_number", "pattern", "position", "occurrence", "dry_run"], "mutates": "unless_dry_run"},
    "delete_range_file": {"tool": "files", "required": ["path", "start_line", "end_line"], "optional": ["dry_run"], "mutates": "unless_dry_run"},
    "delete_backward_file": {"tool": "files", "required": ["path", "count"], "optional": ["line_number", "pattern", "occurrence", "dry_run"], "mutates": "unless_dry_run"},
    "replace_range_file": {"tool": "files", "required": ["path", "start_line", "end_line", "content"], "optional": ["dry_run"], "mutates": "unless_dry_run"},
    "convert_encoding_file": {"tool": "files", "required": ["path", "target_encoding"], "optional": ["source_encoding", "dry_run"], "mutates": "unless_dry_run"},
    "normalize_line_endings_file": {"tool": "files", "required": ["path", "newline"], "optional": ["dry_run"], "mutates": "unless_dry_run"},
    "copy_path_file": {"tool": "files", "required": ["source", "destination"], "optional": ["overwrite", "dry_run"], "mutates": "unless_dry_run"},
    "move_path_file": {"tool": "files", "required": ["source", "destination"], "optional": ["overwrite", "dry_run"], "mutates": "unless_dry_run"},
    "delete_path_file": {"tool": "files", "required": ["path"], "optional": ["recursive", "dry_run"], "mutates": "unless_dry_run"},
    "chmod_path_file": {"tool": "files", "required": ["path", "mode"], "optional": ["recursive", "dry_run"], "mutates": "unless_dry_run"},
    "chown_path_file": {"tool": "files", "required": ["path"], "optional": ["user", "group", "recursive", "dry_run"], "mutates": "unless_dry_run"},
    "patch_file": {"tool": "files", "required": ["path", "diff"], "optional": [], "mutates": True},
    "patch_files": {"tool": "files", "required": ["diff"], "optional": [], "mutates": True},
    "preview_patch_files": {"tool": "files", "required": ["diff"], "optional": [], "mutates": False},
    "list_files": {"tool": "files", "required": [], "optional": ["base_path", "pattern", "limit"], "mutates": False},
    "search_files": {"tool": "files", "required": ["pattern"], "optional": ["base_path", "glob", "limit"], "mutates": False},
    "git_status": {"tool": "git", "required": [], "optional": [], "mutates": False},
    "git_diff": {"tool": "git", "required": [], "optional": [], "mutates": False},
    "git_log": {"tool": "git", "required": [], "optional": ["limit", "path"], "mutates": False},
    "git_show": {"tool": "git", "required": [], "optional": ["revision", "stat"], "mutates": False},
    "git_file_history": {"tool": "git", "required": ["path"], "optional": ["limit"], "mutates": False},
    "git_commit": {"tool": "git", "required": ["message"], "optional": [], "mutates": True},
    "complete": {"tool": "agent", "required": ["message"], "optional": [], "mutates": False},
}

DESTRUCTIVE_ACTION_TOKENS = ("delete", "remove", "destroy", "wipe", "reset", "drop", "format", "purge")


class Executor:
    def __init__(
        self,
        *,
        config: AgentConfig,
        router: ModelRouter,
        handoff: HandoffManager,
        memory: MemoryStore,
        project_handoff: ProjectHandoff | None = None,
    ) -> None:
        self.config = config
        self.router = router
        self.handoff = handoff
        self.memory = memory
        self.project_handoff = project_handoff or ProjectHandoff()
        self.shell = ShellTool(config)
        self.files = FileTool(config)
        self.git = GitTool(config)
        self.prince2 = Prince2AgentPolicy()

    def refresh_permissions(self) -> None:
        self.shell.refresh_permissions()
        self.files.refresh_permissions()

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
        git_head_before = self._git_head()
        prefs = self._configure_handoff_accounts()
        prince2_role = self._role_for_step(task=task, step=step)
        role_assignment = self._role_assignment_for_step(
            prefs,
            prince2_role,
            task=task,
            step=step,
            failure_count=failure_count,
        )
        if role_assignment:
            model = str(role_assignment["provider"])
            self._configure_handoff_role_route(role_assignment)
        prompt = self._build_prompt(task=task, step=step, plan=plan, last_observation=last_observation)

        self._configure_handoff_variant(
            prefs=prefs,
            model=model,
            task=task,
            step_text=step.instruction,
            failure_count=failure_count,
            role_assignment=role_assignment,
        )
        account = str(role_assignment["account"]) if role_assignment and role_assignment.get("account") else self._select_account(model)
        if self._accounts_configured(model) and account is None:
            model = self.router.fallback_for_api_failure(model)
            role_assignment = None
            self._configure_handoff_variant(
                prefs=prefs,
                model=model,
                task=task,
                step_text=step.instruction,
                failure_count=failure_count,
            )
            account = self._select_account(model)
        result, account = self._execute_with_account_failover(model=model, prompt=prompt, account=account)
        if not result.ok:
            response_text = result.error or result.output
            network_issue = self._is_transient_network_failure(response_text)
            rate_limit_until = extract_blocked_until(response_text)
            limit_reason = classify_limit_reason(response_text)
            fallback_model = self._fallback_model_after_failure(model)
            if rate_limit_until or limit_reason in {"usage_limit", "credits_exhausted"}:
                alternatives = self._available_alternative_models(model)
                if alternatives:
                    fallback_model = alternatives[0]
                else:
                    decision = self._rate_limit_decision(model, rate_limit_until, alternatives)
                    self.memory.record_attempt(
                        iteration=iteration,
                        step_id=step.id,
                        model=model,
                        account=account,
                        variant=self.handoff.model_variant_by_model.get(model),
                        action_type="model_rate_limit",
                        action_signature=f"rate-limit:{model}",
                        success=False,
                        observation=(
                            f"Provider {model} is rate-limited"
                            + (f" until {rate_limit_until}" if rate_limit_until else "")
                            + ". "
                            f"User decision: {decision or 'stop'}."
                        ),
                        error_type="rate_limit",
                    )
                    return StepOutcome(
                        ok=False,
                        step_completed=False,
                        model=model,
                        action_type="model_rate_limit",
                        observation=(
                            f"Provider {model} is rate-limited"
                            + (f" until {rate_limit_until}" if rate_limit_until else "")
                            + ". "
                            "No alternative provider is currently available."
                        ),
                        account=account,
                        variant=self.handoff.model_variant_by_model.get(model),
                        git_head_before=git_head_before,
                    git_head_after=self._git_head(),
                    error_type="rate_limit_wait" if decision == "wait" else "rate_limit",
                    prince2_assessment=None,
                    prince2_role=prince2_role,
                )
            self._configure_handoff_variant(
                prefs=prefs,
                model=fallback_model,
                task=task,
                step_text=step.instruction,
                failure_count=failure_count + 1,
            )
            fallback_account = self._select_account(fallback_model)
            fallback, fallback_account = self._execute_with_account_failover(
                model=fallback_model,
                prompt=prompt,
                account=fallback_account,
            )
            fallback_response_text = fallback.error or fallback.output
            fallback_network_issue = self._is_transient_network_failure(fallback_response_text)
            fallback_limit_reason = classify_limit_reason(fallback_response_text)
            if not fallback.ok:
                if network_issue or fallback_network_issue:
                    observation = (
                        "Network unavailable while contacting model providers.\n"
                        f"Primary error: {result.error or result.output or 'unknown'}\n"
                        f"Fallback error: {fallback.error or fallback.output or 'unknown'}\n"
                        "The run is safe to resume once connectivity returns."
                    )
                    self.memory.record_attempt(
                        iteration=iteration,
                        step_id=step.id,
                        model=fallback_model,
                        account=fallback_account,
                        variant=self.handoff.model_variant_by_model.get(fallback_model),
                        action_type="model_network_unavailable",
                        action_signature=f"network-unavailable:{model}->{fallback_model}",
                        success=False,
                        observation=observation,
                        error_type="network_wait",
                    )
                    return StepOutcome(
                        ok=False,
                        step_completed=False,
                        model=fallback_model,
                        action_type="model_network_unavailable",
                        observation=observation,
                        account=fallback_account,
                        variant=self.handoff.model_variant_by_model.get(fallback_model),
                        git_head_before=git_head_before,
                        git_head_after=self._git_head(),
                        error_type="network_wait",
                        prince2_assessment=None,
                        prince2_role=prince2_role,
                    )
                if limit_reason in {"usage_limit", "credits_exhausted"} or fallback_limit_reason in {"usage_limit", "credits_exhausted"}:
                    observation = (
                        f"Provider {model} reached a usage limit"
                        + (f" until {rate_limit_until}" if rate_limit_until else "")
                        + ". "
                        f"Fallback provider {fallback_model} also reported a usage limit. "
                        "The run is safe to resume once limits reset."
                    )
                    self.memory.record_attempt(
                        iteration=iteration,
                        step_id=step.id,
                        model=fallback_model,
                        account=fallback_account,
                        variant=self.handoff.model_variant_by_model.get(fallback_model),
                        action_type="model_rate_limit",
                        action_signature=f"rate-limit:{model}->{fallback_model}",
                        success=False,
                        observation=observation,
                        error_type="rate_limit_wait",
                    )
                    return StepOutcome(
                        ok=False,
                        step_completed=False,
                        model=fallback_model,
                        action_type="model_rate_limit",
                        observation=observation,
                        account=fallback_account,
                        variant=self.handoff.model_variant_by_model.get(fallback_model),
                        git_head_before=git_head_before,
                        git_head_after=self._git_head(),
                        error_type="rate_limit_wait",
                        prince2_assessment=None,
                        prince2_role=prince2_role,
                    )
                self.memory.record_attempt(
                    iteration=iteration,
                    step_id=step.id,
                    model=fallback_model,
                    account=fallback_account,
                    variant=self.handoff.model_variant_by_model.get(fallback_model),
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
                    account=fallback_account,
                    variant=self.handoff.model_variant_by_model.get(fallback_model),
                    git_head_before=git_head_before,
                    git_head_after=self._git_head(),
                    error_type="api_failure",
                    prince2_assessment=None,
                    prince2_role=prince2_role,
                )
            result = fallback
            model = fallback_model
            account = fallback_account

        parsed = self._parse_model_json(result.output)
        if not parsed["ok"]:
            self.memory.record_attempt(
                iteration=iteration,
                step_id=step.id,
                model=model,
                account=account,
                variant=self.handoff.model_variant_by_model.get(model),
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
                account=account,
                variant=self.handoff.model_variant_by_model.get(model),
                git_head_before=git_head_before,
                git_head_after=self._git_head(),
                error_type="invalid_output",
                prince2_assessment=None,
                prince2_role=prince2_role,
            )

        action = parsed["action"]
        devil_advocate = self._run_devil_advocate_review(
            iteration=iteration,
            task=task,
            step=step,
            plan=plan,
            model=model,
            account=account,
            primary_payload=parsed.get("payload", {}) if isinstance(parsed.get("payload", {}), dict) else {},
            primary_action=action,
            primary_output=result.output,
            primary_observation=last_observation,
        )
        review_payload = devil_advocate.get("review", {}) if isinstance(devil_advocate.get("review", {}), dict) else {}
        review_verdict = str(review_payload.get("verdict", "accept")).strip().lower() if review_payload else "accept"
        review_contradictions = [str(item).strip() for item in review_payload.get("contradictions", []) if str(item).strip()] if isinstance(review_payload.get("contradictions", []), list) else []
        review_missing = [str(item).strip() for item in review_payload.get("missing_evidence", []) if str(item).strip()] if isinstance(review_payload.get("missing_evidence", []), list) else []
        review_counter_argument = str(review_payload.get("counter_argument", "")).strip() if review_payload else ""
        review_header = (
            f"Devil advocate verdict={review_verdict}"
            + (f" contradictions={'; '.join(review_contradictions)}" if review_contradictions else "")
            + (f" missing_evidence={'; '.join(review_missing)}" if review_missing else "")
            + (f" counter_argument={review_counter_argument}" if review_counter_argument else "")
        )
        if not devil_advocate.get("ok"):
            self.memory.record_attempt(
                iteration=iteration,
                step_id=step.id,
                model=str(devil_advocate.get("model", model)),
                account=devil_advocate.get("account", account),
                variant=self.handoff.model_variant_by_model.get(str(devil_advocate.get("model", model))),
                action_type="devil_advocate_rejection",
                action_signature=dumps_ascii(review_payload, sort_keys=True),
                success=False,
                observation=str(devil_advocate.get("error", review_header)),
                error_type="critic_invalid_output",
            )
            return StepOutcome(
                ok=False,
                step_completed=False,
                model=str(devil_advocate.get("model", model)),
                action_type="devil_advocate_rejection",
                observation=str(devil_advocate.get("error", review_header)),
                account=devil_advocate.get("account", account),
                variant=self.handoff.model_variant_by_model.get(str(devil_advocate.get("model", model))),
                git_head_before=git_head_before,
                git_head_after=self._git_head(),
                error_type="critic_invalid_output",
                prince2_assessment=None,
                prince2_role=prince2_role,
            )
        if devil_advocate.get("ok") and (review_verdict == "block" or bool(review_payload.get("must_escalate"))):
            self.memory.record_attempt(
                iteration=iteration,
                step_id=step.id,
                model=str(devil_advocate.get("model", model)),
                account=devil_advocate.get("account", account),
                variant=self.handoff.model_variant_by_model.get(str(devil_advocate.get("model", model))),
                action_type="devil_advocate_rejection",
                action_signature=dumps_ascii(review_payload, sort_keys=True),
                success=False,
                observation=review_header,
                error_type="critic_rejection",
            )
            return StepOutcome(
                ok=False,
                step_completed=False,
                model=str(devil_advocate.get("model", model)),
                action_type="devil_advocate_rejection",
                observation=review_header,
                account=devil_advocate.get("account", account),
                variant=self.handoff.model_variant_by_model.get(str(devil_advocate.get("model", model))),
                git_head_before=git_head_before,
                git_head_after=self._git_head(),
                error_type="critic_rejection",
                prince2_assessment=None,
                prince2_role=prince2_role,
            )
        usage_metadata = self._extract_usage_metadata(parsed.get("payload", {}))
        action_type = action.get("type", "").strip()
        observation = self._run_action(action, iteration=iteration, step_id=step.id)
        if devil_advocate.get("ok"):
            observation["message"] = f"{observation['message']}\n{review_header}"
        ok = observation["ok"]
        step_completed = bool(action_type == "complete" and ok)
        error_type = None if ok else observation.get("error_type", "execution_error")

        self.memory.record_attempt(
            iteration=iteration,
            step_id=step.id,
            model=model,
            account=account,
            variant=self.handoff.model_variant_by_model.get(model),
            action_type=action_type or "unknown",
            action_signature=dumps_ascii(action, sort_keys=True),
            success=ok,
            observation=observation["message"],
            error_type=error_type,
            input_tokens=usage_metadata.get("input_tokens"),
            output_tokens=usage_metadata.get("output_tokens"),
            context_window_size=usage_metadata.get("context_window_size"),
            current_usage=usage_metadata.get("current_usage"),
        )
        self._record_goal_usage(model=model, step_id=step.id, usage_metadata=usage_metadata)

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

        response_quality: ResponseQualityAssessment | None = None
        if ok and action_type == "complete":
            response_quality = self._assess_response_quality(
                task=task,
                step=step,
                observation=observation["message"],
                action_type=action_type,
                step_completed=step_completed,
                prince2_assessment=prince2_assessment,
            )
            if not response_quality.sufficient:
                ok = False
                step_completed = False
                error_type = "response_insufficient"
                observation["message"] = (
                    f"{observation['message']}\nResponse quality gate failed: "
                    f"score={response_quality.score:.3f} threshold={response_quality.threshold:.3f}; "
                    f"{'; '.join(response_quality.reasons)}"
                )

        if response_quality is not None:
            self._record_tool_transcript(
                iteration=iteration,
                step_id=step.id,
                tool="model",
                action_type="response_quality_assessment",
                success=response_quality.sufficient,
                summary=f"quality={response_quality.score:.3f}/{response_quality.threshold:.3f}",
                detail=dumps_ascii(response_quality.as_dict()),
                error_type=None if response_quality.sufficient else "response_insufficient",
            )

        if not ok and self.memory.failure_count(step.id) >= self.config.max_retries_per_step:
            escalated_model = self.router.escalate(model)
            return StepOutcome(
                ok=False,
                step_completed=False,
                model=escalated_model,
                action_type=action_type,
                observation=observation["message"],
                account=account,
                variant=self.handoff.model_variant_by_model.get(model),
                git_head_before=git_head_before,
                git_head_after=self._git_head(),
                error_type=error_type,
                prince2_assessment=prince2_assessment,
                prince2_role=prince2_role,
                response_quality=response_quality.as_dict() if response_quality is not None else None,
            )

        return StepOutcome(
            ok=ok,
            step_completed=step_completed,
            model=model,
            action_type=action_type,
            observation=observation["message"],
            account=account,
            variant=self.handoff.model_variant_by_model.get(model),
            git_head_before=git_head_before,
            git_head_after=self._git_head(),
            error_type=error_type,
            prince2_assessment=prince2_assessment,
            prince2_role=prince2_role,
            response_quality=response_quality.as_dict() if response_quality is not None else None,
        )

    def _assess_response_quality(
        self,
        *,
        task: str,
        step: PlanStep,
        observation: str,
        action_type: str,
        step_completed: bool,
        prince2_assessment: dict[str, Any] | None,
    ) -> ResponseQualityAssessment:
        return assess_response_quality(
            task=task,
            step=step,
            observation=observation,
            action_type=action_type,
            step_completed=step_completed,
            prince2_assessment=prince2_assessment,
        )

    def _extract_usage_metadata(self, payload: object) -> dict[str, int | None]:
        if not isinstance(payload, dict):
            return {}
        candidates = [
            payload.get("usage"),
            payload.get("token_usage"),
            payload.get("context_window"),
        ]
        merged: dict[str, object] = {}
        for candidate in candidates:
            if isinstance(candidate, dict):
                merged.update(candidate)
        aliases = {
            "input_tokens": ("input_tokens", "prompt_tokens", "total_input_tokens"),
            "output_tokens": ("output_tokens", "completion_tokens", "total_output_tokens"),
            "context_window_size": ("context_window_size", "context_size", "window_size"),
            "current_usage": ("current_usage", "used_tokens", "total_tokens"),
        }
        extracted: dict[str, int | None] = {}
        for target, keys in aliases.items():
            extracted[target] = None
            for key in keys:
                if key not in merged:
                    continue
                value = self._safe_positive_int(merged.get(key))
                if value is not None:
                    extracted[target] = value
                    break
        if extracted.get("current_usage") is None:
            input_tokens = extracted.get("input_tokens") or 0
            output_tokens = extracted.get("output_tokens") or 0
            total = input_tokens + output_tokens
            extracted["current_usage"] = total if total else None
        return extracted

    def _record_goal_usage(self, *, model: str, step_id: str, usage_metadata: dict[str, int | None]) -> None:
        if not any(usage_metadata.get(key) for key in ("input_tokens", "output_tokens", "current_usage")):
            return
        self.project_handoff.record_goal_token_usage(
            model=model,
            step_id=step_id,
            input_tokens=usage_metadata.get("input_tokens"),
            output_tokens=usage_metadata.get("output_tokens"),
            current_usage=usage_metadata.get("current_usage"),
        )

    def _safe_positive_int(self, value: object) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            number = int(float(str(value).strip()))
        except (TypeError, ValueError):
            return None
        if number < 0:
            return None
        return number

    def _configure_handoff_accounts(self) -> ModelPreferences:
        try:
            prefs = ModelPreferences.load(self.config.model_prefs_path)
        except OSError:
            prefs = ModelPreferences.default()
        self.handoff.account_env_by_target = dict(prefs.env_var_by_account or {})
        self.handoff.model_variant_by_model = dict(prefs.variant_by_model or {})
        return prefs

    def _configure_handoff_variant(
        self,
        *,
        prefs: ModelPreferences,
        model: str,
        task: str,
        step_text: str,
        failure_count: int,
        role_assignment: dict[str, Any] | None = None,
    ) -> None:
        if role_assignment:
            self._configure_handoff_role_route(role_assignment)
            return
        pinned = prefs.variant_for_model(model)
        if pinned:
            self.handoff.model_variant_by_model[model] = pinned
            return
        auto_variant = self.router.choose_variant(model, task, step_text, failure_count)
        if auto_variant:
            self.handoff.model_variant_by_model[model] = auto_variant
        else:
            self.handoff.model_variant_by_model.pop(model, None)

    def _configure_handoff_role_route(self, assignment: dict[str, Any]) -> None:
        provider = str(assignment.get("provider", "")).strip()
        provider_model = str(assignment.get("provider_model", "")).strip()
        if not provider or not provider_model:
            return
        self.handoff.model_variant_by_model[provider] = provider_model
        params = assignment.get("params", {})
        if isinstance(params, dict):
            self.handoff.model_params_by_model[provider] = {str(key): str(value) for key, value in params.items()}

    def _role_for_step(self, *, task: str, step: PlanStep) -> str:
        text = f"{task} {step.id} {step.title} {step.instruction}".lower()
        if "recovery-step" in step.id or any(token in text for token in ("exception", "tolerance", "re-baseline", "rebaseline", "change request")):
            return "change_authority"
        if any(token in text for token in ("implement", "modify", "write", "patch", "create", "build", "fix")):
            return "team_manager"
        if any(token in text for token in ("validate", "test", "quality", "verify", "wet-run", "wet run", "check")):
            return "project_assurance"
        if any(token in text for token in ("business case", "benefit", "cost", "budget", "stop/go", "go/no-go")):
            return "project_executive"
        if any(token in text for token in ("acceptance", "user", "adoption", "benefit realization")):
            return "senior_user"
        if any(token in text for token in ("supplier", "technical feasibility", "architecture", "integration")):
            return "senior_supplier"
        if any(token in text for token in ("log", "handoff", "record", "git", "trace")):
            return "project_support"
        return "project_manager"

    def _role_assignment_for_step(
        self,
        prefs: ModelPreferences,
        role: str,
        *,
        task: str,
        step: PlanStep,
        failure_count: int = 0,
    ) -> dict[str, Any] | None:
        node = self._role_tree_node_for_step(task=task, step=step, role=role)
        assignment = {}
        if node:
            candidate = node.get("assignment", {})
            if isinstance(candidate, dict):
                assignment = dict(candidate)
        if not assignment:
            assignment = prefs.prince2_role_assignment(role)
        if not assignment:
            return None
        if str(assignment.get("mode", "")).strip().lower() == "blocked":
            return self._fallback_assignment_for_node(prefs, node)
        provider = str(assignment.get("provider", "")).strip()
        if provider not in prefs.active_models():
            fallback = self._fallback_assignment_for_node(prefs, node)
            if fallback:
                return fallback
            return None
        if self._attempt_requires_model_escalation(step.id):
            escalated = self._escalate_role_assignment(
                prefs,
                assignment,
                node=node,
                task=task,
                step=step,
                failure_count=failure_count,
            )
            if escalated:
                return escalated
        return assignment

    def _fallback_assignment_for_node(self, prefs: ModelPreferences, node: dict[str, Any]) -> dict[str, Any] | None:
        pools = node.get("assignment_pool", {}) if isinstance(node, dict) else {}
        routes = pools.get("fallback", []) if isinstance(pools, dict) and isinstance(pools.get("fallback", []), list) else []
        for route in routes:
            if not isinstance(route, dict):
                continue
            if str(route.get("mode", "")).strip().lower() == "blocked":
                continue
            provider = str(route.get("provider", "")).strip()
            if provider in prefs.active_models():
                return dict(route)
        return None

    def _attempt_requires_model_escalation(self, step_id: str) -> bool:
        attempts = self.memory.recent_attempts(step_id, limit=1)
        if not attempts:
            return False
        latest = attempts[-1]
        if latest.success:
            return False
        if latest.error_type in {"critic_rejection", "critic_invalid_output", "prince2_closure_failure", "invalid_output", "wet_run_required", "response_insufficient", "verification_failed"}:
            return True
        combined = " ".join(
            part for part in (latest.action_type, latest.observation, latest.error_type or "") if part
        ).lower()
        return any(
            marker in combined
            for marker in (
                "does not clearly confirm",
                "missing a valid verdict",
                "no validation evidence",
                "weak closure evidence",
                "insufficient",
                "too vague",
                "not sufficient",
                "unclear",
            )
        )

    def _escalate_role_assignment(
        self,
        prefs: ModelPreferences,
        assignment: dict[str, Any],
        *,
        node: dict[str, Any],
        task: str,
        step: PlanStep,
        failure_count: int,
    ) -> dict[str, Any] | None:
        current_provider = str(assignment.get("provider", "")).strip()
        current_variant = str(assignment.get("provider_model", "")).strip()
        if not current_provider:
            return None

        escalated_variant = self.router.choose_variant(current_provider, task, step.instruction, failure_count=failure_count)
        if escalated_variant and escalated_variant != current_variant:
            return self._synthesized_role_assignment(
                assignment,
                provider=current_provider,
                provider_model=escalated_variant,
                account=self._select_account(current_provider),
                pool="escalated",
                source="router",
            )

        if failure_count >= 2 and current_provider in {"cheap", "chatgpt", "openai"}:
            next_provider = self.router.escalate(current_provider)
            if next_provider and next_provider != current_provider and next_provider in prefs.active_models():
                fallback = self._assignment_for_provider_in_pool(node, next_provider)
                if fallback:
                    return fallback
                recommended = self.router.recommend_route(task, step.instruction, failure_count=failure_count)
                return self._synthesized_role_assignment(
                    assignment,
                    provider=next_provider,
                    provider_model=recommended.provider_model
                    if recommended.provider == next_provider
                    else self.router.choose_variant(next_provider, task, step.instruction, failure_count=failure_count),
                    account=self._select_account(next_provider),
                    pool="escalated",
                    source="router",
                )

        escalation_provider = self.router.recommend_route(task, step.instruction, failure_count=failure_count).provider
        if escalation_provider and escalation_provider != current_provider and escalation_provider in prefs.active_models():
            fallback = self._assignment_for_provider_in_pool(node, escalation_provider)
            if fallback:
                return fallback
            recommended = self.router.recommend_route(task, step.instruction, failure_count=failure_count)
            return self._synthesized_role_assignment(
                assignment,
                provider=recommended.provider,
                provider_model=recommended.provider_model or self.router.choose_variant(
                    recommended.provider,
                    task,
                    step.instruction,
                    failure_count=failure_count,
                ),
                account=self._select_account(recommended.provider),
                pool="escalated",
                source="router",
            )

        return None

    def _assignment_for_provider_in_pool(self, node: dict[str, Any], provider: str) -> dict[str, Any] | None:
        pools = node.get("assignment_pool", {}) if isinstance(node, dict) else {}
        routes = pools.get("fallback", []) if isinstance(pools, dict) and isinstance(pools.get("fallback", []), list) else []
        for route in routes:
            if not isinstance(route, dict):
                continue
            if str(route.get("provider", "")).strip() == provider:
                return dict(route)
        return None

    def _synthesized_role_assignment(
        self,
        assignment: dict[str, Any],
        *,
        provider: str,
        provider_model: str | None,
        account: str | None,
        pool: str,
        source: str,
    ) -> dict[str, Any]:
        escalated = dict(assignment)
        escalated.update(
            {
                "provider": provider,
                "provider_model": provider_model or assignment.get("provider_model", ""),
                "account": account if account is not None else assignment.get("account"),
                "pool": pool,
                "source": source,
                "mode": "auto",
            }
        )
        return escalated

    def _role_tree_nodes(self) -> list[dict[str, Any]]:
        baseline = self.project_handoff.prince2_role_tree_baseline or {}
        tree = baseline.get("tree", {}) if isinstance(baseline, dict) else {}
        nodes = tree.get("nodes", []) if isinstance(tree, dict) else []
        return [dict(node) for node in nodes if isinstance(node, dict)]

    def _role_tree_node_for_role(self, role: str) -> dict[str, Any]:
        for node in self._role_tree_nodes():
            if str(node.get("role_type", "")).strip() == role:
                return node
        return {}

    def _role_tree_node_for_step(self, *, task: str, step: PlanStep, role: str) -> dict[str, Any]:
        nodes = [node for node in self._role_tree_nodes() if str(node.get("role_type", "")).strip() == role]
        if not nodes:
            return {}
        text = f"{task} {step.id} {step.title} {step.instruction}".lower()
        for node in nodes:
            node_id = str(node.get("node_id", "")).strip().lower()
            if node_id and node_id in text:
                return node
        for node in nodes:
            label = str(node.get("label", "")).strip().lower()
            if label and label in text:
                return node
        return nodes[0]

    def _git_head(self) -> str | None:
        result = self.git.head()
        if result.ok and result.stdout:
            return result.stdout.strip()
        return None

    def _select_account(self, model: str) -> str | None:
        try:
            return ModelPreferences.load(self.config.model_prefs_path).account_for_model(model)
        except (OSError, ValueError, TypeError):
            return None

    def _execute_with_account_failover(self, *, model: str, prompt: str, account: str | None):
        current_account = account
        result = self.handoff.execute(format_run_model(model, prompt, account=current_account))
        tried: set[str] = set()
        if current_account:
            tried.add(current_account)
        while not result.ok:
            self._record_model_block_if_present(model, result.error or result.output, account=current_account)
            next_account = self._next_account(model, current_account)
            if next_account is None or next_account in tried:
                break
            current_account = next_account
            tried.add(current_account)
            result = self.handoff.execute(format_run_model(model, prompt, account=current_account))
        return result, current_account

    def _run_devil_advocate_review(
        self,
        *,
        iteration: int,
        task: str,
        step: PlanStep,
        plan: list[PlanStep],
        model: str,
        account: str | None,
        primary_payload: dict[str, Any],
        primary_action: dict[str, Any],
        primary_output: str,
        primary_observation: str,
    ) -> dict[str, Any]:
        try:
            prefs = ModelPreferences.load(self.config.model_prefs_path)
        except (OSError, ValueError, TypeError):
            prefs = ModelPreferences.default()
        self.handoff.account_env_by_target = dict(prefs.env_var_by_account or {})
        critic_role = "project_assurance"
        critic_assignment = self._role_assignment_for_step(prefs, critic_role, task=task, step=step)
        critic_model = model
        critic_account = account
        if critic_assignment:
            candidate_model = str(critic_assignment.get("provider", "")).strip()
            if candidate_model:
                critic_model = candidate_model
            critic_account = str(critic_assignment.get("account", "")).strip() or self._select_account(critic_model)
            self._configure_handoff_variant(
                prefs=prefs,
                model=critic_model,
                task=task,
                step_text=step.instruction,
                failure_count=self.memory.failure_count(step.id),
                role_assignment=critic_assignment,
            )
        else:
            alternatives = self._available_alternative_models(model)
            if alternatives:
                critic_model = alternatives[0]
                critic_account = self._select_account(critic_model)
        prompt = self._build_devil_advocate_prompt(
            task=task,
            step=step,
            plan=plan,
            primary_payload=primary_payload,
            primary_action=primary_action,
            primary_output=primary_output,
            primary_observation=primary_observation,
        )
        result, critic_account = self._execute_with_account_failover(model=critic_model, prompt=prompt, account=critic_account)
        review = self._parse_devil_advocate_json(result.output)
        summary = review.get("error") if not review.get("ok") else str(review["payload"].get("verdict", "accept"))
        self._record_tool_transcript(
            iteration=iteration,
            step_id=step.id,
            tool="model",
            action_type="devil_advocate_review",
            success=bool(review.get("ok")),
            summary=summary or "devil advocate review",
            detail=result.output[:2000],
            error_type=None if review.get("ok") else "critic_invalid_output",
        )
        if not review.get("ok"):
            return {
                "ok": False,
                "model": critic_model,
                "account": critic_account,
                "result": result,
                "review": review.get("payload", {}),
                "error": review.get("error", "Devil advocate review is invalid."),
            }
        return {
            "ok": bool(review.get("ok")),
            "model": critic_model,
            "account": critic_account,
            "result": result,
            "review": review.get("payload", {}),
            "error": "",
        }

    def _accounts_configured(self, model: str) -> bool:
        try:
            prefs = ModelPreferences.load(self.config.model_prefs_path)
            return bool((prefs.accounts_by_model or {}).get(model))
        except (OSError, ValueError, TypeError):
            return False

    def _next_account(self, model: str, current: str | None) -> str | None:
        try:
            return ModelPreferences.load(self.config.model_prefs_path).next_account_for_model(model, current)
        except (OSError, ValueError, TypeError):
            return None

    def _fallback_model_after_failure(self, model: str) -> str:
        fallback = self.router.fallback_for_api_failure(model)
        if fallback != model:
            return fallback
        alternatives = self._available_alternative_models(model)
        return alternatives[0] if alternatives else fallback

    def _available_alternative_models(self, model: str) -> list[str]:
        try:
            prefs = ModelPreferences.load(self.config.model_prefs_path)
            active = prefs.active_models()
            return [candidate for candidate in active if candidate != model]
        except (OSError, ValueError, TypeError):
            status = self.router.status()
            return [candidate for candidate in status["active_models"] if candidate != model]

    def _rate_limit_decision(self, model: str, until: str | None, alternatives: list[str]) -> str:
        if self.config.rate_limit_decider is None:
            return "stop"
        decision = self.config.rate_limit_decider(model, until, alternatives)
        return str(decision or "stop").strip().lower()

    def _is_transient_network_failure(self, message: str | None) -> bool:
        if not message:
            return False
        lowered = message.lower()
        patterns = (
            "connection refused",
            "connection reset",
            "connection aborted",
            "network is unreachable",
            "temporary failure in name resolution",
            "name or service not known",
            "no route to host",
            "host unreachable",
            "timed out",
            "timeout",
            "request timed out",
            "read timed out",
            "write timed out",
            "ssl",
            "tls",
            "certificate verify failed",
            "proxy error",
            "bad gateway",
            "service unavailable",
            "gateway timeout",
            "network error",
            "network unavailable",
            "network outage",
            "outage",
            "blackout",
            "fetch failed",
            "failed to connect",
            "provider unavailable",
            "service outage",
            "maintenance",
        )
        return any(pattern in lowered for pattern in patterns)

    def _record_model_block_if_present(self, model: str, message: str, *, account: str | None = None) -> None:
        until = extract_blocked_until(message)
        if not until:
            return
        try:
            prefs = ModelPreferences.load(self.config.model_prefs_path)
            clean_message = str(message).strip().replace("\n", " ")[:240]
            snapshot = limit_snapshot_from_message(clean_message, blocked_until=until)
            if account:
                prefs.block_account(model, account, until)
                prefs.last_limit_message_by_account = dict(prefs.last_limit_message_by_account or {})
                prefs.last_limit_message_by_account[f"{model}:{account}"] = clean_message
                prefs.set_account_limit_snapshot(model, account, snapshot)
            else:
                prefs.blocked_until_by_model = dict(prefs.blocked_until_by_model or {})
                prefs.blocked_until_by_model[model] = until
                prefs.last_limit_message_by_model = dict(prefs.last_limit_message_by_model or {})
                prefs.last_limit_message_by_model[model] = clean_message
                prefs.set_model_limit_snapshot(model, snapshot)
            if prefs.preferred_model == model and not prefs.account_for_model(model):
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
        packet = self._build_model_communication_packet(task=task, step=step, plan=plan, last_observation=last_observation)
        return self._render_model_communication_packet(packet)

    def _build_devil_advocate_prompt(
        self,
        *,
        task: str,
        step: PlanStep,
        plan: list[PlanStep],
        primary_payload: dict[str, Any],
        primary_action: dict[str, Any],
        primary_output: str,
        primary_observation: str,
    ) -> str:
        packet = self._build_model_communication_packet(
            task=task,
            step=step,
            plan=plan,
            last_observation=primary_observation,
        )
        critic_sections = [
            PromptSection(
                "Devil advocate mission",
                "\n".join(
                    [
                        "You are the devil's advocate / Project Assurance critic.",
                        "Challenge the primary model response instead of agreeing with it.",
                        "Return strict JSON only.",
                        "Required keys: verdict, contradictions, missing_evidence, counter_argument, must_escalate, confidence.",
                        "Allowed verdict values: accept, revise, block.",
                    ]
                ),
            ),
            PromptSection(
                "Primary model response",
                "\n".join(
                    [
                        f"summary={primary_payload.get('summary', '')}",
                        f"validation={primary_payload.get('validation', '')}",
                        f"confidence={primary_payload.get('confidence', '')}",
                        f"action={dumps_ascii(primary_action, sort_keys=True)}",
                        "raw_output:",
                        primary_output,
                    ]
                ),
            ),
            PromptSection(
                "Critic focus",
                "\n".join(
                    [
                        "Find unsupported assumptions, missing wet-run evidence, unsafe shortcuts, hidden scope creep, and contradictions with the plan.",
                        "If the response depends on unproven claims, set verdict=revise or block.",
                        "If the response is sound but still risky, list the risk and keep verdict=accept with counter_argument.",
                    ]
                ),
            ),
        ]
        packet.sections = list(packet.sections) + critic_sections
        return self._render_model_communication_packet(packet)

    def _build_model_communication_packet(
        self,
        *,
        task: str,
        step: PlanStep,
        plan: list[PlanStep],
        last_observation: str,
        provider_limits: dict[str, object] | None = None,
    ) -> ModelCommunicationPacket:
        plan_lines = "\n".join(
            f"- {item.id}: {item.title} [{item.status}] validation={item.validation} wet_run_required={item.wet_run_required}"
            for item in plan
        )
        memory_summary = _executor_prompting.bounded_context(self.memory.summarize(), 2000, label="memory_summary")
        execution_log = _executor_prompting.bounded_context(self.memory.detailed_summary(), 4000, label="execution_log")
        handoff_log = _executor_prompting.bounded_context(self.project_handoff.detailed_summary(), 4000, label="handoff_log")
        active_role = self._role_for_step(task=task, step=step)
        scoped = _executor_prompting.role_scoped_context(self, active_role)
        risk_register = _executor_prompting.bounded_context(scoped["risks"], 2500, label="risk_register")
        issue_register = _executor_prompting.bounded_context(scoped["issues"], 2500, label="issue_register")
        quality_register = _executor_prompting.bounded_context(scoped["quality"], 2500, label="quality_register")
        lessons_log = _executor_prompting.bounded_context(scoped["lessons"], 2500, label="lessons_log")
        exception_plan = _executor_prompting.bounded_context(scoped["exception_plan"], 2000, label="exception_plan")
        model_context = _executor_prompting.model_context_files_section(self)
        role_context = _executor_prompting.bounded_context(
            _executor_prompting.prince2_role_automation_section(self, task, step),
            2500,
            label="prince2_role_automation",
        )
        node_context_packet = _executor_prompting.bounded_context(
            _executor_prompting.prince2_node_context_packet(self, task, step),
            5000,
            label="prince2_node_context_packet",
        )
        tool_schema_report = _executor_prompting.bounded_context(
            _executor_prompting.model_visible_tool_schema_section(self),
            6000,
            label="model_visible_tool_schema",
        )
        scoped_handoff_log = _executor_prompting.bounded_context(
            handoff_log if scoped["handoff_log"] else "Omitted by PRINCE2 role scope.",
            4000,
            label="handoff_log",
        )
        scoped_execution_log = _executor_prompting.bounded_context(
            execution_log if scoped["execution_log"] else "Omitted by PRINCE2 role scope.",
            4000,
            label="execution_log",
        )
        selected_backend = self.shell._selected_shell_backend()
        thread_start = "\n".join(
            [
                f"- workspace_root: {self.config.workspace_root}",
                f"- shell_backend_configured: {self.config.shell_backend}",
                f"- shell_backend_selected: {selected_backend.get('selected') or 'unknown'}",
                f"- shell_executable: {selected_backend.get('shell_executable') or 'unknown'}",
                f"- prince2_active_role: {active_role}",
                "- protocol_style: structured_turn_packet",
                "- transcript_style: typed_items",
            ]
        )
        turn_context = "\n".join(
            [
                f"Task:\n{task}",
                "Current step:",
                f"id={step.id}",
                f"title={step.title}",
                f"instruction={step.instruction}",
                f"validation={step.validation}",
                f"wet_run_required={step.wet_run_required}",
                "",
                "Plan:",
                plan_lines,
                "",
                "Previous observation:",
                last_observation or "None",
            ]
        )
        sections = [
            PromptSection("Thread Start", thread_start),
            PromptSection("Task", task),
            PromptSection("Turn Context", turn_context),
            PromptSection("Model context files", model_context),
            PromptSection(
                "Implicit project handoff context",
                self._bounded_context("handoff_summary", self.project_handoff.summary(), 2500),
            ),
            PromptSection(
                "Stage boundary view",
                self._bounded_context("stage_view", self.project_handoff.rendered_stage_view(), 3500),
            ),
            PromptSection("PRINCE2 role automation", role_context),
            PromptSection("PRINCE2 node AI context packet", node_context_packet),
            PromptSection("Model-visible tool schema validation", tool_schema_report),
            PromptSection(
                "PRINCE2 registers",
                "\n\n".join(
                    [
                        f"Risks:\n{risk_register}",
                        f"Issues:\n{issue_register}",
                        f"Quality:\n{quality_register}",
                        f"Lessons:\n{lessons_log}",
                        f"Exception plan:\n{exception_plan}",
                    ]
                ),
            ),
            PromptSection("Recent memory", memory_summary),
        ]
        transcript_items = [
            PromptTranscriptItem("handoff_log", scoped_handoff_log),
            PromptTranscriptItem("execution_log", scoped_execution_log),
            PromptTranscriptItem(
                "tool_transcript",
                self._bounded_context("tool_transcript", self.memory.transcript_summary(limit=8), 3000),
            ),
        ]
        contract_sections = [
            PromptSection(
                "Validation policy",
                "\n".join(
                    [
                        "- Always create or update relevant verification tests/checks for code or behavior changes.",
                        "- A dry-run is not a valid checkpoint by itself.",
                        "- A step may complete only after real wet-run evidence: executed tests, executed commands, observed files, or real tool output.",
                        "- If a wet-run is blocked, find a feasible alternative wet-run instead of accepting dry-run completion.",
                        "- Use complete only after the current step has real validation evidence.",
                    ]
                ),
            ),
            PromptSection(
                "Available actions and required fields",
                self._model_action_examples_section(),
            ),
            PromptSection(
                "Respond with strict JSON",
                "\n".join(
                    [
                        "{",
                        '  "summary": "brief reasoning",',
                        '  "confidence": 0.0,',
                        '  "risks": ["risk if relevant"],',
                        '  "validation": "how the action will be validated",',
                        '  "action": {',
                        '    "type": "one action"',
                        "  }",
                        "}",
                    ]
                ),
            ),
        ]
        return ModelCommunicationPacket(
            system_prompt=self.config.system_prompt,
            sections=sections,
            transcript_items=transcript_items,
            contract_sections=contract_sections,
            telemetry=provider_limits,
        )

    def _render_model_communication_packet(self, packet: ModelCommunicationPacket) -> str:
        blocks = [packet.system_prompt]
        for section in packet.sections:
            blocks.append(f"{section.title}:\n{section.body}")
        blocks.append("Typed transcript items:")
        for item in packet.transcript_items:
            blocks.append(f"[{item.item_type}]\n{item.body}")
        for section in packet.contract_sections:
            blocks.append(f"{section.title}:\n{section.body}")
        return "\n\n".join(blocks) + "\n"

    def _model_visible_tool_schema_report(self) -> dict[str, Any]:
        return _executor_prompting.model_visible_tool_schema_report(self)

    def _model_visible_tool_schema_section(self) -> str:
        return _executor_prompting.model_visible_tool_schema_section(self)

    def _model_action_examples_section(self) -> str:
        return _executor_prompting.model_action_examples_section(self)

    def _example_value_for_action_field(self, field: str) -> Any:
        return _executor_prompting.example_value_for_action_field(field)

    def _executor_action_branches(self) -> set[str]:
        return _executor_prompting.executor_action_branches(self)

    def _prince2_role_automation_section(self, task: str, step: PlanStep) -> str:
        return _executor_prompting.prince2_role_automation_section(self, task, step)

    def _prince2_node_context_packet(self, task: str, step: PlanStep) -> str:
        return _executor_prompting.prince2_node_context_packet(self, task, step)

    def _active_flow_context(self, active_node: dict[str, Any]) -> str:
        return _executor_prompting.active_flow_context(self, active_node)

    def _role_scoped_context(self, role: str) -> dict[str, str | bool]:
        return _executor_prompting.role_scoped_context(self, role)

    def _role_scope_description(self, role: str, node: dict[str, Any] | None = None) -> str:
        return _executor_prompting.role_scope_description(self, role, node=node)

    def _model_context_files_section(self) -> str:
        return _executor_prompting.model_context_files_section(self)

    def _bounded_context(self, label: str, text: str, limit: int) -> str:
        return _executor_prompting.bounded_context(text, limit, label=label)

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
        schema_error = self._validate_model_result_schema(payload, action)
        if schema_error:
            return {"ok": False, "error": schema_error}
        return {"ok": True, "action": action, "payload": payload}

    def _parse_devil_advocate_json(self, raw: str) -> dict[str, Any]:
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
            error = f"Devil advocate review did not return valid JSON: {last_error}" if last_error else "No JSON object found."
            return {"ok": False, "error": error}

        verdict = str(payload.get("verdict", "")).strip().lower()
        if verdict not in {"accept", "revise", "block"}:
            return {"ok": False, "error": "Devil advocate review is missing a valid verdict."}

        contradictions = payload.get("contradictions")
        if contradictions is not None and not (isinstance(contradictions, list) and all(isinstance(item, str) for item in contradictions)):
            return {"ok": False, "error": "Devil advocate review field 'contradictions' must be a list of strings."}

        missing_evidence = payload.get("missing_evidence")
        if missing_evidence is not None and not (
            isinstance(missing_evidence, list) and all(isinstance(item, str) for item in missing_evidence)
        ):
            return {"ok": False, "error": "Devil advocate review field 'missing_evidence' must be a list of strings."}

        counter_argument = payload.get("counter_argument")
        if counter_argument is not None and not isinstance(counter_argument, str):
            return {"ok": False, "error": "Devil advocate review field 'counter_argument' must be a string."}

        must_escalate = payload.get("must_escalate")
        if must_escalate is not None and not isinstance(must_escalate, bool):
            return {"ok": False, "error": "Devil advocate review field 'must_escalate' must be boolean."}

        confidence = payload.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, int | float) or isinstance(confidence, bool):
                return {"ok": False, "error": "Devil advocate review field 'confidence' must be a number from 0.0 to 1.0."}
            if confidence < 0 or confidence > 1:
                return {"ok": False, "error": "Devil advocate review field 'confidence' must be a number from 0.0 to 1.0."}

        return {"ok": True, "payload": payload}

    def _validate_model_result_schema(self, payload: dict[str, Any], action: dict[str, Any]) -> str:
        summary = payload.get("summary")
        if "summary" in payload and not isinstance(summary, str):
            return "Model JSON field 'summary' must be a string."
        confidence = payload.get("confidence")
        if confidence is not None:
            if not isinstance(confidence, int | float) or isinstance(confidence, bool):
                return "Model JSON field 'confidence' must be a number from 0.0 to 1.0."
            if confidence < 0 or confidence > 1:
                return "Model JSON field 'confidence' must be a number from 0.0 to 1.0."
        risks = payload.get("risks")
        if risks is not None and not (isinstance(risks, list) and all(isinstance(item, str) for item in risks)):
            return "Model JSON field 'risks' must be a list of strings."
        validation = payload.get("validation")
        if validation is not None and not (
            isinstance(validation, str)
            or (isinstance(validation, list) and all(isinstance(item, str) for item in validation))
        ):
            return "Model JSON field 'validation' must be a string or a list of strings."
        action_type = str(action.get("type", "")).strip()
        if action_type not in ALLOWED_MODEL_ACTIONS:
            if any(token in action_type.lower() for token in DESTRUCTIVE_ACTION_TOKENS):
                return f"Unknown destructive action denied: {action_type}"
            return f"Unsupported action type: {action_type}"
        schema = MODEL_ACTION_SCHEMAS.get(action_type, {})
        for field in schema.get("required", []):
            if field not in action:
                return f"Model JSON action '{action_type}' is missing required field '{field}'."
            value = action.get(field)
            if isinstance(value, str) and not value.strip():
                return f"Model JSON action '{action_type}' required field '{field}' must not be empty."
            if value is None:
                return f"Model JSON action '{action_type}' required field '{field}' must not be null."
        return ""

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

    def _run_action(self, action: dict[str, Any], *, iteration: int = 0, step_id: str = "") -> dict[str, Any]:
        action_type = action.get("type")
        if action_type == "shell":
            command = str(action.get("command", ""))
            status_before = self.git.status_porcelain().stdout.strip() if self._is_shell_command_likely_mutating(command) else ""
            head_before = self.git.head().stdout.strip() if "git commit" in command.lower() else ""
            result = self.shell.run(action.get("command", ""), cwd=action.get("cwd"))
            verification_ok, verification_message = self._verify_shell_action(command, result, status_before=status_before, head_before=head_before)
            observation = {
                "ok": result.ok,
                "message": result.output_preview or result.error or "Shell command executed.",
                "error_type": "runtime_error",
            }
            if result.ok and verification_message:
                observation["message"] = f"{observation['message']}\n{verification_message}"
            if result.ok and not verification_ok:
                observation["ok"] = False
                observation["message"] = f"{observation['message']}\n{verification_message}"
                observation["error_type"] = "verification_failed"
            self._record_tool_transcript(
                iteration=iteration,
                step_id=step_id,
                tool="shell",
                action_type=str(action_type),
                success=bool(observation["ok"]),
                summary=command,
                detail=observation["message"],
                duration_ms=result.duration_ms,
                error_type=None if observation["ok"] else observation["error_type"],
            )
            return observation

        if action_type == "shell_session_create":
            result = self.shell.create_session(cwd=action.get("cwd"))
            observation = {"ok": result.ok, "message": result.output_preview or result.error, "error_type": "runtime_error"}
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="shell", action_type=str(action_type), success=result.ok, summary="create shell session", detail=result.output_preview or result.error, duration_ms=result.duration_ms, error_type=None if result.ok else "runtime_error")
            return observation

        if action_type == "shell_session_send":
            command = str(action.get("command", ""))
            status_before = self.git.status_porcelain().stdout.strip() if self._is_shell_command_likely_mutating(command) else ""
            head_before = self.git.head().stdout.strip() if "git commit" in command.lower() else ""
            result = self.shell.send_session(action.get("session_id", ""), command)
            verification_ok, verification_message = self._verify_shell_action(command, result, status_before=status_before, head_before=head_before)
            observation = {"ok": result.ok, "message": result.output_preview or result.error or "Shell session command executed.", "error_type": "runtime_error"}
            if result.ok and verification_message:
                observation["message"] = f"{observation['message']}\n{verification_message}"
            if result.ok and not verification_ok:
                observation["ok"] = False
                observation["message"] = f"{observation['message']}\n{verification_message}"
                observation["error_type"] = "verification_failed"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="shell", action_type=str(action_type), success=bool(observation["ok"]), summary=command, detail=observation["message"], duration_ms=result.duration_ms, error_type=None if observation["ok"] else observation["error_type"])
            return observation

        if action_type == "shell_session_close":
            result = self.shell.close_session(action.get("session_id", ""))
            observation = {"ok": result.ok, "message": result.output_preview or result.error, "error_type": "runtime_error"}
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="shell", action_type=str(action_type), success=result.ok, summary="close shell session", detail=result.output_preview or result.error, duration_ms=result.duration_ms, error_type=None if result.ok else "runtime_error")
            return observation

        if action_type == "read_file":
            result = self.files.read(action.get("path", ""))
            message = result.content or result.error or "File read."
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "inspect_file":
            result = self.files.inspect(action.get("path", ""))
            if result.ok and isinstance(result.report, dict):
                message = json.dumps(result.report, ensure_ascii=True)
            else:
                message = result.error or "File inspection failed."
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "inspect_metadata_file":
            result = self.files.inspect_metadata(action.get("path", ""))
            if result.ok and isinstance(result.report, dict):
                message = json.dumps(result.report, ensure_ascii=True)
            else:
                message = result.error or "File metadata inspection failed."
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "write_file":
            result = self.files.write(action.get("path", ""), action.get("content", ""))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            message = f"Wrote file {result.path}" if result.ok else result.error
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "apply_patch":
            result = self.files.apply_patch(
                action.get("path", ""),
                action.get("search", ""),
                action.get("replace", ""),
            )
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            message = f"Patched file {result.path}" if result.ok else result.error
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "search_replace_file":
            result = self.files.search_replace(
                action.get("path", ""),
                action.get("search", ""),
                action.get("replace", ""),
                count=int(action.get("count", 1)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("search-replaced", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "insert_text_file":
            result = self.files.insert_text(
                action.get("path", ""),
                action.get("content", ""),
                line_number=int(action["line_number"]) if action.get("line_number") is not None else None,
                pattern=action.get("pattern"),
                position=str(action.get("position", "after")),
                occurrence=int(action.get("occurrence", 1)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("edited", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "delete_range_file":
            result = self.files.delete_range(
                action.get("path", ""),
                int(action.get("start_line", 0)),
                int(action.get("end_line", 0)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("edited", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "delete_backward_file":
            result = self.files.delete_backward(
                action.get("path", ""),
                int(action.get("count", 0)),
                line_number=int(action["line_number"]) if action.get("line_number") is not None else None,
                pattern=action.get("pattern"),
                occurrence=int(action.get("occurrence", 1)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("edited", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "replace_range_file":
            result = self.files.replace_range(
                action.get("path", ""),
                int(action.get("start_line", 0)),
                int(action.get("end_line", 0)),
                action.get("content", ""),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("edited", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "convert_encoding_file":
            result = self.files.convert_encoding(
                action.get("path", ""),
                action.get("target_encoding", ""),
                source_encoding=action.get("source_encoding"),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("converted", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "normalize_line_endings_file":
            result = self.files.normalize_line_endings(
                action.get("path", ""),
                action.get("newline", ""),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("normalized", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "copy_path_file":
            source_snapshot = self._snapshot_workspace_path(action.get("source", ""))
            result = self.files.copy_path(
                action.get("source", ""),
                action.get("destination", ""),
                overwrite=bool(action.get("overwrite", False)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("copied", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result, source_snapshot=source_snapshot)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=f"{action.get('source', '')} -> {action.get('destination', '')}", detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "move_path_file":
            source_snapshot = self._snapshot_workspace_path(action.get("source", ""))
            result = self.files.move_path(
                action.get("source", ""),
                action.get("destination", ""),
                overwrite=bool(action.get("overwrite", False)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("moved", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result, source_snapshot=source_snapshot)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=f"{action.get('source', '')} -> {action.get('destination', '')}", detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "delete_path_file":
            result = self.files.delete_path(
                action.get("path", ""),
                recursive=bool(action.get("recursive", False)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("deleted", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "chmod_path_file":
            result = self.files.chmod_path(
                action.get("path", ""),
                action.get("mode", ""),
                recursive=bool(action.get("recursive", False)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("chmod-updated", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "chown_path_file":
            result = self.files.chown_path(
                action.get("path", ""),
                user=action.get("user"),
                group=action.get("group"),
                recursive=bool(action.get("recursive", False)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("chown-updated", result, dry_run=bool(action.get("dry_run", False)))
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "patch_file":
            result = self.files.patch(action.get("path", ""), action.get("diff", ""))
            message = f"Patched file {result.path}" if result.ok else result.error
            verification_ok, verification_message = self._verify_file_action(action_type, action, result)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary=action.get("path", ""), detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "patch_files":
            patch_plan = self._snapshot_patch_plan(action.get("diff", ""))
            status_before = self.git.status_porcelain().stdout.strip()
            result = self.files.patch_files(action.get("diff", ""))
            message = f"Patched files:\n{result.content}" if result.ok else result.error
            verification_ok, verification_message = self._verify_file_action(action_type, action, result, git_status_before=status_before, patch_plan=patch_plan)
            if result.ok and verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            if result.ok and not verification_ok:
                message = f"{message}\n{verification_message}"
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=ok, summary="multi-file patch", detail=message, error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "file_error"))
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "file_error"}

        if action_type == "preview_patch_files":
            result = self.files.preview_patch_files(action.get("diff", ""))
            message = f"Patch preview:\n{result.content}" if result.ok else result.error
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary="multi-file patch preview", detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "list_files":
            result = self.files.list_files(
                base_path=action.get("base_path", "."),
                pattern=action.get("pattern", "*"),
                limit=int(action.get("limit", 200)),
            )
            message = result.content or result.error or "No files found."
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("base_path", "."), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "search_files":
            result = self.files.search(
                pattern=action.get("pattern", ""),
                base_path=action.get("base_path", "."),
                glob=action.get("glob", "*"),
                limit=int(action.get("limit", 100)),
            )
            message = result.content or result.error or "No matches found."
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("pattern", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "git_diff":
            result = self.git.diff()
            return self._git_observation(iteration, step_id, str(action_type), "git diff", result.stdout or result.error or "No diff.", result.ok)

        if action_type == "git_status":
            result = self.git.status()
            return self._git_observation(iteration, step_id, str(action_type), "git status", result.stdout or result.error or "Clean working tree.", result.ok)

        if action_type == "git_log":
            result = self.git.log(limit=int(action.get("limit", 20)), path=action.get("path") or None)
            return self._git_observation(iteration, step_id, str(action_type), action.get("path") or "git log", result.stdout or result.error or "No git history.", result.ok)

        if action_type == "git_show":
            result = self.git.show(revision=action.get("revision", "HEAD"), stat=bool(action.get("stat", False)))
            return self._git_observation(iteration, step_id, str(action_type), action.get("revision", "HEAD"), result.stdout or result.error or "No revision details.", result.ok)

        if action_type == "git_file_history":
            result = self.git.file_history(action.get("path", ""), limit=int(action.get("limit", 20)))
            return self._git_observation(iteration, step_id, str(action_type), action.get("path", ""), result.stdout or result.error or "No file history.", result.ok)

        if action_type == "git_commit":
            head_before = self._git_head()
            result = self.git.commit(action.get("message", "Agent commit"))
            verification_ok, verification_message = self._verify_git_commit_action(result, head_before=head_before)
            message = result.stdout or result.error or "Committed."
            if verification_message:
                message = f"{message}\n{verification_message}"
            ok = bool(result.ok and verification_ok)
            self._record_tool_transcript(
                iteration=iteration,
                step_id=step_id,
                tool="git",
                action_type=str(action_type),
                success=ok,
                summary=action.get("message", "Agent commit"),
                detail=message,
                error_type=None if ok else ("verification_failed" if result.ok and not verification_ok else "git_error"),
            )
            return {"ok": ok, "message": message, "error_type": "verification_failed" if result.ok and not verification_ok else "git_error"}

        if action_type == "complete":
            return {"ok": True, "message": action.get("message", "Step completed.")}

        return {"ok": False, "message": f"Unsupported action type: {action_type}", "error_type": "invalid_output"}

    def _record_tool_transcript(
        self,
        *,
        iteration: int,
        step_id: str,
        tool: str,
        action_type: str,
        success: bool,
        summary: str,
        detail: str = "",
        duration_ms: int = 0,
        error_type: str | None = None,
    ) -> None:
        self.memory.record_tool_transcript(
            iteration=iteration,
            step_id=step_id or "-",
            tool=tool,
            action_type=action_type,
            success=success,
            summary=summary,
            detail=detail,
            duration_ms=duration_ms,
            error_type=error_type,
        )

    def _file_edit_message(self, verb: str, result: object, *, dry_run: bool) -> str:
        if not bool(getattr(result, "ok", False)):
            return str(getattr(result, "error", "file operation failed"))
        path = str(getattr(result, "path", ""))
        report = getattr(result, "report", None)
        if dry_run:
            return f"Dry-run {verb} file {path}"
        if isinstance(report, dict) and report.get("changed"):
            return f"Edited file {path}"
        return f"No-op edit for file {path}"

    def _git_observation(self, iteration: int, step_id: str, action_type: str, summary: str, message: str, ok: bool) -> dict[str, Any]:
        self._record_tool_transcript(
            iteration=iteration,
            step_id=step_id,
            tool="git",
            action_type=action_type,
            success=ok,
            summary=summary,
            detail=message,
            error_type=None if ok else "git_error",
        )
        return {"ok": ok, "message": message, "error_type": "git_error"}

    def _is_shell_command_likely_mutating(self, command: str) -> bool:
        lowered = command.lower().strip()
        if not lowered:
            return False
        if ">" in command or ">>" in command or "| tee" in lowered:
            return True
        mutation_tokens = (
            "git add",
            "git commit",
            "git rm",
            "git mv",
            "git merge",
            "git rebase",
            "git reset",
            "mkdir ",
            "touch ",
            "cp ",
            "mv ",
            "rm ",
            "ln ",
            "chmod ",
            "chown ",
            "truncate",
            "sed -i",
            "perl -i",
            "install ",
        )
        return any(token in lowered for token in mutation_tokens)

    def _snapshot_workspace_path(self, path: str) -> dict[str, Any] | None:
        candidate = str(path).strip()
        if not candidate:
            return None
        read_result = self.files.read(candidate)
        if read_result.ok:
            return {
                "kind": "file",
                "path": read_result.path,
                "content": read_result.content,
            }
        metadata = self.files.inspect_metadata(candidate)
        if metadata.ok and isinstance(metadata.report, dict):
            report = dict(metadata.report)
            return {
                "kind": str(report.get("kind", "other")),
                "path": metadata.path,
                "report": report,
            }
        return None

    def _normalize_for_verification(self, content: str) -> str:
        return content.replace("\r\n", "\n").replace("\r", "\n")

    def _snapshot_patch_plan(self, diff: str) -> list[dict[str, Any]]:
        plan: list[dict[str, Any]] = []
        for patch in self.files._parse_file_patches(diff):  # noqa: SLF001
            target = self.files._target_path(str(patch["old_path"]), str(patch["new_path"]))  # noqa: SLF001
            if target is None:
                continue
            operation = str(patch["operation"])
            try:
                original_exists = target.exists()
                original_content = self.files.read(str(target)).content if original_exists else ""
            except OSError:
                original_exists = False
                original_content = ""
            plan.append(
                {
                    "target": str(target),
                    "operation": operation,
                    "hunks": patch["hunks"],
                    "original_exists": original_exists,
                    "original_content": original_content,
                }
            )
        return plan

    def _verify_shell_action(self, command: str, result: object, *, status_before: str, head_before: str = "") -> tuple[bool, str]:
        if not bool(getattr(result, "ok", False)):
            return False, str(getattr(result, "error", "")) or "Shell command failed."
        preview = str(getattr(result, "output_preview", "")) or str(getattr(result, "error", "")) or ""
        if not self._is_shell_command_likely_mutating(command):
            return True, "Verified shell command output."
        lowered = command.lower()
        if "git commit" in lowered:
            if "No changes to commit." in preview:
                return True, "Verified shell git commit: no changes to commit."
            head_after = self.git.head()
            if not head_after.ok:
                return False, f"Verification failed: unable to read git HEAD after shell git commit: {head_after.error or head_after.stderr or 'unknown'}"
            if not head_before:
                return False, "Verification failed: git HEAD before shell git commit was unavailable."
            if head_after.stdout.strip() == head_before.strip():
                return False, "Verification failed: shell git commit did not advance HEAD."
            return True, f"Verified shell git commit at {head_after.stdout.strip()[:12]}."
        status_after = self.git.status_porcelain()
        if not status_after.ok:
            return False, f"Verification failed: unable to inspect git status after shell command: {status_after.error or status_after.stderr or 'unknown'}"
        if status_after.stdout.strip() != status_before.strip():
            return True, "Verified shell command via workspace change."
        if any(token in preview.lower() for token in ("wrote", "created", "updated", "copied", "moved", "deleted", "removed", "installed", "saved", "committed")):
            return True, "Verified shell command via output evidence."
        return False, "Verification failed: shell command reported success but left no concrete workspace evidence."

    def _verify_file_action(
        self,
        action_type: str,
        action: dict[str, Any],
        result: object,
        *,
        source_snapshot: dict[str, Any] | None = None,
        git_status_before: str = "",
        patch_plan: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str]:
        if not bool(getattr(result, "ok", False)):
            return False, str(getattr(result, "error", "")) or "File action failed."

        report = getattr(result, "report", None)
        if not isinstance(report, dict):
            report = {}
        dry_run = bool(action.get("dry_run", False)) or bool(report.get("dry_run", False))
        if dry_run:
            return True, f"Verified dry-run preview for {action_type}."

        if action_type == "delete_path_file":
            target = str(action.get("path", "")).strip()
            if not target:
                return False, "Verification failed: delete_path_file is missing the target path."
            target_state = self.files.inspect_metadata(target)
            if target_state.ok:
                return False, f"Verification failed: path still exists after delete_path_file: {target_state.path}."
            return True, f"Verified delete_path_file removed {target}."

        if action_type in {"copy_path_file", "move_path_file"}:
            source = str(action.get("source", "")).strip()
            destination = str(action.get("destination", "")).strip()
            if not source or not destination:
                return False, "Verification failed: copy/move path is missing source or destination."
            destination_state = self.files.inspect_metadata(destination)
            if not destination_state.ok or not isinstance(destination_state.report, dict):
                return False, f"Verification failed: destination could not be inspected after {action_type}: {destination_state.error or getattr(destination_state, 'stderr', '') or 'unknown'}."
            source_state_after = self.files.inspect_metadata(source)
            if action_type == "move_path_file":
                if source_state_after.ok:
                    return False, f"Verification failed: move_path_file left the source present: {source_state_after.path}."
            elif not source_state_after.ok:
                return False, f"Verification failed: copy_path_file removed or hid the source unexpectedly: {source_state_after.error or getattr(source_state_after, 'stderr', '') or 'unknown'}."

            if source_snapshot and source_snapshot.get("kind") == "file":
                destination_read = self.files.read(destination)
                if not destination_read.ok:
                    return False, f"Verification failed: unable to read copied/moved file {destination}: {destination_read.error}."
                if self._normalize_for_verification(destination_read.content) != self._normalize_for_verification(str(source_snapshot.get("content", ""))):
                    return False, f"Verification failed: {action_type} destination content does not match the source snapshot."
            elif source_snapshot:
                destination_kind = str(destination_state.report.get("kind", ""))
                if destination_kind != str(source_snapshot.get("kind", "")):
                    return False, f"Verification failed: {action_type} destination kind {destination_kind!r} does not match source kind {source_snapshot.get('kind')!r}."
            return True, f"Verified {action_type} from {source} to {destination}."

        if action_type == "chmod_path_file":
            target = str(action.get("path", "")).strip()
            if not target:
                return False, "Verification failed: chmod_path_file is missing the target path."
            expected_mode = str(report.get("mode", "")).strip()
            metadata = self.files.inspect_metadata(target)
            if not metadata.ok or not isinstance(metadata.report, dict):
                return False, f"Verification failed: unable to inspect metadata for chmod_path_file: {metadata.error or getattr(metadata, 'stderr', '') or 'unknown'}."
            actual_mode = str(metadata.report.get("mode_octal", "")).strip()
            if expected_mode and actual_mode != expected_mode:
                return False, f"Verification failed: chmod_path_file mode mismatch expected={expected_mode} actual={actual_mode}."
            return True, f"Verified chmod_path_file on {target}."

        if action_type == "chown_path_file":
            target = str(action.get("path", "")).strip()
            if not target:
                return False, "Verification failed: chown_path_file is missing the target path."
            metadata = self.files.inspect_metadata(target)
            if not metadata.ok or not isinstance(metadata.report, dict):
                return False, f"Verification failed: unable to inspect metadata for chown_path_file: {metadata.error or getattr(metadata, 'stderr', '') or 'unknown'}."
            expected_uid = report.get("uid")
            expected_gid = report.get("gid")
            actual_uid = metadata.report.get("uid")
            actual_gid = metadata.report.get("gid")
            if expected_uid is not None and actual_uid != expected_uid:
                return False, f"Verification failed: chown_path_file uid mismatch expected={expected_uid} actual={actual_uid}."
            if expected_gid is not None and actual_gid != expected_gid:
                return False, f"Verification failed: chown_path_file gid mismatch expected={expected_gid} actual={actual_gid}."
            return True, f"Verified chown_path_file on {target}."

        if action_type == "patch_files":
            if patch_plan is not None:
                for item in patch_plan:
                    target = str(item.get("target", ""))
                    operation = str(item.get("operation", ""))
                    hunks = item.get("hunks", [])
                    original_content = str(item.get("original_content", ""))
                    expected = self.files._apply_unified_patch(original_content, hunks)  # noqa: SLF001
                    if expected is None:
                        return False, f"Verification failed: unable to replay patch plan for {target}."
                    target_state = self.files.inspect_metadata(target)
                    if operation == "delete":
                        if target_state.ok:
                            return False, f"Verification failed: patch_files did not delete {target}."
                        continue
                    target_read = self.files.read(target)
                    if not target_read.ok:
                        return False, f"Verification failed: unable to read patched file {target}: {target_read.error}."
                    if self._normalize_for_verification(target_read.content) != self._normalize_for_verification(expected):
                        return False, f"Verification failed: patch_files content mismatch for {target}."
                return True, "Verified patch_files through replayed file snapshots."
            status = self.git.status_porcelain()
            if not status.ok:
                return False, f"Verification failed: unable to inspect git status after patch_files: {status.error or status.stderr or 'unknown'}."
            if not status.stdout.strip():
                return False, "Verification failed: patch_files reported success but left no git-visible changes."
            if git_status_before.strip() == status.stdout.strip():
                return False, "Verification failed: patch_files left the workspace status unchanged."
            return True, "Verified patch_files through workspace status changes."

        path = str(action.get("path", "")).strip() or str(getattr(result, "path", "")).strip()
        if not path:
            return False, f"Verification failed: {action_type} is missing the target path."
        readback = self.files.read(path)
        if not readback.ok:
            return False, f"Verification failed: unable to read back {path}: {readback.error}."
        if report.get("changed") is False:
            return True, f"Verified {action_type} no-op on {path}."
        expected_content = str(getattr(result, "content", ""))
        if self._normalize_for_verification(readback.content) != self._normalize_for_verification(expected_content):
            return False, f"Verification failed: read-back content mismatch for {path}."
        return True, f"Verified {action_type} by reading back {path}."

    def _verify_git_commit_action(self, result: object, *, head_before: str) -> tuple[bool, str]:
        if not bool(getattr(result, "ok", False)):
            return False, str(getattr(result, "error", "")) or "Git commit failed."
        message = str(getattr(result, "stdout", "")) or str(getattr(result, "error", "")) or ""
        if "No changes to commit." in message:
            return True, "Verified git commit: no changes to commit."
        head_after = self.git.head()
        if not head_after.ok:
            return False, f"Verification failed: unable to read git HEAD after commit: {head_after.error or head_after.stderr or 'unknown'}"
        if not head_before:
            return False, "Verification failed: git HEAD before commit was unavailable."
        if head_after.stdout.strip() == head_before.strip():
            return False, "Verification failed: git commit did not advance HEAD."
        status = self.git.status_porcelain()
        if status.ok and status.stdout.strip():
            return False, "Verification failed: git commit left the workspace dirty."
        return True, f"Verified git commit at {head_after.stdout.strip()[:12]}."

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
        if "wrote file" in lower or "patched file" in lower or "edited file" in lower:
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
            "inspect_file",
            "inspect_metadata_file",
            "write_file",
            "apply_patch",
            "search_replace_file",
            "insert_text_file",
            "delete_range_file",
            "delete_backward_file",
            "replace_range_file",
            "convert_encoding_file",
            "normalize_line_endings_file",
            "copy_path_file",
            "move_path_file",
            "delete_path_file",
            "chmod_path_file",
            "chown_path_file",
            "patch_file",
            "patch_files",
            "preview_patch_files",
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
