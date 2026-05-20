from __future__ import annotations

from typing import TextIO

from ..agent import Agent
from ..config import AgentConfig
from ..modelprefs import ModelPreferences, PRINCE2_ROLE_IDS, PRINCE2_ROLE_LABELS
from .. import model_views as _model_views
from .. import project_handoff_views as _project_handoff_views
from . import role_flow as _project_role_flow
from . import role_runtime_views as _project_role_runtime_views
from . import role_views as _project_role_views
from . import role_tree_views as _project_role_tree_views
from . import start_flow as _project_start_flow


def _handle_project_and_roles_command(
    command: str,
    agent: Agent,
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] == "project" and parts[1:2] == ["start"] and len(parts) in {2, 3}:
        if len(parts) == 3 and parts[2] != "--ai":
            return "Usage: project start [--ai]"
        prefs = _model_views._load_model_preferences(config)
        return _project_start_flow._render_project_start(agent, config, prefs, force_ai=len(parts) == 3)
    if parts[0] != "roles":
        return None

    prefs = _model_views._load_model_preferences(config)
    if len(parts) == 1:
        _model_views._sync_prince2_roles_to_handoff(config, prefs)
        return _project_role_views._render_prince2_roles(config)
    if len(parts) == 2 and parts[1] == "domains":
        return _project_role_tree_views._render_prince2_role_domains()
    if len(parts) == 3 and parts[1] == "context":
        return _project_role_views._render_prince2_role_context(config, parts[2])
    if len(parts) == 2 and parts[1] == "tree":
        return _project_role_tree_views._render_prince2_role_tree(config)
    if len(parts) == 3 and parts[1] == "tree" and parts[2] == "approve":
        _project_role_flow._approve_prince2_role_tree_baseline(config, prefs, source="roles_tree_approve")
        return "Approved PRINCE2 role-tree baseline.\n" + _project_role_tree_views._render_prince2_role_tree_baseline(config)
    if len(parts) == 2 and parts[1] == "baseline":
        return _project_role_tree_views._render_prince2_role_tree_baseline(config)
    if len(parts) == 3 and parts[1] == "baseline" and parts[2] == "matrix":
        return _project_role_tree_views._render_prince2_role_tree_baseline_matrix(config)
    if len(parts) in {2, 3} and parts[1] == "messages":
        return _project_role_runtime_views._render_prince2_role_messages(config, node_id=parts[2] if len(parts) == 3 else None)
    if len(parts) == 2 and parts[1] == "runtime":
        return _project_role_runtime_views._render_prince2_role_runtime(config)
    if len(parts) == 2 and parts[1] == "active":
        return _project_role_runtime_views._render_prince2_role_active(config)
    if len(parts) == 2 and parts[1] == "control":
        return _project_role_runtime_views._render_prince2_role_control(config)
    if len(parts) == 2 and parts[1] == "queues":
        return _project_role_runtime_views._render_prince2_role_queues(config)
    if len(parts) in {2, 3} and parts[1] == "tick":
        max_nodes = None
        if len(parts) == 3:
            try:
                max_nodes = int(parts[2])
            except ValueError:
                return "Usage: roles tick [max_nodes]"
        result = _project_role_flow._tick_prince2_role_runtime(config, max_nodes=max_nodes)
        return (
            f"Batch advanced PRINCE2 runtime: processed={result.get('processed')} "
            f"woken={result.get('woken')} progressed={result.get('progressed')} skipped={result.get('skipped')}.\n"
            + _project_role_runtime_views._render_prince2_role_runtime(config)
        )
    if len(parts) == 2 and parts[1] == "check":
        return _project_role_tree_views._render_prince2_role_check(config)
    if len(parts) == 2 and parts[1] == "flow":
        return _project_role_tree_views._render_prince2_role_flow()
    if len(parts) == 2 and parts[1] == "matrix":
        return _project_role_tree_views._render_prince2_role_matrix(config)
    if len(parts) == 2 and parts[1] == "propose":
        prefs.apply_prince2_role_proposal()
        _model_views._save_model_preferences(config, prefs)
        _project_role_flow._approve_prince2_role_tree_baseline(config, prefs, source="roles_propose")
        _model_views._apply_model_preferences(agent, config)
        return (
            "Applied automatic PRINCE2 role proposal.\n"
            + _project_role_views._render_prince2_roles(config)
            + "\n"
            + _project_role_tree_views._render_prince2_role_tree_baseline(config)
        )
    if len(parts) == 2 and parts[1] == "setup":
        return _project_role_flow._guided_roles_setup(
            prefs=prefs,
            config=config,
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) == 2 and parts[1] == "shell":
        return _project_role_flow._guided_role_shell(
            prefs=prefs,
            config=config,
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) == 3 and parts[1] == "shell":
        return _project_role_flow._guided_role_node_shell(
            prefs=prefs,
            config=config,
            node_id=parts[2],
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) == 3 and parts[1] == "switch":
        return _project_role_flow._guided_role_node_switch_agent(
            prefs=prefs,
            config=config,
            node_id=parts[2],
            input_stream=input_stream,
            output_stream=output_stream,
        )
    return (
        "Usage: roles | roles domains | roles context <node_id> | roles tree | roles tree approve | roles baseline | "
        "roles baseline matrix | roles runtime | roles active | roles control | roles queues | roles messages [node_id] | "
        "roles tick [max_nodes] | roles check | roles flow | roles matrix | roles propose | roles setup | roles shell [node_id] | "
        "roles switch [node_id]"
    )


