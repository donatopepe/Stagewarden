from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .config import AgentConfig
from .handoff import HandoffManager, format_run_model
from .memory import MemoryStore
from .modelprefs import ModelPreferences, extract_blocked_until, limit_snapshot_from_message
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "sections": [section.as_dict() for section in self.sections],
            "transcript_items": [item.as_dict() for item in self.transcript_items],
            "contract_sections": [section.as_dict() for section in self.contract_sections],
        }


ALLOWED_MODEL_ACTIONS = {
    "shell",
    "shell_session_create",
    "shell_session_send",
    "shell_session_close",
    "read_file",
    "inspect_file",
    "write_file",
    "apply_patch",
    "search_replace_file",
    "insert_text_file",
    "delete_range_file",
    "delete_backward_file",
    "replace_range_file",
    "convert_encoding_file",
    "normalize_line_endings_file",
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
        role_assignment = self._role_assignment_for_step(prefs, prince2_role, task=task, step=step)
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
            rate_limit_until = extract_blocked_until(result.error or result.output)
            fallback_model = self._fallback_model_after_failure(model)
            if rate_limit_until:
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
                            f"Provider {model} is rate-limited until {rate_limit_until}. "
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
                            f"Provider {model} is rate-limited until {rate_limit_until}. "
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
            if not fallback.ok:
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
        usage_metadata = self._extract_usage_metadata(parsed.get("payload", {}))
        action_type = action.get("type", "").strip()
        observation = self._run_action(action, iteration=iteration, step_id=step.id)
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
                account=account,
                variant=self.handoff.model_variant_by_model.get(model),
                git_head_before=git_head_before,
                git_head_after=self._git_head(),
                error_type=error_type,
                prince2_assessment=prince2_assessment,
                prince2_role=prince2_role,
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

    def _role_assignment_for_step(self, prefs: ModelPreferences, role: str, *, task: str, step: PlanStep) -> dict[str, Any] | None:
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
        provider = str(assignment.get("provider", "")).strip()
        if provider not in prefs.active_models():
            fallback = self._fallback_assignment_for_node(prefs, node)
            if fallback:
                return fallback
            return None
        return assignment

    def _fallback_assignment_for_node(self, prefs: ModelPreferences, node: dict[str, Any]) -> dict[str, Any] | None:
        pools = node.get("assignment_pool", {}) if isinstance(node, dict) else {}
        routes = pools.get("fallback", []) if isinstance(pools, dict) and isinstance(pools.get("fallback", []), list) else []
        for route in routes:
            if not isinstance(route, dict):
                continue
            provider = str(route.get("provider", "")).strip()
            if provider in prefs.active_models():
                return dict(route)
        return None

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
        packet = self._build_model_communication_packet(
            task=task,
            step=step,
            plan=plan,
            last_observation=last_observation,
        )
        return self._render_model_communication_packet(packet)

    def _build_model_communication_packet(
        self,
        *,
        task: str,
        step: PlanStep,
        plan: list[PlanStep],
        last_observation: str,
    ) -> ModelCommunicationPacket:
        plan_lines = "\n".join(
            f"- {item.id}: {item.title} [{item.status}] validation={item.validation} wet_run_required={item.wet_run_required}"
            for item in plan
        )
        memory_summary = self._bounded_context("memory_summary", self.memory.summarize(), 2000)
        execution_log = self._bounded_context("execution_log", self.memory.detailed_summary(), 4000)
        handoff_log = self._bounded_context("handoff_log", self.project_handoff.detailed_summary(), 4000)
        active_role = self._role_for_step(task=task, step=step)
        scoped = self._role_scoped_context(active_role)
        risk_register = self._bounded_context("risk_register", scoped["risks"], 2500)
        issue_register = self._bounded_context("issue_register", scoped["issues"], 2500)
        quality_register = self._bounded_context("quality_register", scoped["quality"], 2500)
        lessons_log = self._bounded_context("lessons_log", scoped["lessons"], 2500)
        exception_plan = self._bounded_context("exception_plan", scoped["exception_plan"], 2000)
        model_context = self._model_context_files_section()
        role_context = self._bounded_context("prince2_role_automation", self._prince2_role_automation_section(task, step), 2500)
        node_context_packet = self._bounded_context("prince2_node_context_packet", self._prince2_node_context_packet(task, step), 5000)
        scoped_handoff_log = self._bounded_context("handoff_log", handoff_log if scoped["handoff_log"] else "Omitted by PRINCE2 role scope.", 4000)
        scoped_execution_log = self._bounded_context("execution_log", execution_log if scoped["execution_log"] else "Omitted by PRINCE2 role scope.", 4000)
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
                "\n".join(
                    [
                        '1. shell -> {"type":"shell","command":"...","cwd":"optional-relative-path"}',
                        '2. shell_session_create -> {"type":"shell_session_create","cwd":"optional-relative-path"}',
                        '3. shell_session_send -> {"type":"shell_session_send","session_id":"session id","command":"..."}',
                        '4. shell_session_close -> {"type":"shell_session_close","session_id":"session id"}',
                        '5. read_file -> {"type":"read_file","path":"relative/path"}',
                        '6. inspect_file -> {"type":"inspect_file","path":"relative/path"}',
                        '7. write_file -> {"type":"write_file","path":"relative/path","content":"full file contents"}',
                        '8. apply_patch -> {"type":"apply_patch","path":"relative/path","search":"old text","replace":"new text"}',
                        '9. search_replace_file -> {"type":"search_replace_file","path":"relative/path","search":"old text","replace":"new text","count":1,"dry_run":false}',
                        '10. insert_text_file -> {"type":"insert_text_file","path":"relative/path","content":"text to insert","line_number":12,"pattern":"optional anchor","position":"before|after","occurrence":1,"dry_run":false}',
                        '11. delete_range_file -> {"type":"delete_range_file","path":"relative/path","start_line":4,"end_line":7,"dry_run":false}',
                        '12. delete_backward_file -> {"type":"delete_backward_file","path":"relative/path","count":2,"line_number":10,"pattern":"optional anchor","occurrence":1,"dry_run":false}',
                        '13. replace_range_file -> {"type":"replace_range_file","path":"relative/path","start_line":4,"end_line":7,"content":"replacement block","dry_run":false}',
                        '14. convert_encoding_file -> {"type":"convert_encoding_file","path":"relative/path","target_encoding":"utf-8","source_encoding":"optional-codec","dry_run":false}',
                        '15. normalize_line_endings_file -> {"type":"normalize_line_endings_file","path":"relative/path","newline":"lf|crlf|cr","dry_run":false}',
                        '16. patch_file -> {"type":"patch_file","path":"relative/path","diff":"unified diff for one file"}',
                        '17. patch_files -> {"type":"patch_files","diff":"unified diff with one or more files"}',
                        '18. preview_patch_files -> {"type":"preview_patch_files","diff":"unified diff with one or more files"}',
                        '19. list_files -> {"type":"list_files","base_path":"optional-relative-path","pattern":"glob pattern","limit":100}',
                        '20. search_files -> {"type":"search_files","pattern":"regex","base_path":"optional-relative-path","glob":"glob pattern","limit":50}',
                        '21. git_status -> {"type":"git_status"}',
                        '22. git_diff -> {"type":"git_diff"}',
                        '23. git_log -> {"type":"git_log","limit":20,"path":"optional-relative-path"}',
                        '24. git_show -> {"type":"git_show","revision":"HEAD","stat":true}',
                        '25. git_file_history -> {"type":"git_file_history","path":"relative/path","limit":20}',
                        '26. git_commit -> {"type":"git_commit","message":"commit message"}',
                        '27. complete -> {"type":"complete","message":"why the current step is done"}',
                    ]
                ),
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

    def _prince2_role_automation_section(self, task: str, step: PlanStep) -> str:
        active_role = self._role_for_step(task=task, step=step)
        active_node = self._role_tree_node_for_step(task=task, step=step, role=active_role)
        context_rule = active_node.get("context_rule", {}) if active_node else {}
        context_include = context_rule.get("include", []) if isinstance(context_rule, dict) else []
        context_exclude = context_rule.get("exclude", []) if isinstance(context_rule, dict) else []
        lines = [
            f"- active_role: {active_role}",
            f"- active_role_node: {active_node.get('node_id', 'unbaselined') if active_node else 'unbaselined'}",
            f"- active_role_parent_node: {active_node.get('parent_id') or 'none' if active_node else 'none'}",
            f"- active_role_level: {active_node.get('level', 'unbaselined') if active_node else 'unbaselined'}",
            f"- active_role_responsibility: {PRINCE2_ROLE_AUTOMATION_RULES.get(active_role, 'controlled project work')}",
            f"- active_node_accountability_boundary: {active_node.get('accountability_boundary', 'static role fallback') if active_node else 'static role fallback'}",
            f"- active_node_delegated_authority: {active_node.get('delegated_authority', 'static role fallback') if active_node else 'static role fallback'}",
            "- automation_rule: plan via Project Manager, deliver via Team Manager, validate via Project Assurance, escalate exceptions or tolerance breaches via Change Authority.",
            "- governance_rule: do not bypass accountability; record evidence in handoff and use Project Executive for business/cost/benefit stop-go decisions.",
            f"- context_scope: {self._role_scope_description(active_role, active_node)}",
            f"- context_include: {', '.join(str(item) for item in context_include) if context_include else 'static role fallback'}",
            f"- context_exclude: {', '.join(str(item) for item in context_exclude) if context_exclude else 'static role fallback'}",
            self._active_flow_context(active_node),
        ]
        assignment = active_node.get("assignment", {}) if active_node else {}
        if not isinstance(assignment, dict) or not assignment:
            assignment = self.project_handoff.prince2_roles.get(active_role, {})
        pools = active_node.get("assignment_pool", {}) if active_node and isinstance(active_node.get("assignment_pool"), dict) else {}
        if assignment:
            params = assignment.get("params", {})
            params_text = ",".join(f"{key}={value}" for key, value in sorted(params.items())) if isinstance(params, dict) else ""
            lines.append(
                f"- active_role_route: provider={assignment.get('provider', 'unknown')} "
                f"provider_model={assignment.get('provider_model', 'unknown')} "
                f"account={assignment.get('account') or 'none'}"
                + (f" params={params_text}" if params_text else "")
            )
        else:
            lines.append("- active_role_route: unassigned; use router default and preserve role accountability in reasoning.")
        for pool_name in ("reviewer", "fallback"):
            routes = pools.get(pool_name, []) if isinstance(pools.get(pool_name, []), list) else []
            if routes:
                rendered = []
                for route in routes:
                    if not isinstance(route, dict):
                        continue
                    rendered.append(
                        f"{route.get('provider', 'unknown')}:{route.get('provider_model', 'provider-default')}"
                        + (f":{route.get('account')}" if route.get("account") else "")
                    )
                lines.append(f"- active_role_{pool_name}_pool: {', '.join(rendered) if rendered else 'none'}")
        return "\n".join(lines)

    def _prince2_node_context_packet(self, task: str, step: PlanStep) -> str:
        active_role = self._role_for_step(task=task, step=step)
        active_node = self._role_tree_node_for_step(task=task, step=step, role=active_role)
        runtime = self.project_handoff.prince2_node_runtime if isinstance(self.project_handoff.prince2_node_runtime, dict) else {}
        runtime_nodes = [node for node in runtime.get("nodes", []) if isinstance(node, dict)]
        runtime_node = None
        if active_node:
            node_id = str(active_node.get("node_id", "")).strip()
            runtime_node = next((item for item in runtime_nodes if str(item.get("node_id", "")).strip() == node_id), None)
        node = runtime_node or active_node or {}
        context_rule = node.get("context_rule", {}) if isinstance(node.get("context_rule"), dict) else {}
        assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
        flow = build_prince2_role_flow()
        edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
        node_id = str(node.get("node_id", "")).strip()
        incoming = [edge for edge in edges if str(edge.get("target_node", "")).strip() == node_id]
        outgoing = [edge for edge in edges if str(edge.get("source_node", "")).strip() == node_id]
        runtime_capabilities = detect_runtime_capabilities(self.config.workspace_root)
        selected_backend = self.shell._selected_shell_backend()
        lines = [
            f"- node_id: {node_id or 'unbaselined'}",
            f"- node_label: {node.get('label', 'unbaselined')}",
            f"- role_type: {node.get('role_type', active_role)}",
            f"- runtime_state: {node.get('state', 'unknown')}",
            f"- wait_status: {node.get('wait_status', 'none')}",
            f"- wait_reason: {node.get('wait_reason') or 'none'}",
            f"- wake_triggers: {', '.join(str(item) for item in node.get('wake_triggers', [])) if isinstance(node.get('wake_triggers', []), list) and node.get('wake_triggers', []) else 'none'}",
            f"- inbox_count: {node.get('inbox_count', 0)} outbox_count: {node.get('outbox_count', 0)}",
            f"- transcript_refs: {', '.join(str(item) for item in node.get('transcript_refs', [])) if isinstance(node.get('transcript_refs', []), list) and node.get('transcript_refs', []) else 'none'}",
            f"- provider: {assignment.get('provider', 'unknown') if assignment else 'unassigned'}",
            f"- provider_model: {assignment.get('provider_model', 'unknown') if assignment else 'unassigned'}",
            f"- account: {assignment.get('account') or 'none' if assignment else 'none'}",
            f"- responsibility_domain: {node.get('responsibility_domain', PRINCE2_ROLE_AUTOMATION_RULES.get(active_role, 'controlled project work'))}",
            f"- context_scope: {node.get('context_scope', PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(active_role, 'controlled project work'))}",
            f"- accountability_boundary: {node.get('accountability_boundary', 'static role fallback')}",
            f"- delegated_authority: {node.get('delegated_authority', 'static role fallback')}",
            f"- context_include: {', '.join(str(item) for item in context_rule.get('include', [])) if isinstance(context_rule.get('include', []), list) and context_rule.get('include', []) else 'none'}",
            f"- context_exclude: {', '.join(str(item) for item in context_rule.get('exclude', [])) if isinstance(context_rule.get('exclude', []), list) and context_rule.get('exclude', []) else 'none'}",
            f"- communication_incoming_edges: {', '.join(str(edge.get('edge_id')) for edge in incoming) if incoming else 'none'}",
            f"- communication_outgoing_edges: {', '.join(str(edge.get('edge_id')) for edge in outgoing) if outgoing else 'none'}",
            "- communication_commands: roles messages [node_id] | role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> | role wait <node_id> reason=<text> | role wake <node_id> trigger=<name> | role tick <node_id>",
            f"- workspace: {self.config.workspace_root}",
            f"- os_family: {runtime_capabilities.get('os_family', 'unknown')}",
            f"- recommended_shell: {runtime_capabilities.get('recommended_shell', 'unknown')}",
            f"- shell_backend_selected: {selected_backend.get('selected') or 'unknown'}",
            f"- core_agent_capabilities: shell=true files=true git=true wet_run_required=true",
            f"- model_actions: {', '.join(sorted(ALLOWED_MODEL_ACTIONS))}",
            "- file_operations: read_file, inspect_file, write_file, apply_patch, search_replace_file, insert_text_file, delete_range_file, delete_backward_file, replace_range_file, convert_encoding_file, normalize_line_endings_file, patch_file, patch_files, preview_patch_files, list_files, search_files",
            "- git_operations: git_status, git_diff, git_log, git_show, git_file_history, git_commit",
            "- shell_operations: shell, shell_session_create, shell_session_send, shell_session_close",
            f"- project_task: {self.project_handoff.task or 'none'}",
            f"- project_status: {self.project_handoff.status or 'idle'}",
            f"- current_step: {self.project_handoff.current_step_id or 'none'} [{self.project_handoff.current_step_status or 'none'}]",
        ]
        return "\n".join(lines)

    def _active_flow_context(self, active_node: dict[str, Any]) -> str:
        node_id = str(active_node.get("node_id", "")) if active_node else ""
        flow = build_prince2_role_flow()
        edges = [edge for edge in flow.get("edges", []) if isinstance(edge, dict)]
        incoming = [edge for edge in edges if edge.get("target_node") == node_id]
        outgoing = [edge for edge in edges if edge.get("source_node") == node_id]
        if not node_id:
            return "- active_flow_edges: none; context expansion requires formal PRINCE2 event."
        lines = [
            "- active_flow_rule: context moves only through approved PRINCE2 flow edges; fallback changes route, not context scope.",
            f"- active_flow_incoming: {', '.join(str(edge.get('edge_id')) for edge in incoming) if incoming else 'none'}",
            f"- active_flow_outgoing: {', '.join(str(edge.get('edge_id')) for edge in outgoing) if outgoing else 'none'}",
        ]
        for edge in incoming + outgoing:
            payload = edge.get("payload_scope", [])
            payload_text = ", ".join(str(item) for item in payload) if isinstance(payload, list) else str(payload)
            lines.append(
                f"- flow_edge {edge.get('edge_id')}: trigger={edge.get('trigger')} "
                f"type={edge.get('flow_type')} payload_scope={payload_text} "
                f"validation={edge.get('validation_condition')}"
            )
        return "\n".join(lines)

    def _role_scoped_context(self, role: str) -> dict[str, str | bool]:
        rendered = {
            "risks": self.project_handoff.rendered_risks(),
            "issues": self.project_handoff.rendered_issues(),
            "quality": self.project_handoff.rendered_quality(),
            "lessons": self.project_handoff.rendered_lessons(),
            "exception_plan": self.project_handoff.rendered_exception_plan(),
        }
        omitted = "Omitted by PRINCE2 role scope."
        if role == "team_manager":
            return {
                "risks": omitted,
                "issues": omitted,
                "quality": rendered["quality"],
                "lessons": rendered["lessons"],
                "exception_plan": omitted,
                "handoff_log": False,
                "execution_log": False,
            }
        if role == "project_assurance":
            return {
                "risks": rendered["risks"],
                "issues": rendered["issues"],
                "quality": rendered["quality"],
                "lessons": rendered["lessons"],
                "exception_plan": omitted,
                "handoff_log": True,
                "execution_log": True,
            }
        if role == "change_authority":
            return {
                "risks": rendered["risks"],
                "issues": rendered["issues"],
                "quality": rendered["quality"],
                "lessons": rendered["lessons"],
                "exception_plan": rendered["exception_plan"],
                "handoff_log": True,
                "execution_log": False,
            }
        if role == "project_executive":
            return {
                "risks": rendered["risks"],
                "issues": rendered["issues"],
                "quality": omitted,
                "lessons": rendered["lessons"],
                "exception_plan": rendered["exception_plan"],
                "handoff_log": True,
                "execution_log": False,
            }
        if role in {"senior_user", "senior_supplier"}:
            return {
                "risks": rendered["risks"],
                "issues": rendered["issues"],
                "quality": rendered["quality"],
                "lessons": rendered["lessons"],
                "exception_plan": omitted,
                "handoff_log": False,
                "execution_log": False,
            }
        if role == "project_support":
            return {
                "risks": omitted,
                "issues": rendered["issues"],
                "quality": rendered["quality"],
                "lessons": rendered["lessons"],
                "exception_plan": rendered["exception_plan"],
                "handoff_log": True,
                "execution_log": True,
            }
        return {
            "risks": rendered["risks"],
            "issues": rendered["issues"],
            "quality": rendered["quality"],
            "lessons": rendered["lessons"],
            "exception_plan": rendered["exception_plan"],
            "handoff_log": True,
            "execution_log": True,
        }

    def _role_scope_description(self, role: str, node: dict[str, Any] | None = None) -> str:
        node = node or self._role_tree_node_for_role(role)
        if node.get("context_scope"):
            return str(node["context_scope"])
        return PRINCE2_ROLE_SCOPE_DESCRIPTIONS.get(role, "controlled project work")

    def _model_context_files_section(self) -> str:
        status = self.git.status()
        porcelain = self.git.status_porcelain()
        dirty_state = "unknown"
        status_preview = status.stdout or status.error
        if porcelain.ok:
            dirty_state = "dirty" if porcelain.stdout.strip() else "clean"
        elif status.ok:
            dirty_state = "dirty" if status.stdout and any(line and not line.startswith("##") for line in status.stdout.splitlines()) else "clean"
        view = self.project_handoff.stage_view()
        backlog = view["backlog_statuses"]
        git_boundary = view["git_boundary"]
        lines = [
            f"- handoff_file: {self.config.handoff_path.name}",
            f"- memory_file: {self.config.memory_path.name}",
            f"- trace_file: {self.config.trace_path.name}",
            f"- recovery_state: {view['recovery_state']}",
            f"- backlog_status: ready={backlog['ready']} planned={backlog['planned']} in_progress={backlog['in_progress']} blocked={backlog['blocked']} done={backlog['done']}",
            f"- git_boundary: baseline={git_boundary['baseline']} current={git_boundary['current']}",
            f"- git_dirty_state: {dirty_state}",
            f"- git_status: {self._bounded_context('git_status', status_preview or 'No git status available.', 1200)}",
            "- context_boundaries: sections are truncated with explicit markers; consult files through read_file when exact full context is needed.",
        ]
        return "\n".join(lines)

    def _bounded_context(self, label: str, text: str, limit: int) -> str:
        clean = text if text else ""
        if len(clean) <= limit:
            return clean
        remaining = len(clean) - limit
        return f"{clean[:limit]}\n[truncated {label}: {remaining} chars omitted]"

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
            result = self.shell.run(action.get("command", ""), cwd=action.get("cwd"))
            observation = {
                "ok": result.ok,
                "message": result.output_preview or result.error or "Shell command executed.",
                "error_type": "runtime_error",
            }
            self._record_tool_transcript(
                iteration=iteration,
                step_id=step_id,
                tool="shell",
                action_type=str(action_type),
                success=result.ok,
                summary=action.get("command", ""),
                detail=result.output_preview or result.error,
                duration_ms=result.duration_ms,
                error_type=None if result.ok else "runtime_error",
            )
            return observation

        if action_type == "shell_session_create":
            result = self.shell.create_session(cwd=action.get("cwd"))
            observation = {"ok": result.ok, "message": result.output_preview or result.error, "error_type": "runtime_error"}
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="shell", action_type=str(action_type), success=result.ok, summary="create shell session", detail=result.output_preview or result.error, duration_ms=result.duration_ms, error_type=None if result.ok else "runtime_error")
            return observation

        if action_type == "shell_session_send":
            result = self.shell.send_session(action.get("session_id", ""), action.get("command", ""))
            observation = {"ok": result.ok, "message": result.output_preview or result.error, "error_type": "runtime_error"}
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="shell", action_type=str(action_type), success=result.ok, summary=action.get("command", ""), detail=result.output_preview or result.error, duration_ms=result.duration_ms, error_type=None if result.ok else "runtime_error")
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

        if action_type == "write_file":
            result = self.files.write(action.get("path", ""), action.get("content", ""))
            message = f"Wrote file {result.path}" if result.ok else result.error
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "apply_patch":
            result = self.files.apply_patch(
                action.get("path", ""),
                action.get("search", ""),
                action.get("replace", ""),
            )
            message = f"Patched file {result.path}" if result.ok else result.error
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "search_replace_file":
            result = self.files.search_replace(
                action.get("path", ""),
                action.get("search", ""),
                action.get("replace", ""),
                count=int(action.get("count", 1)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("search-replaced", result, dry_run=bool(action.get("dry_run", False)))
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

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
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "delete_range_file":
            result = self.files.delete_range(
                action.get("path", ""),
                int(action.get("start_line", 0)),
                int(action.get("end_line", 0)),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("edited", result, dry_run=bool(action.get("dry_run", False)))
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

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
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "replace_range_file":
            result = self.files.replace_range(
                action.get("path", ""),
                int(action.get("start_line", 0)),
                int(action.get("end_line", 0)),
                action.get("content", ""),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("edited", result, dry_run=bool(action.get("dry_run", False)))
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "convert_encoding_file":
            result = self.files.convert_encoding(
                action.get("path", ""),
                action.get("target_encoding", ""),
                source_encoding=action.get("source_encoding"),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("converted", result, dry_run=bool(action.get("dry_run", False)))
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "normalize_line_endings_file":
            result = self.files.normalize_line_endings(
                action.get("path", ""),
                action.get("newline", ""),
                dry_run=bool(action.get("dry_run", False)),
            )
            message = self._file_edit_message("normalized", result, dry_run=bool(action.get("dry_run", False)))
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "patch_file":
            result = self.files.patch(action.get("path", ""), action.get("diff", ""))
            message = f"Patched file {result.path}" if result.ok else result.error
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary=action.get("path", ""), detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

        if action_type == "patch_files":
            result = self.files.patch_files(action.get("diff", ""))
            message = f"Patched files:\n{result.content}" if result.ok else result.error
            self._record_tool_transcript(iteration=iteration, step_id=step_id, tool="files", action_type=str(action_type), success=result.ok, summary="multi-file patch", detail=message, error_type=None if result.ok else "file_error")
            return {"ok": result.ok, "message": message, "error_type": "file_error"}

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
            result = self.git.commit(action.get("message", "Agent commit"))
            return self._git_observation(iteration, step_id, str(action_type), action.get("message", "Agent commit"), result.stdout or result.error or "Committed.", result.ok)

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
            "write_file",
            "apply_patch",
            "search_replace_file",
            "insert_text_file",
            "delete_range_file",
            "delete_backward_file",
            "replace_range_file",
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
