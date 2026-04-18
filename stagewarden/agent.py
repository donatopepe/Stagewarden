from __future__ import annotations

from dataclasses import dataclass

from .caveman import CavemanDirective, CavemanManager, CavemanState
from .config import AgentConfig
from .executor import Executor
from .handoff import HandoffManager
from .ljson import dump_file
from .memory import MemoryStore
from .planner import Planner, PlanStep
from .prince2 import Prince2AgentPolicy
from .router import ModelRouter


@dataclass(slots=True)
class AgentResult:
    ok: bool
    steps_taken: int
    message: str


class Agent:
    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.base_system_prompt = config.system_prompt
        self.memory = self._load_memory()
        self.caveman = CavemanManager()
        self.caveman_state = self.caveman.load_state(config)
        self.trace_records: list[dict[str, object]] = []
        self.prince2 = Prince2AgentPolicy()
        self.router = ModelRouter()
        self.handoff = HandoffManager(timeout_seconds=config.model_timeout_seconds)
        self.planner = Planner()
        self.executor = Executor(
            config=config,
            router=self.router,
            handoff=self.handoff,
            memory=self.memory,
        )

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

        plan = self.planner.create_plan(effective_task)
        last_observation = "Task received."
        iterations = 0
        self.trace_records = []
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
                self._save_memory()
                self._trace(
                    phase="finish",
                    iteration=iterations - 1,
                    task=effective_task,
                    success=True,
                    prince2_stage_boundary=checklist.stage_boundary_review,
                    prince2_pid=pid.as_dict(),
                    plan_status=self._plan_status(plan),
                )
                self._save_trace()
                message = self._format_summary(plan, success=True)
                if directive.active:
                    message = self.caveman.format_text(message, directive.level)
                return AgentResult(True, iterations - 1, message)

            if self.config.verbose:
                print(f"[step {iterations}] {current.id} :: {current.title} [{current.status}]")

            if self.memory.should_abort_step(current.id):
                current.status = "failed"
                last_observation = "Aborted repeated loop for current step."
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

            outcome = self.executor.execute_step(
                task=effective_task,
                step=current,
                plan=plan,
                iteration=iterations,
                last_observation=last_observation,
                prince2_checklist=checklist,
            )

            if self.config.verbose:
                print(f"  model={outcome.model} action={outcome.action_type} ok={outcome.ok}")
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

        success = all(step.status == "completed" for step in plan)
        pid.status = "closed" if success else "exception"
        pid.outcome = "All planned stages completed." if success else "Run stopped before controlled closure."
        self._save_pid(pid)
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
        message = self._format_summary(plan, success=success)
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
        if not success:
            lines.append("Recent memory:")
            lines.append(self.memory.summarize())
        return "\n".join(lines)

    def _load_memory(self) -> MemoryStore:
        try:
            return MemoryStore.load(self.config.memory_path)
        except (OSError, ValueError, TypeError):
            return MemoryStore()

    def _save_memory(self) -> None:
        try:
            self.memory.save(self.config.memory_path)
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
                return AgentResult(True, 0, self.caveman.compress_file(directive.argument, self.config))
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

    def _trace(self, **record: object) -> None:
        self.trace_records.append(record)

    def _plan_status(self, plan: list[PlanStep]) -> str:
        return ",".join(f"{step.id}:{step.status}" for step in plan)