def _handle_role_command(
    command: str,
    agent: Agent,
    config: AgentConfig,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> str | None:
    parts = command.split()
    if not parts:
        return None
    if parts[0] != "role":
        return None

    prefs = _model_views._load_model_preferences(config)
    if len(parts) == 2 and parts[1] == "menu":
        return _project_role_flow._guided_role_tree_menu(
            prefs=prefs,
            config=config,
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) == 2 and parts[1] == "shell":
        return _project_role_flow._guided_role_shell(
            prefs=prefs,
            config=config,
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) == 3 and parts[1] == "shell":
        return _project_role_flow._guided_role_node_shell(
            prefs=prefs,
            config=config,
            node_id=parts[2],
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) == 3 and parts[1] == "switch":
        return _project_role_flow._guided_role_node_switch_agent(
            prefs=prefs,
            config=config,
            node_id=parts[2],
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) == 3 and parts[1] == "menu":
        return _project_role_flow._guided_role_node_menu(
            prefs=prefs,
            config=config,
            node_id=parts[2],
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) in {4, 5} and parts[1] == "add-child":
        try:
            child = _project_role_flow._add_child_prince2_role_node(
                config,
                prefs,
                parent_id=parts[2],
                role_type=parts[3],
                node_id=parts[4] if len(parts) == 5 else None,
            )
        except ValueError as exc:
            return str(exc)
        return (
            f"Added delegated PRINCE2 role node {child.get('node_id')} under {child.get('parent_id')}.\n"
            + _project_role_tree_views._render_prince2_role_tree_baseline(config)
        )
    if len(parts) == 2 and parts[1] == "add-child":
        return _project_role_flow._guided_role_add_child(
            prefs=prefs,
            config=config,
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) >= 3 and parts[1] == "model":
        if len(parts) == 3:
            return _project_role_flow._guided_role_node_menu(
                prefs=prefs,
                config=config,
                node_id=parts[2],
                input_stream=input_stream,
                output_stream=output_stream,
            )
        if len(parts) < 5:
            return "Usage: role model <node_id> <provider> <provider_model> [reasoning_effort=<value>] [account=<name>] [pool=<primary|reviewer|fallback>]"
        extra_params: dict[str, str] = {}
        account = None
        pool = "primary"
        for token in parts[5:]:
            key, separator, value = token.partition("=")
            if not separator:
                return "Usage: role model <node_id> <provider> <provider_model> [reasoning_effort=<value>] [account=<name>] [pool=<primary|reviewer|fallback>]"
            if key == "account":
                account = value or None
            elif key == "pool":
                pool = value
            else:
                extra_params[key] = value
        try:
            node = _project_role_flow._assign_prince2_role_node(
                config,
                prefs,
                node_id=parts[2],
                provider=parts[3],
                provider_model=parts[4],
                params=extra_params,
                account=account,
                pool=pool,
            )
        except ValueError as exc:
            return str(exc)
        assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
        if pool == "primary":
            return (
                f"Assigned role node {node.get('node_id')}: provider={assignment.get('provider')} "
                f"provider_model={assignment.get('provider_model')} account={assignment.get('account') or 'none'} pool=primary."
            )
        pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
        routes = pools.get(pool, []) if isinstance(pools.get(pool, []), list) else []
        route = routes[-1] if routes and isinstance(routes[-1], dict) else {}
        return (
            f"Assigned role node {node.get('node_id')}: provider={route.get('provider')} "
            f"provider_model={route.get('provider_model')} account={route.get('account') or 'none'} pool={pool}."
        )
    if len(parts) >= 3 and parts[1] == "tolerance":
        if len(parts) == 5 and parts[2] == "set":
            try:
                margin = float(parts[4].rstrip("%"))
            except ValueError:
                return "Usage: role tolerance set <node_id> <percent>"
            try:
                updated = _project_role_flow._set_prince2_role_node_tolerance_margin(
                    config, prefs, node_id=parts[3], margin_percent=margin
                )
            except ValueError as exc:
                return str(exc)
            return f"Updated tolerance for {parts[3]}: margin={updated.get('tolerance_margin_percent', 'unknown')}."
        if len(parts) == 4 and parts[2] == "reset":
            updated = _project_role_flow._reset_prince2_role_node_tolerance(config, prefs, node_id=parts[3])
            return (
                f"Reset tolerance for {parts[3]}: margin={updated.get('tolerance_margin_percent', 'unknown')} "
                f"pressure={updated.get('tolerance_pressure_percent', 'unknown')}."
            )
        return "Usage: role tolerance set <node_id> <percent> | role tolerance reset <node_id>"
    if len(parts) >= 3 and parts[1] == "remove":
        reparent_children = True
        for token in parts[3:]:
            key, separator, value = token.partition("=")
            if not separator:
                return "Usage: role remove <node_id> [reparent_children=<yes|no>]"
            if key == "reparent_children":
                reparent_children = value.strip().lower() not in {"0", "false", "no"}
        try:
            removed = _project_role_flow._remove_prince2_role_node(
                config, prefs, node_id=parts[2], reparent_children=reparent_children
            )
        except ValueError as exc:
            return str(exc)
        return (
            f"Removed PRINCE2 role node {removed.get('node_id', parts[2])}.\n"
            + _project_role_tree_views._render_prince2_role_tree_baseline(config)
        )
    if len(parts) >= 5 and parts[1] == "assign":
        extra_params: dict[str, str] = {}
        account = None
        pool = "primary"
        for token in parts[5:]:
            key, separator, value = token.partition("=")
            if not separator:
                return "Usage: role assign <node_id> <provider> <provider_model> [reasoning_effort=<value>] [account=<name>] [pool=<primary|reviewer|fallback>]"
            if key == "account":
                account = value or None
            elif key == "pool":
                pool = value
            else:
                extra_params[key] = value
        try:
            node = _project_role_flow._assign_prince2_role_node(
                config,
                prefs,
                node_id=parts[2],
                provider=parts[3],
                provider_model=parts[4],
                params=extra_params,
                account=account,
                pool=pool,
            )
        except ValueError as exc:
            return str(exc)
        assignment = node.get("assignment", {}) if isinstance(node.get("assignment"), dict) else {}
        if pool == "primary":
            return (
                f"Assigned role node {node.get('node_id')}: provider={assignment.get('provider')} "
                f"provider_model={assignment.get('provider_model')} account={assignment.get('account') or 'none'} pool=primary."
            )
        pools = node.get("assignment_pool", {}) if isinstance(node.get("assignment_pool"), dict) else {}
        routes = pools.get(pool, []) if isinstance(pools.get(pool, []), list) else []
        route = routes[-1] if routes and isinstance(routes[-1], dict) else {}
        return (
            f"Assigned role node {node.get('node_id')}: provider={route.get('provider')} "
            f"provider_model={route.get('provider_model')} account={route.get('account') or 'none'} pool={pool}."
        )
    if len(parts) == 2 and parts[1] == "assign":
        return _project_role_flow._guided_role_assign(
            prefs=prefs,
            config=config,
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) >= 6 and parts[1] == "message":
        payload_scope: list[str] = []
        evidence_refs: list[str] = []
        summary = None
        for token in parts[5:]:
            key, separator, value = token.partition("=")
            if not separator:
                return "Usage: role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> [evidence=<ref1,ref2>] [summary=<text_with_underscores>]"
            if key == "payload":
                payload_scope = [item.strip() for item in value.split(",") if item.strip()]
            elif key == "evidence":
                evidence_refs = [item.strip() for item in value.split(",") if item.strip()]
            elif key == "summary":
                summary = value.replace("_", " ").strip()
        if not payload_scope:
            return "Usage: role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> [evidence=<ref1,ref2>] [summary=<text_with_underscores>]"
        try:
            message = _project_role_flow._send_prince2_role_message(
                config,
                source_node=parts[2],
                target_node=parts[3],
                edge_id=parts[4],
                payload_scope=payload_scope,
                evidence_refs=evidence_refs,
                summary=summary,
            )
        except ValueError as exc:
            _project_handoff_views._record_handoff_action(
                config,
                phase="role_message_blocked",
                task=f"role message {parts[2]} {parts[3]} {parts[4]}",
                summary=str(exc),
                details={
                    "source_node": parts[2],
                    "target_node": parts[3],
                    "edge_id": parts[4],
                    "payload_scope": list(payload_scope),
                },
            )
            return str(exc)
        return (
            f"Queued PRINCE2 node message {message.get('message_id')} "
            f"{parts[2]} -> {parts[3]} edge={parts[4]}.\n"
            + _project_role_runtime_views._render_prince2_role_messages(config, node_id=parts[3])
        )
    if len(parts) >= 4 and parts[1] == "wait":
        reason = None
        wake_triggers = None
        for token in parts[3:]:
            key, separator, value = token.partition("=")
            if not separator:
                return "Usage: role wait <node_id> reason=<text_with_underscores> [wake=<trigger1,trigger2>]"
            if key == "reason":
                reason = value.replace("_", " ").strip()
            elif key == "wake":
                wake_triggers = [item.strip() for item in value.split(",") if item.strip()]
        if not reason:
            return "Usage: role wait <node_id> reason=<text_with_underscores> [wake=<trigger1,trigger2>]"
        try:
            node = _project_role_flow._set_prince2_role_node_waiting(
                config,
                node_id=parts[2],
                reason=reason,
                wake_triggers=wake_triggers,
            )
        except ValueError as exc:
            return str(exc)
        return (
            f"Node {node.get('node_id')} is now waiting.\n"
            + _project_role_runtime_views._render_prince2_role_runtime(config)
        )
    if len(parts) >= 4 and parts[1] == "wake":
        trigger = None
        for token in parts[3:]:
            key, separator, value = token.partition("=")
            if not separator:
                return "Usage: role wake <node_id> trigger=<name>"
            if key == "trigger":
                trigger = value.strip()
        if not trigger:
            return "Usage: role wake <node_id> trigger=<name>"
        try:
            node = _project_role_flow._wake_prince2_role_node(
                config,
                node_id=parts[2],
                trigger=trigger,
            )
        except ValueError as exc:
            return str(exc)
        return (
            f"Node {node.get('node_id')} woke with trigger {trigger}.\n"
            + _project_role_runtime_views._render_prince2_role_runtime(config)
        )
    if len(parts) == 3 and parts[1] == "tick":
        try:
            result = _project_role_flow._tick_prince2_role_node(config, node_id=parts[2])
        except ValueError as exc:
            return str(exc)
        return (
            f"Node {result.get('node_id')} advanced to {result.get('state')}.\n"
            + _project_role_runtime_views._render_prince2_role_messages(config, node_id=parts[2])
        )
    if len(parts) >= 2 and parts[1] == "configure":
        if len(parts) > 3:
            return "Usage: role configure [role]"
        requested_role = parts[2] if len(parts) == 3 else None
        return _project_role_flow._guided_role_configure(
            requested_role=requested_role,
            prefs=prefs,
            config=config,
            input_stream=input_stream,
            output_stream=output_stream,
        )
    if len(parts) == 3 and parts[1] == "clear":
        role = parts[2]
        if role not in PRINCE2_ROLE_IDS:
            return f"Unsupported PRINCE2 role '{role}'. Supported: {', '.join(PRINCE2_ROLE_IDS)}"
        prefs.clear_prince2_role_assignment(role)
        _model_views._save_model_preferences(config, prefs)
        _model_views._sync_prince2_roles_to_handoff(config, prefs)
        return f"Cleared PRINCE2 role assignment for {PRINCE2_ROLE_LABELS[role]}."
    return (
        "Usage: role configure [role] | role clear <role> | role add-child <parent_node> <role_type> [node_id] | "
        "role menu [node_id] | role shell [node_id] | role model <node_id> [provider provider_model] "
        "[reasoning_effort=<value>] [account=<name>] | role tolerance set <node_id> <percent> | "
        "role tolerance reset <node_id> | role remove <node_id> [reparent_children=<yes|no>] | role assign <node_id> "
        "<provider> <provider_model> [reasoning_effort=<value>] [account=<name>] | role message <source_node> "
        "<target_node> <edge_id> payload=<scope1,scope2> [evidence=<ref1,ref2>] [summary=<text_with_underscores>] | "
        "role wait <node_id> reason=<text_with_underscores> [wake=<trigger1,trigger2>] | role wake <node_id> trigger=<name> | "
        "role tick <node_id>"
    )
