from __future__ import annotations

import argparse
from pathlib import Path

from . import extension_views as _extension_views
from . import model_views as _model_views
from . import project_handoff_views as _project_handoff_views
from . import project_state_views as _project_state_views
from .project import tree_flow as _project_tree_flow
from . import shell_views as _shell_views
from . import status_dashboard_views as _status_dashboard_views
from . import status_views as _status_views


def _default_ljson_encode_path(source: Path, *, gzip_enabled: bool) -> Path:
    if gzip_enabled:
        return source.with_suffix(".ljson.gz")
    return source.with_suffix(".ljson")


def _default_ljson_decode_path(source: Path) -> Path:
    if source.suffix == ".gz":
        without_gzip = source.with_suffix("")
        return without_gzip.with_suffix(".json")
    return source.with_suffix(".json")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stagewarden", description="Stagewarden: production-grade CLI coding agent.")
    parser.add_argument("task", nargs="*", default=[], help='Task to execute, for example: stagewarden "fix the failing tests"')
    parser.add_argument("--max-steps", type=int, default=20, help="Maximum agent loop iterations.")
    parser.add_argument("--verbose", action="store_true", help="Print step-by-step logs.")
    parser.add_argument("--strict-ascii-output", dest="strict_ascii_output", action="store_true", default=True, help="Escape ambiguous non-ASCII characters in structured and generated text output.")
    parser.add_argument("--allow-unicode-output", dest="strict_ascii_output", action="store_false", help="Disable ASCII-safe escaping for generic file output.")
    parser.add_argument("--caveman", nargs="?", const="full", choices=["lite", "full", "ultra", "wenyan-lite", "wenyan", "wenyan-ultra"], help="Activate caveman mode at the selected level.")
    parser.add_argument("--caveman-commit", action="store_true", help="Generate a caveman-style commit message from the current diff.")
    parser.add_argument("--caveman-review", action="store_true", help="Generate one-line caveman review findings for the current diff.")
    parser.add_argument("--caveman-help", action="store_true", help="Show caveman commands and usage.")
    parser.add_argument("--caveman-compress", metavar="PATH", help="Compress a natural-language memory file and write a .original backup.")
    parser.add_argument("--ljson-encode", metavar="JSON_PATH", help="Encode a JSON array file to LJSON.")
    parser.add_argument("--ljson-decode", metavar="LJSON_PATH", help="Decode an LJSON file to JSON array.")
    parser.add_argument("--ljson-output", metavar="OUT_PATH", help="Output path for --ljson-encode/--ljson-decode.")
    parser.add_argument("--ljson-numeric", action="store_true", help="Use numeric-key LJSON representation when encoding.")
    parser.add_argument("--ljson-gzip", action="store_true", help="Write gzipped LJSON when encoding.")
    parser.add_argument("--ljson-benchmark", metavar="JSON_PATH", help="Benchmark standard JSON vs LJSON for a JSON array file.")
    parser.add_argument("--openrouter-benchmark", action="store_true", help="Run the live OpenRouter benchmark baseline and report accuracy by suite.")
    parser.add_argument("--openrouter-benchmark-output", metavar="OUT_PATH", help="Write the live OpenRouter benchmark report to a JSON file.")
    parser.add_argument("--openrouter-benchmark-history", metavar="HISTORY_PATH", help="Append a JSONL history snapshot and compare the current benchmark against the latest prior run.")
    parser.add_argument("--prince2-benchmark", action="store_true", help="Run the local PRINCE2 benchmark baseline and report accuracy by suite.")
    parser.add_argument("--prince2-benchmark-output", metavar="OUT_PATH", help="Write the local PRINCE2 benchmark report to a JSON file.")
    parser.add_argument("--interactive", action="store_true", help="Start an interactive Stagewarden shell.")
    parser.add_argument("--json", action="store_true", help="Emit JSON for machine-readable commands such as `doctor`.")
    parser.add_argument("--full", action="store_true", help="Show expanded status dashboard sections.")
    return parser


