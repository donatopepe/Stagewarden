from __future__ import annotations

from dataclasses import dataclass

from .caveman import CavemanDirective, CavemanManager, CavemanState
from .config import AgentConfig
from .executor import Executor
from .handoff import HandoffManager
from .ljson import dump_file
from .memory import MemoryStore
from .modelprefs import ModelPreferences
from .planner import Planner, PlanStep
from .prince2 import Prince2AgentPolicy
from .project_handoff import ProjectHandoff
from .router import ModelRouter
from .tools.git import GitTool


@dataclass(slots=True)
class AgentResult:
    ok: bool
    steps_taken: int
    message: str


class Agent:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.base_system_prompt = config.system_prompt
        self.git = GitTool(config)
        self._ensure_git_governance()
        self.memory = self._load_memory()
        self.caveman = CavemanManager()
        self.caveman_state = self.caveman.load_state(config)
        self.trace_records: list[dict[str, object]] = []
        self.prince2 = Prince2AgentPolicy()
        self.router = ModelRouter()
        self.handoff = HandoffManager(timeout_seconds=config.model_timeout_seconds)
        self.planner = Planner()
        self.project_handoff = self._load_handoff()
        self.executor = Executor(
            config=config,
            router=self.router,
            handoff=self.handoff,
            memory=self.memory,
            project_handoff=self.project_handoff,
        )
        self._apply_workspace_model_preferences()

    def run(self, task: str) -> AgentResult:
        self.executor.config.system_prompt = self.base_system_prompt
        directive = self.caveman.parse(task)
        special = self._handle_caveman_command(directive)
        if special is not None:
            return special
        directive = self._merge_caveman_state(directive, task)

        effective_task = directive.stripped_task or task
        checklist = self.prince2.build_checklist(effective_task)
        assessment = self.prince2.assess_task(effective_task, checklist)
        pid = self.prince2.build_pid(effective_task, checklist)
        if directive.active:
            self.executor.config.system_prompt = self.caveman.augment_system_prompt(
                self.base_system_prompt,
                directive.level,
            )
        self.executor.config.system_prompt = (
            f"{self.executor.config.system_prompt}\n\nPRINCE2 agent policy:\n{checklist.render_for_prompt()}"
        )

        plan = self.planner.create_plan(effective_task, project_handoff=self.project_handoff)
        last_observation = "Task received."
        iterations = 0
        self.trace_records = []
        start_head = self._git_head()
        self.project_handoff.start_run(
            task=effective_task,
            plan_status=self._plan_status(plan),
            git_head=start_head,
        )
        self.project_handoff.record_plan(
            task=effective_task,
            plan_status=self._plan_status(plan),
            checklist=checklist.as_dict(),
            git_head=start_head,
        )
        self._save_handoff()
        self._trace(
            phase="start",
            iteration=0,
            task=effective_task,
            caveman_active=directive.active,
            caveman_level=directive.level if directive.active else None,
            prince2_checklist=checklist.as_dict(),
            prince2_assessment=assessment.as_dict(),
            prince2_pid=pid.as_dict(),
            plan_status=self._plan_status(plan),
        )
        self._save_pid(pid)

        if not assessment.allowed:
            pid.status = "rejected"
            pid.outcome = "Rejected by PRINCE2 governance gate before execution."
            self._save_pid(pid)
            self.project_handoff.close_run(
                task=effective_task,
                success=False,
                plan_status=self._plan_status(plan),
                git_head=self._git_head(),
                outcome="Task rejected by PRINCE2 governance gate before execution.",
            )
            self._save_handoff()
            self._save_memory()
            self._trace(
                phase="finish",
                iteration=0,
                task=effective_task,
                success=False,
                prince2_exception="task rejected before execution",
                prince2_assessment=assessment.as_dict(),
                prince2_pid=pid.as_dict(),
                plan_status=self._plan_status(plan),
            )
            self._save_trace()
            message = "Task rejected by PRINCE2 governance gate.\n" + "\n".join(f"- {item}" for item in assessment.reasons)
            if directive.active:
                message = self.caveman.format_text(message, directive.level)
            return AgentResult(False, 0, message)

        for iterations in range(1, self.config.max_steps + 1):
            current = self._next_pending_step(plan)
            if current is None:
                success = all(step.status == "completed" for step in plan)
                if success:
                    self.project_handoff.finalize_quality_register(
                        resolution="project closed with controlled completion",
                    )
                    self.project_handoff.close_all_open_risks(
                        resolution="project closed with controlled completion",
                    )
                    self.project_handoff.close_all_open_issues(
                        resolution="project closed with controlled completion",
                    )
                    self.project_handoff.clear_exception_plan_if_recovered()
                pid.status = "closed" if success else "exception"
                pid.outcome = "All planned stages completed." if success else "Run stopped before controlled closure."
                self._save_pid(pid)
                self.project_handoff.close_run(
                    task=effective_task,
                    success=success,
                    plan_status=self._plan_status(plan),
                    git_head=self._git_head(),
                    outcome=pid.outcome,
                )
                self._save_handoff()
                self._save_memory()
                self._trace(
                    phase="finish",
                    iteration=iterations - 1,
                    task=effective_task,
                    success=success,
                    prince2_stage_boundary=checklist.stage_boundary_review,
                    prince2_pid=pid.as_dict(),
                    plan_status=self._plan_status(plan),
                )
                self._save_trace()
                git_result = self._git_snapshot("stagewarden: complete agent run")
                message = self._format_summary(plan, success=success)
                if git_result:
                    message = f"{message}\n{git_result}"
                if directive.active:
                    message = self.caveman.format_text(message, directive.level)
                return AgentResult(success, iterations - 1, message)

            if self.config.verbose:
                print(f"[step {iterations}] {current.id} :: {current.title} [{current.status}]")

            if self.memory.should_abort_step(current.id):
                current.status = "failed"
                last_observation = "Aborted repeated loop for current step."
                self.project_handoff.record_issue(
                    step_id=current.id,
                    severity="high",
                    summary="Repeated loop exceeded acceptable control tolerance.",
                )
                self.project_handoff.record_lesson(
                    step_id=current.id,
                    lesson_type="failure",
                    lesson="Repeated loop indicates the current stage needs a revised control approach or exception plan.",
                )
                self.project_handoff.begin_step(
                    iteration=iterations,
                    task=effective_task,
                    step_id=current.id,
                    step_title=current.title,
                    step_status=current.status,
                    git_head=self._git_head(),
                )
                self.project_handoff.complete_step(
                    iteration=iterations,
                    task=effective_task,
                    step_id=current.id,
                    step_title=current.title,
                    step_status=current.status,
                    model="none",
                    action_type="abort_step",
                    observation=last_observation,
                    git_head=self._git_head(),
                )
                self._save_handoff()
                self._trace(
                    phase="abort_step",
                    iteration=iterations,
                    task=effective_task,
                    step_id=current.id,
                    step_title=current.title,
                    observation=last_observation,
                    prince2_exception="repeated loop exceeded acceptable control tolerance",
                    prince2_pid=pid.as_dict(),
                    plan_status=self._plan_status(plan),
                )
                continue

            self.project_handoff.begin_step(
                iteration=iterations,
                task=effective_task,
                step_id=current.id,
                step_title=current.title,
                step_status=current.status,
                git_head=self._git_head(),
            )
            self._save_handoff()
            outcome = self.executor.execute_step(
                task=effective_task,
                step=current,
                plan=plan,
                iteration=iterations,
                last_observation=last_observation,
                prince2_checklist=checklist,
            )

            if self.config.verbose:
                account_text = outcome.account or "-"
                variant_text = outcome.variant or "provider-default"
                head_before = outcome.git_head_before or "unknown"
                head_after = outcome.git_head_after or "unknown"
                print(
                    "  "
                    f"model={outcome.model} variant={variant_text} account={account_text} "
                    f"action={outcome.action_type} ok={outcome.ok}"
                )
                print(f"  git_head_before={head_before}")
                print(f"  git_head_after={head_after}")
                print(f"  observation={outcome.observation[:300]}")

            last_observation = outcome.observation
            if outcome.step_completed:
                current.status = "completed"
            elif outcome.ok:
                current.status = "in_progress"
            else:
                if (
                    self.memory.failure_count(current.id) >= self.config.max_retries_per_step
                    and outcome.model == "claude"
                ):
                    current.status = "failed"
                else:
                    current.status = "in_progress"
            if outcome.ok:
                self.project_handoff.record_quality(
                    step_id=current.id,
                    status="passed" if outcome.step_completed else "observed",
                    evidence=outcome.observation,
                )
                self.project_handoff.record_lesson(
                    step_id=current.id,
                    lesson_type="success" if outcome.step_completed else "observation",
                    lesson=outcome.observation,
                )
                if outcome.step_completed:
                    self.project_handoff.close_issues_for_step(
                        step_id=current.id,
                        resolution="step completed with wet-run evidence",
                    )
                    self.project_handoff.clear_exception_plan_if_recovered()
            else:
                severity = "high" if current.status == "failed" else "medium"
                self.project_handoff.record_issue(
                    step_id=current.id,
                    severity=severity,
                    summary=outcome.observation,
                )
                self.project_handoff.record_lesson(
                    step_id=current.id,
                    lesson_type="failure",
                    lesson=outcome.observation,
                )
            self.project_handoff.complete_step(
                iteration=iterations,
                task=effective_task,
                step_id=current.id,
                step_title=current.title,
                step_status=current.status,
                model=outcome.model,
                action_type=outcome.action_type,
                observation=outcome.observation,
                git_head=self._git_head(),
            )
            self._trace(
                phase="step_result",
                iteration=iterations,
                task=effective_task,
                step_id=current.id,
                step_title=current.title,
                step_status=current.status,
                model=outcome.model,
                action_type=outcome.action_type,
                success=outcome.ok,
                step_completed=outcome.step_completed,
                error_type=outcome.error_type,
                observation=outcome.observation[:1000],
                prince2_assessment=outcome.prince2_assessment,
                prince2_stage_boundary=checklist.stage_boundary_review,
                prince2_pid=pid.as_dict(),
                plan_status=self._plan_status(plan),
            )
            self._save_memory()
            snapshot_message = self._git_snapshot(f"stagewarden: step {current.id} {current.status}")
            if snapshot_message:
                self.project_handoff.record_git_snapshot(
                    iteration=iterations,
                    task=effective_task,
                    message=snapshot_message,
                    git_head=self._git_head(),
                )
            self._save_handoff()

        success = all(step.status == "completed" for step in plan)
        pid.status = "closed" if success else "exception"
        pid.outcome = "All planned stages completed." if success else "Run stopped before controlled closure."
        self._save_pid(pid)
        self.project_handoff.close_run(
            task=effective_task,
            success=success,
            plan_status=self._plan_status(plan),
            git_head=self._git_head(),
            outcome=pid.outcome or "",
        )
        self._save_handoff()
        self._save_memory()
        self._trace(
            phase="finish",
            iteration=iterations,
            task=effective_task,
            success=success,
            prince2_closure=checklist.closure_criteria,
            prince2_pid=pid.as_dict(),
            plan_status=self._plan_status(plan),
        )
        self._save_trace()
        git_result = self._git_snapshot("stagewarden: finish agent run")
        message = self._format_summary(plan, success=success)
        if git_result:
            message = f"{message}\n{git_result}"
        if directive.active:
            message = self.caveman.format_text(message, directive.level)
        return AgentResult(success, iterations, message)

    def _next_pending_step(self, plan: list[PlanStep]) -> PlanStep | None:
        for step in plan:
            if step.status in {"pending", "in_progress"}:
                return step
        return None

    def _format_summary(self, plan: list[PlanStep], *, success: bool) -> str:
        lines = ["Agent run completed." if success else "Agent run stopped before completion."]
        for step in plan:
            lines.append(f"- {step.id}: {step.status} :: {step.title}")
        lines.append(self.project_handoff.rendered_operational_posture())
        lines.append("Stage boundary:")
        lines.append(self.project_handoff.rendered_stage_view())
        if not success:
            lines.append("Recent memory:")
            lines.append(self.memory.summarize())
        return "\n".join(lines)

    def _load_memory(self) -> MemoryStore:
        try:
            return MemoryStore.load(self.config.memory_path)
        except (OSError, ValueError, TypeError):
            return MemoryStore()

    def _apply_workspace_model_preferences(self) -> None:
        try:
            prefs = ModelPreferences.load(self.config.model_prefs_path)
        except (OSError, ValueError, TypeError):
            return
        self.router.configure(
            enabled_models=prefs.enabled_models,
            preferred_model=prefs.preferred_model,
            blocked_until_by_model=prefs.blocked_until_by_model or {},
        )
        self.handoff.account_env_by_target = dict(prefs.env_var_by_account or {})
        self.handoff.model_variant_by_model = dict(prefs.variant_by_model or {})

    def _load_handoff(self) -> ProjectHandoff:
        try:
            return ProjectHandoff.load(self.config.handoff_path)
        except (OSError, ValueError, TypeError):
            return ProjectHandoff()

    def _save_memory(self) -> None:
        try:
            self.memory.save(self.config.memory_path)
        except OSError:
            pass

    def _save_handoff(self) -> None:
        try:
            self.project_handoff.save(self.config.handoff_path)
        except OSError:
            pass

    def _handle_caveman_command(self, directive: CavemanDirective) -> AgentResult | None:
        if directive.command == "help":
            return AgentResult(True, 0, self.caveman.help_text())
        if directive.command == "deactivate":
            self.caveman_state = CavemanState(active=False, level="full")
            self.caveman.clear_state(self.config)
            return AgentResult(True, 0, "Caveman mode disabled.")
        if directive.command == "compress":
            if not directive.argument:
                return AgentResult(False, 0, "Missing file path for caveman compress.")
            try:
                message = self.caveman.compress_file(directive.argument, self.config)
                git_message = self._git_snapshot("stagewarden: caveman compress")
                return AgentResult(True, 0, f"{message}\n{git_message}" if git_message else message)
            except (OSError, ValueError) as exc:
                return AgentResult(False, 0, str(exc))
        if directive.command == "commit":
            return self._run_caveman_commit()
        if directive.command == "review":
            return self._run_caveman_review()
        if directive.command == "activate" and not directive.stripped_task:
            self.caveman_state = CavemanState(active=True, level=directive.level)
            self.caveman.save_state(self.config, self.caveman_state)
            return AgentResult(True, 0, f"Caveman mode active. Level: {directive.level}.")
        return None

    def _merge_caveman_state(self, directive: CavemanDirective, task: str) -> CavemanDirective:
        if directive.command == "deactivate":
            return directive
        if directive.active and directive.command in {None, "activate"}:
            self.caveman_state = CavemanState(active=True, level=directive.level)
            self.caveman.save_state(self.config, self.caveman_state)
            return directive
        if self.caveman_state.active:
            return CavemanDirective(
                active=True,
                level=self.caveman_state.level,
                stripped_task=task,
                command=None,
                argument=None,
            )
        return directive

    def _run_caveman_commit(self) -> AgentResult:
        diff = self.executor.git.diff(staged=True)
        if not diff.ok or not diff.stdout:
            diff = self.executor.git.diff()
        if not diff.ok or not diff.stdout:
            return AgentResult(False, 0, diff.error or "No diff available for caveman commit.")
        result = self.handoff.invoke(
            model="cheap",
            prompt=(
                "Generate terse commit message for current diff. Conventional Commits. "
                "Subject <=50 chars. Lowercase after type. Why over what. No period on subject.\n\n"
                f"{diff.stdout[:12000]}"
            ),
        )
        return AgentResult(result.ok, 0, (result.output or result.error).strip())

    def _run_caveman_review(self) -> AgentResult:
        diff = self.executor.git.diff()
        if not diff.ok or not diff.stdout:
            return AgentResult(False, 0, diff.error or "No diff available for caveman review.")
        result = self.handoff.invoke(
            model="cheap",
            prompt=(
                "Review current code changes. One-line per finding. Format: "
                "L<line>: <severity> <problem>. <fix>. Severity: bug, risk, nit, q. "
                "Skip praise. If code good, say LGTM.\n\n"
                f"{diff.stdout[:12000]}"
            ),
        )
        return AgentResult(result.ok, 0, (result.output or result.error).strip())

    def trace_as_ljson(self) -> dict[str, object]:
        from .ljson import encode

        return encode(self.trace_records)

    def _save_trace(self) -> None:
        try:
            dump_file(self.config.trace_path, self.trace_records)
        except OSError:
            pass

    def _save_pid(self, pid: object) -> None:
        try:
            pid.save(self.config.prince2_pid_path)
        except OSError:
            pass

    def _ensure_git_governance(self) -> None:
        if not self.config.enforce_git:
            return
        ready = self.git.ensure_ready()
        if not ready.ok:
            raise RuntimeError(ready.error or "Git prerequisite failed.")
        if self.config.auto_git_commit:
            baseline = self.git.commit_if_changed("stagewarden: initialize workspace")
            if not baseline.ok:
                raise RuntimeError(baseline.error or "Git baseline commit failed.")

    def _git_snapshot(self, message: str) -> str:
        if not self.config.enforce_git or not self.config.auto_git_commit:
            return ""
        result = self.git.commit_if_changed(message)
        if result.ok:
            if "No changes" in result.stdout:
                return ""
            return f"Git snapshot: {result.stdout.splitlines()[-1] if result.stdout else message}"
        return f"Git snapshot failed: {result.error}"

    def _git_head(self) -> str | None:
        result = self.git.head()
        if result.ok and result.stdout:
            return result.stdout.strip()
        return None

    def _trace(self, **record: object) -> None:
        self.trace_records.append(record)

    def _plan_status(self, plan: list[PlanStep]) -> str:
        return ",".join(f"{step.id}:{step.status}" for step in plan)
