from __future__ import annotations

import sys
from typing import TextIO

from .agent import Agent
from .config import AgentConfig

def _run_interactive_shell_impl(
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    from . import main as main_module

    globals().update(main_module.__dict__)
    source = input_stream or sys.stdin
    sink = output_stream or sys.stdout
    agent = _configure_agent_for_workspace(config)
    provider_limits = _provider_limit_status_report(agent, config)
    stream_enabled = True

    def apply_stream_callback(current_agent: Agent) -> None:
        if stream_enabled:
            current_agent.handoff.stream_callback = lambda chunk: (sink.write(chunk), sink.flush())
        else:
            current_agent.handoff.stream_callback = None

    apply_stream_callback(agent)
    config.permission_approver = _make_permission_approver(
        config=config,
        input_stream=source,
        output_stream=sink,
        get_agent=lambda: agent,
    )
    config.rate_limit_decider = _make_rate_limit_decider(input_stream=source, output_stream=sink)

    sink.write(f"Stagewarden interactive shell in {config.workspace_root}\n")
    sink.write("Type '/help' for commands. Any input without '/' is treated as a task.\n")
    if source is sys.stdin and sink is sys.stdout and _configure_readline(config):
        sink.write(f"History file: {config.history_path.name}\n")
    sink.flush()

    def _run_task(task: str) -> None:
        sink.write(f"Running task: {task}\n")
        sink.write(f"{_render_shell_progress(agent, phase='before', command=task)}\n")
        sink.flush()
        result = agent.run(task)
        sink.write("Agent result:\n")
        sink.write(f"{result.message}\n")
        sink.write(f"{_render_last_step_outcome(agent)}\n")
        sink.write(f"{_render_shell_progress(agent, phase='after')}\n")
        sink.flush()

    suspended_task = str(agent.project_handoff.task or "").strip()
    waiting_reason = str(getattr(agent.project_handoff, "waiting_reason", "") or "").strip().lower()
    if agent.project_handoff.status == "waiting" and suspended_task and waiting_reason != "clarification":
        sink.write(f"Auto-resuming suspended task: {suspended_task}\n")
        sink.flush()
        _run_task(suspended_task)
    elif agent.project_handoff.status == "waiting" and waiting_reason == "clarification":
        pending_question = agent.project_handoff.user_question.get("question") if isinstance(agent.project_handoff.user_question, dict) else None
        if pending_question:
            sink.write(f"Pending clarification: {pending_question}\n")
            sink.flush()

    while True:
        sink.write("stagewarden> ")
        sink.flush()
        line = source.readline()
        if line == "":
            sink.write("\n")
            sink.flush()
            return 0

        command = line.strip()
        if not command:
            continue
        legacy_shell_command = (
            not command.startswith(INTERACTIVE_COMMAND_PREFIX)
            and source is not sys.stdin
            and _is_known_interactive_command(command)
        )
        if not command.startswith(INTERACTIVE_COMMAND_PREFIX) and not legacy_shell_command:
            if agent.project_handoff.status == "waiting" and str(getattr(agent.project_handoff, "waiting_reason", "") or "").strip().lower() == "clarification":
                try:
                    agent.project_handoff.answer_user_question(answer=command)
                    agent.project_handoff.save(config.handoff_path)
                except ValueError as exc:
                    sink.write(f"{exc}\n")
                    sink.flush()
                    continue
                sink.write("Recorded answer for pending clarification.\n")
                sink.flush()
                if suspended_task:
                    _run_task(suspended_task)
                continue
            _run_task(command)
            continue
        shell_command = command[len(INTERACTIVE_COMMAND_PREFIX) :].strip() if command.startswith(INTERACTIVE_COMMAND_PREFIX) else command
        if not shell_command:
            sink.write("Command prefix detected but no command was provided. Use '/help'.\n")
            sink.flush()
            continue
        if shell_command in {"exit", "quit"}:
            sink.write("Session closed.\n")
            sink.flush()
            return 0
        if shell_command == "reset":
            config.session_permission_settings = None
            agent = _configure_agent_for_workspace(config)
            apply_stream_callback(agent)
            config.permission_approver = _make_permission_approver(
                config=config,
                input_stream=source,
                output_stream=sink,
                get_agent=lambda: agent,
            )
            sink.write("Session reset.\n")
            sink.flush()
            continue
        if shell_command in {"stream on", "stream off", "stream status"}:
            if shell_command == "stream status":
                sink.write(f"Model streaming is {'on' if stream_enabled else 'off'}.\n")
                sink.flush()
                continue
            stream_enabled = shell_command == "stream on"
            apply_stream_callback(agent)
            sink.write(f"Model streaming {'enabled' if stream_enabled else 'disabled'} for this session.\n")
            sink.flush()
            continue
        if shell_command == "slash choose" or shell_command.startswith("slash choose "):
            query = "" if shell_command == "slash choose" else shell_command.split(maxsplit=2)[2]
            sink.write(f"{_guided_slash_choice(config, query, input_stream=source, output_stream=sink)}\n")
            sink.flush()
            continue
        rewritten, immediate = _rewrite_shell_command(shell_command, agent)
        if immediate is not None:
            sink.write(f"{immediate}\n")
            sink.flush()
            continue
        shell_command = rewritten or shell_command
        model_message = _model_views._handle_model_command(shell_command, agent, config, input_stream=source, output_stream=sink)
        if model_message is not None:
            sink.write(f"{model_message}\n")
            sink.flush()
            continue
        account_message = _handle_account_command(shell_command, agent, config, input_stream=source, output_stream=sink)
        if account_message is not None:
            sink.write(f"{account_message}\n")
            sink.flush()
            continue
        project_brief_message = _handle_project_brief_command(shell_command, config)
        if project_brief_message is not None:
            sink.write(f"{project_brief_message}\n")
            sink.flush()
            continue
        if shell_command in {"project tree propose", "project tree propose --ai"}:
            use_ai = shell_command.endswith(" --ai")
            report = _project_tree_proposal_report(config, agent=agent, use_ai=use_ai)
            _record_project_tree_proposal_action(config, report, task=shell_command)
            sink.write(f"{_render_project_tree_proposal_report(report)}\n")
            sink.flush()
            continue
        if shell_command in {"project tree approve", "project tree approve --force"}:
            sink.write(f"{_render_project_tree_approval(config, force=shell_command.endswith(' --force'))}\n")
            sink.flush()
            continue
        role_message = _handle_role_command(shell_command, agent, config, input_stream=source, output_stream=sink)
        if role_message is not None:
            sink.write(f"{role_message}\n")
            sink.flush()
            continue
        sources_message = _handle_sources_command(shell_command, config)
        if sources_message is not None:
            sink.write(f"{sources_message}\n")
            sink.flush()
            continue
        update_message = _handle_update_command(shell_command, config)
        if update_message is not None:
            sink.write(f"{update_message}\n")
            sink.flush()
            continue
        extension_message = _handle_extension_command(shell_command, config)
        if extension_message is not None:
            sink.write(f"{extension_message}\n")
            sink.flush()
            continue
        external_io_message = _handle_external_io_command(
            shell_command,
            config,
            execute_external_io_command=_external_io_execute,
            record_handoff_action=_record_handoff_action,
        )
        if external_io_message is not None:
            sink.write(f"{external_io_message}\n")
            sink.flush()
            continue
        system_message = _handle_system_command(
            shell_command,
            config,
            execute_system_command=_system_execute,
            record_handoff_action=_record_handoff_action,
        )
        if system_message is not None:
            sink.write(f"{system_message}\n")
            sink.flush()
            continue
        mode_message = _handle_mode_command(shell_command, agent, config)
        if mode_message is not None:
            sink.write(f"{mode_message}\n")
            sink.flush()
            continue
        resume_message = _handle_resume_command(shell_command, agent, config)
        if resume_message is not None:
            sink.write(f"{resume_message}\n")
            sink.flush()
            continue
        git_message = _handle_git_command(shell_command, config)
        if git_message is not None:
            sink.write(f"{git_message}\n")
            sink.flush()
            continue
        file_message = _handle_file_command(shell_command, config)
        if file_message is not None:
            sink.write(f"{file_message}\n")
            sink.flush()
            continue
        shell_session_message = _handle_shell_session_command(shell_command, agent)
        if shell_session_message is not None:
            sink.write(f"{shell_session_message}\n")
            sink.flush()
            continue
        patch_message = _handle_patch_command(shell_command, agent)
        if patch_message is not None:
            sink.write(f"{patch_message}\n")
            sink.flush()
            continue
        sink.write(f"Unknown slash command: /{shell_command}\n")
        sink.write("Use '/help' for available commands or remove '/' to send a task to the agent.\n")
        sink.flush()


def run_interactive_shell(
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> int:
    from . import main as main_module

    globals().update(main_module.__dict__)
    return _run_interactive_shell_impl(config, input_stream=input_stream, output_stream=output_stream)