def run_cli() -> int:
    from . import main as main_module

    globals().update(main_module.__dict__)
    args = _build_parser().parse_args()
    config = AgentConfig(
        workspace_root=Path.cwd(),
        max_steps=args.max_steps,
        verbose=args.verbose,
        strict_ascii_output=args.strict_ascii_output,
    )
    config.shell_backend = _shell_views._configured_shell_backend(config)

    if args.ljson_encode:
        source = Path(args.ljson_encode)
        records = loads_text(read_text_utf8(source))
        if not isinstance(records, list):
            raise SystemExit("Input for --ljson-encode must be a JSON array.")
        target = Path(args.ljson_output) if args.ljson_output else _default_ljson_encode_path(source, gzip_enabled=args.ljson_gzip)
        dump_file(
            target,
            records,
            options=LJSONOptions(numeric_keys=args.ljson_numeric),
            gzip_enabled=args.ljson_gzip,
        )
        print(str(target))
        return 0

    if args.ljson_decode:
        source = Path(args.ljson_decode)
        records = load_file(source, gzipped=args.ljson_gzip or str(source).endswith(".gz"))
        target = Path(args.ljson_output) if args.ljson_output else _default_ljson_decode_path(source)
        write_text_utf8(target, dumps_ascii(records, indent=2))
        print(str(target))
        return 0

    if args.ljson_benchmark:
        records = loads_text(read_text_utf8(Path(args.ljson_benchmark)))
        if not isinstance(records, list):
            raise SystemExit("Input for --ljson-benchmark must be a JSON array.")
        print(
            dumps_ascii(
                _with_json_schema(
                    "ljson benchmark",
                    {
                        "command": "ljson benchmark",
                        "record_count": len(records),
                        "standard": benchmark_sizes(records),
                        "numeric": benchmark_sizes(records, numeric_keys=True),
                        "standard_gzip": benchmark_sizes(records, gzip_enabled=True),
                        "numeric_gzip": benchmark_sizes(records, numeric_keys=True, gzip_enabled=True),
                    },
                ),
                indent=2,
            )
        )
        return 0

    if args.openrouter_benchmark:
        report = run_openrouter_benchmark(history_path=args.openrouter_benchmark_history)
        rendered = dumps_ascii(_with_json_schema("openrouter benchmark", report), indent=2)
        if args.openrouter_benchmark_output:
            write_text_utf8(Path(args.openrouter_benchmark_output), rendered)
        print(rendered)
        return 0 if report.get("overall", {}).get("passed") else 1

    if args.prince2_benchmark:
        report = run_prince2_benchmark()
        rendered = dumps_ascii(_with_json_schema("prince2 benchmark", report), indent=2)
        if args.prince2_benchmark_output:
            write_text_utf8(Path(args.prince2_benchmark_output), rendered)
        print(rendered)
        return 0 if report.get("overall", {}).get("passed") else 1

    task = " ".join(args.task).strip()
    if args.caveman_help:
        task = "/caveman help"
    elif args.caveman_commit:
        task = "/caveman commit"
    elif args.caveman_review:
        task = "/caveman review"
    elif args.caveman_compress:
        task = f"/caveman compress {args.caveman_compress}"
    elif args.caveman:
        task = f"/caveman {args.caveman} {task}".strip()
    elif args.interactive or not task:
        return run_interactive_shell(config)
    if task in {"help", "help topics", "help --json", "help topics --json"}:
        if args.json or task.endswith("--json"):
            print(dumps_ascii(_with_json_schema("help", _help_json_report()), indent=2))
        else:
            print(interactive_help_text())
        return 0
    if task.startswith("help "):
        topic = task.split(maxsplit=1)[1]
        if topic == "--json":
            print(dumps_ascii(_with_json_schema("help", _help_json_report()), indent=2))
            return 0
        if topic.endswith(" --json"):
            raw_topic = topic[: -len(" --json")].strip()
            if raw_topic.lower() == "caveman":
                print(dumps_ascii(_with_json_schema("help", {"command": "help", "ok": True, "topic": "caveman", "title": "Caveman", "message": "Use `help caveman` for the rich caveman help surface."}), indent=2))
            else:
                print(dumps_ascii(_with_json_schema("help", _help_json_report(raw_topic)), indent=2))
            return 0
        if args.json:
            print(dumps_ascii(_with_json_schema("help", _help_json_report(topic)), indent=2))
        elif topic.lower() == "caveman":
            print(Agent(config=config).caveman.help_text())
        elif topic.lower() == "topics":
            print(interactive_help_text())
        else:
            print(interactive_help_text(topic))
        return 0
    if task in {"commands", "commands --json"}:
        if args.json or task == "commands --json":
            print(dumps_ascii(_with_json_schema("commands", {"command": "commands", "commands": command_catalog()}), indent=2))
        else:
            print(render_command_catalog())
        return 0
    if task == "slash choose" or task.startswith("slash choose "):
        query = "" if task == "slash choose" else task.split(maxsplit=2)[2]
        if args.json:
            report = _slash_palette_report(config, query)
            print(
                dumps_ascii(
                    _with_json_schema(
                        "slash choose",
                        {
                            "command": "slash choose",
                            "query": query,
                            "no_match": report["no_match"],
                            "message": report["message"],
                            "entries": report["entries"][:10],
                        },
                    ),
                    indent=2,
                )
            )
        else:
            print(_render_slash_choice_candidates(config, query))
        return 0
    if task == "slash" or task.startswith("slash "):
        prefix = "" if task == "slash" else task.split(maxsplit=1)[1]
        if prefix.endswith(" --json"):
            prefix = prefix[: -len(" --json")].strip()
        if args.json or task.endswith(" --json"):
            print(dumps_ascii(_with_json_schema("slash", _slash_palette_report(config, prefix)), indent=2))
        else:
            print(_render_slash_palette(config, prefix))
        return 0
    if task == "doctor":
        report = _status_dashboard_views._doctor_report(config)
        rendered = _status_dashboard_views._render_doctor(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("doctor", report), indent=2))
        else:
            print(rendered)
        return 0 if _status_dashboard_views._doctor_ok(rendered) else 1
    if task == "status":
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("status", _status_dashboard_views._status_dashboard_report(agent, config) if args.full else _status_views._status_report(agent, config)), indent=2))
        else:
            print(_status_views._render_status_full(agent, config) if args.full else _status_views._render_status(agent, config))
        return 0
    if task in {"status full", "status --full"}:
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("status", _status_dashboard_views._status_dashboard_report(agent, config)), indent=2))
        else:
            print(_status_views._render_status_full(agent, config))
        return 0
    if task == "prince2 benchmark":
        report = run_prince2_benchmark()
        rendered = dumps_ascii(_with_json_schema("prince2 benchmark", report), indent=2)
        print(rendered)
        return 0 if report.get("overall", {}).get("passed") else 1
    if task == "statusline":
        agent = _configure_readonly_agent_for_workspace(config)
        print(dumps_ascii(_with_json_schema("statusline", _status_dashboard_views._statusline_report(agent, config)), indent=2))
        return 0
    if task == "baseline":
        if args.json:
            print(dumps_ascii(_with_json_schema("baseline", _status_views._agent_baseline_report(config)), indent=2))
        else:
            print(_status_views._render_agent_baseline(config))
        return 0
    if task == "battery":
        if args.json:
            print(dumps_ascii(_with_json_schema("battery", _battery_views()._battery_report(config)), indent=2))
        else:
            print(_battery_views()._render_battery(config))
        return 0
    if task == "preflight":
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("preflight", _status_dashboard_views._preflight_report(agent, config)), indent=2))
        else:
            print(_status_dashboard_views._render_preflight(agent, config))
        return 0
    if task == "shell backend":
        if args.json:
            print(dumps_ascii(_with_json_schema("shell backend", _shell_views._shell_backend_report(config)), indent=2))
        else:
            print(_shell_views._render_shell_backend(config))
        return 0
    if task.startswith("shell backend use "):
        response = _handle_shell_command(task.split(), config)
        payload = _with_json_schema("shell backend use", {"command": "shell backend use", "message": response, "report": _shell_views._shell_backend_report(config)})
        if args.json:
            print(dumps_ascii(_with_json_schema("shell backend use", payload), indent=2))
        else:
            print(response)
        return 0
    if task.startswith("auth status "):
        provider = task.split(maxsplit=2)[2]
        if args.json:
            print(dumps_ascii(_with_json_schema("auth status", _auth_status_report(provider)), indent=2))
        else:
            print(_render_auth_status(provider))
        return 0
    if task == "overview":
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("overview", _status_views._overview_report(agent, config)), indent=2))
        else:
            print(_status_views._render_overview(agent, config))
        return 0
    if task == "health":
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("health", _status_views._health_report(agent, config)), indent=2))
        else:
            print(_status_views._render_health(agent, config))
        return 0
    if task == "report":
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("report", _status_dashboard_views._report_report(agent, config)), indent=2))
        else:
            print(_status_dashboard_views._render_report(agent, config))
        return 0
    if task == "models":
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("models", _status_views._model_status_report(agent, config)), indent=2))
        else:
            print(_status_views._render_model_status(agent, config))
        return 0
    if task in {"model limits", "models limits"}:
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("model limits", _model_limits_report(agent, config)), indent=2))
        else:
            print(_render_model_limits(agent, config))
        return 0
    if (
        task.startswith("model limit-record ")
        or task.startswith("account limit-record ")
        or task.startswith("model limit-clear ")
        or task.startswith("account limit-clear ")
    ):
        agent = _configure_readonly_agent_for_workspace(config)
        response = _handle_model_command(task, agent, config)
        if response is None:
            response = _handle_account_command(task, agent, config)
        schema_command = " ".join(task.split()[:2])
        payload = _with_json_schema(schema_command, {"command": schema_command, "message": response})
        if args.json:
            print(dumps_ascii(payload, indent=2))
        else:
            print(response or "No limit message recorded.")
        return 0 if response else 1
    if task == "catalog" or task.startswith("catalog "):
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            parts = task.split()
            if len(parts) == 1 or parts[1] == "status":
                print(dumps_ascii(_with_json_schema("catalog status", _catalog_status_report()), indent=2))
                return 0
            if parts[1] == "search":
                if len(parts) < 3:
                    print(dumps_ascii(_with_json_schema("catalog search", {"command": "catalog search", "ok": False, "error": _catalog_usage()}), indent=2))
                    return 1
                query_parts: list[str] = []
                provider = None
                feature = None
                for token in parts[2:]:
                    if token.startswith("provider=") and len(token) > len("provider="):
                        provider = token.split("=", 1)[1]
                        continue
                    if token.startswith("feature=") and len(token) > len("feature="):
                        feature = token.split("=", 1)[1]
                        continue
                    query_parts.append(token)
                query = " ".join(query_parts).strip()
                if not query and not provider and not feature:
                    print(dumps_ascii(_with_json_schema("catalog search", {"command": "catalog search", "ok": False, "error": _catalog_usage()}), indent=2))
                    return 1
                print(dumps_ascii(_with_json_schema("catalog search", _catalog_search_report(query, provider, feature=feature)), indent=2))
                return 0
            if parts[1] == "refresh":
                try:
                    include_artificial_analysis = _parse_catalog_refresh_flags(parts[2:])
                except ValueError:
                    print(dumps_ascii(_with_json_schema("catalog refresh", {"command": "catalog refresh", "ok": False, "error": _catalog_usage()}), indent=2))
                    return 1
                catalog = write_ai_models_catalog(include_artificial_analysis=include_artificial_analysis)
                catalog["include_artificial_analysis"] = include_artificial_analysis
                print(dumps_ascii(_with_json_schema("catalog refresh", _catalog_refresh_report(catalog)), indent=2))
                return 0
        response = _handle_model_command(task, agent, config)
        payload = _with_json_schema("catalog", {"command": task, "message": response})
        if args.json:
            print(dumps_ascii(payload, indent=2))
        else:
            print(response or _catalog_usage())
        return 0 if response else 1
    if task == "model inspect" or task.startswith("model inspect "):
        agent = _configure_readonly_agent_for_workspace(config)
        parts = task.split()
        if len(parts) not in {3, 4}:
            payload = _with_json_schema("model inspect", {"command": "model inspect", "ok": False, "error": "Usage: model inspect <provider> [provider_model]"})
            if args.json:
                print(dumps_ascii(_with_json_schema("model inspect", payload), indent=2))
            else:
                print(payload["error"])
            return 1
        provider = parts[2]
        provider_model = parts[3] if len(parts) == 4 else None
        try:
            report = _inspect_provider_models(agent, config, provider=provider, provider_model=provider_model)
        except ValueError as exc:
            payload = _with_json_schema("model inspect", {"command": "model inspect", "ok": False, "error": str(exc)})
            if args.json:
                print(dumps_ascii(_with_json_schema("model inspect", payload), indent=2))
            else:
                print(payload["error"])
            return 1
        if args.json:
            print(dumps_ascii(_with_json_schema("model inspect", report), indent=2))
        else:
            print(_render_provider_model_inspection(report))
        return 0
    if task.startswith("model "):
        agent = _configure_readonly_agent_for_workspace(config)
        response = _handle_model_command(task, agent, config)
        if response is None:
            print(_model_usage())
            return 1
        if args.json:
            print(dumps_ascii(_with_json_schema("model", {"command": task, "message": response, "models": _model_status_report(agent, config)}), indent=2))
        else:
            print(response)
        return 0
    if task == "accounts":
        if args.json:
            print(dumps_ascii(_with_json_schema("accounts", _accounts_report(config)), indent=2))
        else:
            print(_render_accounts(config))
        return 0
    if task == "roles":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles", _prince2_roles_report(config)), indent=2))
        else:
            print(_render_prince2_roles(config))
        return 0
    if task == "project brief":
        if args.json:
            print(dumps_ascii(_with_json_schema("project brief", _project_brief_report(config)), indent=2))
        else:
            print(_render_project_brief(config))
        return 0
    if task == "project design":
        agent = _configure_readonly_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("project design", _project_design_report(agent, config)), indent=2))
        else:
            print(_render_project_design(agent, config))
        return 0
    if task in {"project tree propose", "project tree propose --ai"}:
        use_ai = task.endswith(" --ai")
        agent = _configure_readonly_agent_for_workspace(config) if use_ai else None
        report = _project_tree_flow._project_tree_proposal_report(config, agent=agent, use_ai=use_ai)
        if use_ai and report.get("status") == "needs_clarification":
            report["clarification_question"] = _project_tree_flow._project_tree_clarification_record(
                config,
                gaps=list(report.get("clarification_gaps", [])) if isinstance(report.get("clarification_gaps"), list) else [],
            )
        _project_tree_flow._record_project_tree_proposal_action(config, report, task=task)
        if args.json:
            print(dumps_ascii(_with_json_schema("project tree propose", report), indent=2))
        else:
            print(_project_tree_flow._render_project_tree_proposal_report(report))
        return 0
    if task in {"project tree approve", "project tree approve --force"}:
        force = task.endswith(" --force")
        report = _project_tree_flow._approve_project_tree_proposal(config, force=force)
        if args.json:
            print(dumps_ascii(_with_json_schema("project tree approve", report), indent=2))
        else:
            print(_project_tree_flow._render_project_tree_approval_report(report, config))
        return 0 if report["status"] == "approved" else 1
    if task == "roles domains":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles domains", _prince2_role_domains_report()), indent=2))
        else:
            print(_render_prince2_role_domains())
        return 0
    if task == "roles tree":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles tree", _prince2_role_tree_report(config)), indent=2))
        else:
            print(_render_prince2_role_tree(config))
        return 0
    if task == "roles tree approve":
        agent = _configure_readonly_agent_for_workspace(config)
        response = _handle_role_command(task, agent, config)
        if args.json:
            print(dumps_ascii(_with_json_schema("roles tree approve", _prince2_role_tree_baseline_report(config)), indent=2))
        else:
            print(response)
        return 0
    if task == "roles baseline":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles baseline", _prince2_role_tree_baseline_report(config)), indent=2))
        else:
            print(_render_prince2_role_tree_baseline(config))
        return 0
    if task == "roles baseline matrix":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles baseline matrix", _prince2_role_tree_baseline_matrix_report(config)), indent=2))
        else:
            print(_render_prince2_role_tree_baseline_matrix(config))
        return 0
    if task.startswith("roles context "):
        node_id = task.split(maxsplit=2)[2]
        if args.json:
            print(dumps_ascii(_with_json_schema("roles context", _prince2_role_context_report(config, node_id)), indent=2))
        else:
            print(_render_prince2_role_context(config, node_id))
        return 0
    if task == "roles active":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles active", _prince2_role_active_report(config)), indent=2))
        else:
            print(_render_prince2_role_active(config))
        return 0
    if task == "goal" or task.startswith("goal "):
        report = _project_state_views.goal_command_report(task, config)
        if args.json:
            print(dumps_ascii(_with_json_schema("goal", report), indent=2))
        else:
            if report.get("ok") is False:
                print(report.get("error", "Goal command failed."))
            elif task == "goal":
                print(_project_state_views.render_goal_report(config))
            else:
                goal = report.get("goal", {})
                if isinstance(goal, dict):
                    print(f"Goal {goal.get('status', 'updated')}: {goal.get('objective', '') or 'none'}")
                else:
                    print("Goal updated.")
        return 0 if report.get("ok", True) else 1
    if task == "roles control":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles control", _prince2_role_control_report(config)), indent=2))
        else:
            print(_render_prince2_role_control(config))
        return 0
    if task == "roles queues":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles queues", _prince2_role_queue_report(config)), indent=2))
        else:
            print(_render_prince2_role_queues(config))
        return 0
    if task == "roles messages" or task.startswith("roles messages "):
        node_id = task.split(maxsplit=2)[2] if len(task.split(maxsplit=2)) == 3 else None
        if args.json:
            print(dumps_ascii(_with_json_schema("roles messages", _prince2_role_messages_report(config, node_id=node_id)), indent=2))
        else:
            print(_render_prince2_role_messages(config, node_id=node_id))
        return 0
    if task == "roles runtime":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles runtime", _prince2_role_runtime_report(config)), indent=2))
        else:
            print(_render_prince2_role_runtime(config))
        return 0
    if task == "roles tick" or task.startswith("roles tick "):
        max_nodes = None
        if task != "roles tick":
            try:
                max_nodes = int(task.split(maxsplit=2)[2])
            except (ValueError, IndexError):
                error_payload = _with_json_schema("roles tick", {"command": "roles tick", "ok": False, "error": "Usage: roles tick [max_nodes]"})
                if args.json:
                    print(dumps_ascii(_with_json_schema("roles tick", error_payload), indent=2))
                else:
                    print(error_payload["error"])
                return 1
        result = _tick_prince2_role_runtime(config, max_nodes=max_nodes)
        if args.json:
            print(
                dumps_ascii(
                    _with_json_schema(
                        "roles tick",
                    {
                        "command": "roles tick",
                        "ok": True,
                        "result": result,
                        "runtime": _prince2_role_runtime_report(config),
                        "messages": _prince2_role_messages_report(config),
                    },
                    ),
                    indent=2,
                )
            )
        else:
            print(
                f"Batch advanced PRINCE2 runtime: processed={result.get('processed')} "
                f"woken={result.get('woken')} progressed={result.get('progressed')} skipped={result.get('skipped')}.\n"
                + _render_prince2_role_runtime(config)
            )
        return 0
    if task == "roles check":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles check", _prince2_role_check_report(config)), indent=2))
        else:
            print(_render_prince2_role_check(config))
        return 0
    if task == "roles flow":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles flow", _prince2_role_flow_report()), indent=2))
        else:
            print(_render_prince2_role_flow())
        return 0
    if task == "roles matrix":
        if args.json:
            print(dumps_ascii(_with_json_schema("roles matrix", _prince2_role_matrix_report(config)), indent=2))
        else:
            print(_render_prince2_role_matrix(config))
        return 0
    if task.startswith("project brief "):
        response = _handle_project_brief_command(task, config)
        if response is None:
            print("Usage: project brief | project brief set <field> <value> | project brief clear [field]")
            return 1
        if args.json:
            schema_command = "project brief set" if task.startswith("project brief set") else "project brief clear" if task.startswith("project brief clear") else "project brief"
            print(dumps_ascii(_with_json_schema(schema_command, {"command": task, "message": response, "project_brief": _project_brief_report(config)}), indent=2))
        else:
            print(response)
        return 0
    if task in {"project start", "project start --ai"}:
        agent = _configure_readonly_agent_for_workspace(config)
        prefs = _model_views._load_model_preferences(config)
        report = _project_start_report(agent, config, prefs, force_ai=task.endswith("--ai"))
        if args.json:
            print(dumps_ascii(_with_json_schema("project start", report), indent=2))
        else:
            print(_render_project_start_report(report, agent, config, prefs))
        return 0 if report.get("ready") else 1
    if task.startswith("roles ") or task.startswith("role ") or task in {"project start", "project start --ai"}:
        agent = _configure_readonly_agent_for_workspace(config)
        response = _handle_role_command(task, agent, config)
        if response is None:
            print("Usage: project brief | project brief set <field> <value> | project brief clear [field] | roles | roles domains | roles context <node_id> | roles tree | roles tree approve | roles baseline | roles baseline matrix | roles runtime | roles active | roles control | roles queues | roles messages [node_id] | roles tick [max_nodes] | roles check | roles flow | roles matrix | roles propose | roles setup | role configure [role] | role clear <role> | role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> | role wait <node_id> reason=<text_with_underscores> | role wake <node_id> trigger=<name> | role tick <node_id> | project start [--ai]")
            return 1
        if args.json:
            if task.startswith("role message "):
                parts = task.split()
                node_id = parts[3] if len(parts) >= 4 else None
                print(
                    dumps_ascii(
                        _with_json_schema(
                            "roles messages",
                        {
                            "command": task,
                            "message": response,
                            "messages": _prince2_role_messages_report(config, node_id=node_id),
                        },
                        ),
                        indent=2,
                    )
                )
            elif task.startswith("role wait ") or task.startswith("role wake ") or task.startswith("role tick "):
                parts = task.split()
                node_id = parts[2] if len(parts) >= 3 else None
                print(
                    dumps_ascii(
                        _with_json_schema(
                            "roles runtime",
                        {
                            "command": task,
                            "message": response,
                            "runtime": _prince2_role_runtime_report(config),
                            "messages": _prince2_role_messages_report(config, node_id=node_id),
                        },
                        ),
                        indent=2,
                    )
                )
            elif task.startswith("roles tick"):
                print(
                    dumps_ascii(
                        _with_json_schema(
                            "roles tick",
                        {
                            "command": task,
                            "result": _tick_prince2_role_runtime(
                                config,
                                max_nodes=int(task.split(maxsplit=2)[2]) if len(task.split(maxsplit=2)) == 3 else None,
                            ),
                            "runtime": _prince2_role_runtime_report(config),
                            "messages": _prince2_role_messages_report(config),
                        },
                        ),
                        indent=2,
                    )
                )
            else:
                print(dumps_ascii(_with_json_schema("roles", {"command": task, "message": response, "roles": _prince2_roles_report(config)}), indent=2))
        else:
            print(response)
        return 1 if task.startswith("project start") and not _project_start_ready(config) else 0
    if task in {"sources", "sources status"} or task.startswith("sources "):
        if args.json:
            if task == "sources update":
                report = _with_json_schema("sources update", _sources_update_report(config))
                print(dumps_ascii(_with_json_schema("sources update", report), indent=2))
                return 0 if report.get("ok") else 1
            if task in {"sources", "sources status", "sources status --strict"}:
                strict = task == "sources status --strict"
                report = _with_json_schema("sources status", _sources_status_report(config, strict=strict))
                print(dumps_ascii(_with_json_schema("sources status", report), indent=2))
                return 0 if not strict or report.get("ok") else 1
            print(dumps_ascii(_with_json_schema("sources status", {"command": task, "ok": False, "error": "Usage: sources | sources status [--strict] | sources update"}), indent=2))
            return 1
        response = _handle_sources_command(task, config)
        if response is None or response.startswith("Usage:"):
            print(response or "Usage: sources | sources status [--strict] | sources update")
            return 1
        print(response)
        return 0 if task != "sources status --strict" or _sources_status_report(config, strict=True).get("ok") else 1
    if task in {"update status", "update check", "update check --json", "update apply", "update apply --yes"} or task.startswith("update "):
        if args.json or task == "update check --json":
            if task in {"update status"}:
                report = _with_json_schema("update status", _update_status_report(config))
            elif task in {"update check", "update check --json"}:
                report = _with_json_schema("update check", _update_status_report(config, fetch=True))
            elif task in {"update apply", "update apply --yes"}:
                report = _with_json_schema("update apply", _update_apply_report(config, confirmed=task.endswith(" --yes")))
            else:
                report = _with_json_schema("update", {"command": task, "ok": False, "error": "Usage: update status | update check [--json] | update apply --yes"})
            print(dumps_ascii(_with_json_schema((report or {}).get("command", "update"), report), indent=2))
            return 0 if report.get("ok") else 1
        response = _handle_update_command(task, config)
        if response is None or response.startswith("Usage:"):
            print(response or "Usage: update status | update check [--json] | update apply --yes")
            return 1
        print(response)
        return 0 if "\n- ok: false" not in response else 1
    if task == "extensions" or task.startswith("extension ") or task.startswith("extensions "):
        if args.json:
            if task == "extensions":
                report = _with_json_schema("extensions", _extension_views.discover_extensions(config.workspace_root))
            elif task.startswith("extension scaffold "):
                try:
                    report = _with_json_schema("extensions", _extension_views.scaffold_extension(config.workspace_root, task.split(maxsplit=2)[2]))
                    _project_handoff_views._record_handoff_action(
                        config,
                        phase="extension_scaffold",
                        task=task,
                        summary=f"Created extension scaffold {report['name']}.",
                        details=report,
                    )
                except ValueError as exc:
                    report = {"command": "extension scaffold", "ok": False, "error": str(exc)}
            else:
                report = {"command": task, "ok": False, "error": "Usage: extensions | extension scaffold <name>"}
            print(dumps_ascii(_with_json_schema("extensions", report), indent=2))
            if task == "extensions":
                return 0
            return 0 if report.get("ok") else 1
        response = _handle_extension_command(task, config)
        if response is None or response.startswith("Usage:") or response.startswith("Extension scaffold failed"):
            print(response or "Usage: extensions | extension scaffold <name>")
            return 1
        print(response)
        return 0
    if task.startswith("file "):
        report = _file_command_report(task, config)
        if args.json:
            schema_command = (report or {}).get("command", "file")
            if schema_command not in {"file inspect", "file stat", "file copy", "file move", "file delete", "file chmod", "file chown"}:
                schema_command = "file"
            print(dumps_ascii(_with_json_schema(schema_command, report or {"command": task, "ok": False, "error": "Unsupported file command"}), indent=2))
            return 0 if report and report.get("ok") else 1
        response = _handle_file_command(task, config)
        print(response or "Usage: file inspect <path> | file stat <path> | file copy <source> <destination> [--overwrite] [--dry-run] | file move <source> <destination> [--overwrite] [--dry-run] | file delete <path> [--recursive] [--dry-run] | file chmod <path> <mode> [--recursive] [--dry-run] | file chown <path> <user> [group] [--recursive] [--dry-run]")
        return 0 if report and report.get("ok") else 1
    if (
        task.startswith("web search ")
        or task.startswith("download ")
        or task.startswith("checksum ")
        or task.startswith("compress ")
        or task.startswith("archive verify ")
        or task in {"download", "checksum", "compress", "archive", "web"}
    ):
        if args.json:
            report = _external_io_report(
                task,
                config,
                execute_external_io_command=_external_io_execute,
                record_handoff_action=_project_handoff_views._record_handoff_action,
            )
            schema_command = (report or {}).get("command", "external_io")
            if schema_command not in {"web search", "download", "checksum", "compress", "archive verify"}:
                schema_command = "external_io"
            print(dumps_ascii(_with_json_schema(schema_command, report or {"command": task, "ok": False, "error": "Unsupported external IO command"}), indent=2))
            return 0 if report and report.get("ok") else 1
        response = _handle_external_io_command(
            task,
            config,
            execute_external_io_command=_external_io_execute,
            record_handoff_action=_project_handoff_views._record_handoff_action,
        )
        print(response or "Usage: web search <query> | download <url> [path] [--max-bytes N] | checksum <path> | compress <path> [target.gz] | archive verify <path.gz>")
        return 0 if response and ": OK " in response else 1
    if task == "permissions":
        if args.json:
            print(
                dumps_ascii(
                    _with_json_schema("permissions", {"command": "permissions", "report": _permissions_report(config)}),
                    indent=2,
                )
            )
        else:
            print(_render_permissions(config))
        return 0
    if task in {"board", "stage review"}:
        if args.json:
            print(dumps_ascii(_with_json_schema("board", _board_report(config)), indent=2))
        else:
            print(_render_board(config))
        return 0
    if task in {"sessions", "session list"}:
        agent = _configure_agent_for_workspace(config)
        if args.json:
            print(dumps_ascii(_with_json_schema("sessions", _shell_sessions_report(agent)), indent=2))
        else:
            shell_session_message = _handle_shell_session_command(task, agent)
            print(shell_session_message or "No active shell sessions.")
        return 0
    if task.startswith("git "):
        if args.json:
            report = _git_command_report(task, config)
            schema_command = (report or {}).get("command", "git")
            if schema_command not in {"git status", "git log", "git history", "git show"}:
                schema_command = "git"
            print(dumps_ascii(_with_json_schema(schema_command, report or {"command": task, "ok": False, "error": "Unsupported git command"}), indent=2))
            return 0 if report and report.get("ok") else 1
        else:
            git_message = _handle_git_command(task, config)
            if git_message is not None:
                print(git_message)
            else:
                print("Usage: git status | git log [limit] | git history <path> [limit] | git show [--stat] [revision]")
        return 0
    if task == "boundary":
        if args.json:
            print(dumps_ascii(_with_json_schema("boundary", _boundary_report(config)), indent=2))
        else:
            print(_render_boundary(config))
        return 0
    if task == "risks" or task.startswith("risks close"):
        if task.startswith("risks close"):
            resolution = task.partition("close")[2].strip() or "Resolved by explicit mitigation and wet-run validation."
            if args.json:
                print(dumps_ascii(_with_json_schema("risks", _risks_close_report(config, resolution)), indent=2))
            else:
                print(_render_risks_close(config, resolution))
            return 0
        if args.json:
            print(dumps_ascii(_with_json_schema("risks", _risks_report(config)), indent=2))
        else:
            print(_render_risks(config))
        return 0
    if task == "issues" or task.startswith("issues close"):
        if task.startswith("issues close"):
            resolution = task.partition("close")[2].strip() or "Resolved by explicit corrective action and wet-run validation."
            if args.json:
                print(dumps_ascii(_with_json_schema("issues", _issues_close_report(config, resolution)), indent=2))
            else:
                print(_render_issues_close(config, resolution))
            return 0
        if args.json:
            print(dumps_ascii(_with_json_schema("issues", _issues_report(config)), indent=2))
        else:
            print(_render_issues(config))
        return 0
    if task == "quality" or task.startswith("quality close"):
        if task.startswith("quality close"):
            resolution = task.partition("close")[2].strip() or "Accepted by explicit validation and wet-run evidence."
            if args.json:
                print(dumps_ascii(_with_json_schema("quality", _quality_close_report(config, resolution)), indent=2))
            else:
                print(_render_quality_close(config, resolution))
            return 0
        if args.json:
            print(dumps_ascii(_with_json_schema("quality", _quality_report(config)), indent=2))
        else:
            print(_render_quality(config))
        return 0
    if task == "exception":
        if args.json:
            print(dumps_ascii(_with_json_schema("exception", _exception_report(config)), indent=2))
        else:
            print(_render_exception(config))
        return 0
    if task == "lessons":
        if args.json:
            print(dumps_ascii(_with_json_schema("lessons", _lessons_report(config)), indent=2))
        else:
            print(_render_lessons(config))
        return 0
    if task == "todo":
        if args.json:
            print(dumps_ascii(_with_json_schema("todo", _todo_report(config)), indent=2))
        else:
            print(_render_todo(config))
        return 0
    if task in {"transcript", "trace"}:
        if args.json:
            print(dumps_ascii(_with_json_schema("transcript", _transcript_report(config)), indent=2))
        else:
            print(_render_transcript(config))
        return 0
    if task == "handoff":
        if args.json:
            print(dumps_ascii(_with_json_schema("handoff", _handoff_report(config)), indent=2))
        else:
            print(_render_handoff(config))
        return 0
    if task == "handoff actions" or task.startswith("handoff actions "):
        parts = task.split()
        limit = _parse_optional_limit(parts)
        if args.json:
            print(dumps_ascii(_with_json_schema("handoff", _handoff_actions_report(config, limit=limit)), indent=2))
        else:
            print(_render_handoff_actions(config, limit=limit))
        return 0
    if task in {"handoff export", "handoff md"}:
        if args.json:
            print(dumps_ascii(_with_json_schema("handoff", _export_handoff_markdown_report(config)), indent=2))
        else:
            print(_export_handoff_markdown(config))
        return 0
    if task == "resume --show":
        if args.json:
            print(dumps_ascii(_with_json_schema("resume --show", _resume_show_report(config)), indent=2))
        else:
            print(_render_resume_show(config))
        return 0
    if task == "resume context":
        if args.json:
            print(dumps_ascii(_with_json_schema("resume context", _resume_context_payload(config)), indent=2))
        else:
            print(_render_resume_context(config))
        return 0
    if task == "resume --clear":
        if args.json:
            print(dumps_ascii(_with_json_schema("resume --clear", _archive_and_clear_handoff_report(config)), indent=2))
        else:
            print(_archive_and_clear_handoff(config))
        return 0
    if task in {"models usage", "cost"}:
        if args.json:
            print(dumps_ascii(_with_json_schema("models usage", _model_usage_report(config)), indent=2))
        else:
            print(_render_model_usage(config))
        return 0

    agent = _configure_agent_for_workspace(config)
    result = agent.run(task)
    print(result.message)
    return 0 if result.ok else 1
