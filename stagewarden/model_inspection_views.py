from __future__ import annotations

from .agent import Agent
from .config import AgentConfig
from .handoff import format_run_model
from .modelprefs import SUPPORTED_MODELS
from . import model_views as _model_views
from .provider_registry import provider_capability, provider_model_specs
from .textcodec import dumps_ascii, loads_text


def _local_model_profile_from_spec(spec) -> dict[str, object]:
    agentic_fit = "medium"
    tool_support_risk = "unknown"
    availability = str(spec.availability or "unknown")
    hint = str(spec.context_window_hint or "")
    lowered_hint = hint.lower()
    if availability == "local-agentic":
        agentic_fit = "high"
        tool_support_risk = "medium"
    elif availability == "local-limited":
        agentic_fit = "low"
        tool_support_risk = "high"
    elif availability == "local-specialized":
        agentic_fit = "medium"
        tool_support_risk = "medium"
    strengths: list[str] = []
    weaknesses: list[str] = []
    best_for: list[str] = []
    if "coder" in spec.id.lower():
        strengths.append("coding-oriented local model")
        best_for.append("code editing and repository tasks")
    if "deepseek" in spec.id.lower() or "r1" in spec.id.lower():
        strengths.append("stronger reasoning-oriented profile")
        best_for.append("deeper debugging and analysis")
    if "sqlcoder" in spec.id.lower():
        strengths.append("specialized SQL profile")
        best_for.append("SQL generation and schema work")
    if "validate tool support" in lowered_hint:
        weaknesses.append("tool support must be validated before agentic routing")
        best_for.append("manual/local chat unless validated")
    if not strengths:
        strengths.append("available local model discovered from Ollama")
    if not best_for:
        best_for.append("general local experimentation")
    summary = hint or f"Discovered local model {spec.id}."
    return {
        "id": spec.id,
        "label": spec.label,
        "availability": availability,
        "reasoning_efforts": list(spec.reasoning_efforts),
        "reasoning_default": spec.reasoning_default,
        "metadata_hint": hint,
        "summary": summary,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "best_for": best_for,
        "agentic_fit": agentic_fit,
        "tool_support_risk": tool_support_risk,
        "source": spec.source,
    }


def _local_model_inspection_prompt(catalog: list[dict[str, object]], selected_model: str | None) -> str:
    inventory = dumps_ascii({"models": catalog}, indent=2)
    return "\n".join(
        [
            "You are evaluating dynamically discovered local Ollama models for a Codex-style coding agent.",
            "Task: analyze the discovered local model inventory and summarize the peculiarities of each model.",
            "Rules:",
            "- Use only the provided model ids and metadata hints.",
            "- Do not invent benchmark numbers.",
            "- If tool support is uncertain, say so explicitly.",
            "- Return valid JSON only.",
            "- JSON schema:",
            '{',
            '  "models": [',
            '    {',
            '      "id": "model id",',
            '      "summary": "short summary",',
            '      "strengths": ["..."],',
            '      "weaknesses": ["..."],',
            '      "best_for": ["..."],',
            '      "agentic_fit": "high|medium|low",',
            '      "tool_support_risk": "low|medium|high|unknown"',
            "    }",
            "  ],",
            '  "global_recommendation": "short recommendation"',
            "}",
            f"Selected model: {selected_model or 'all discovered local models'}",
            "Discovered inventory:",
            inventory,
        ]
    )


def _inspect_provider_models(
    agent: Agent,
    config: AgentConfig,
    *,
    provider: str,
    provider_model: str | None = None,
) -> dict[str, object]:
    if provider not in SUPPORTED_MODELS:
        raise ValueError(f"Unsupported model '{provider}'. Supported: {', '.join(SUPPORTED_MODELS)}")
    specs = [spec for spec in provider_model_specs(provider) if spec.id != "provider-default"]
    if provider_model is not None:
        specs = [spec for spec in specs if spec.id == provider_model]
        if not specs:
            raise ValueError(f"Provider-model '{provider_model}' not found for provider '{provider}'.")
    catalog = [_local_model_profile_from_spec(spec) for spec in specs] if provider == "local" else [
        {
            "id": spec.id,
            "label": spec.label,
            "availability": spec.availability,
            "reasoning_efforts": list(spec.reasoning_efforts),
            "reasoning_default": spec.reasoning_default,
            "metadata_hint": spec.context_window_hint,
            "summary": spec.context_window_hint or spec.label,
            "strengths": [],
            "weaknesses": [],
            "best_for": [],
            "agentic_fit": "unknown",
            "tool_support_risk": "unknown",
            "source": spec.source,
        }
        for spec in specs
    ]
    report: dict[str, object] = {
        "command": "model inspect",
        "provider": provider,
        "provider_model": provider_model,
        "status": "ok",
        "catalog_source": next((item["source"] for item in catalog if item.get("source")), provider_capability(provider).source) if catalog else provider_capability(provider).source,
        "models": catalog,
        "ai_analysis": {
            "attempted": False,
            "ok": False,
            "model": None,
            "account": None,
            "message": "",
        },
    }
    if provider != "local" or not catalog:
        return report
    _model_views._apply_model_preferences(agent, config)
    prefs = _model_views._load_model_preferences(config)
    analysis_model = _model_views._choose_cloud_priority_model(agent, prefs)
    account = prefs.account_for_model(analysis_model)
    result = agent.handoff.execute(format_run_model(analysis_model, _local_model_inspection_prompt(catalog, provider_model), account=account))
    ai_analysis = {
        "attempted": True,
        "ok": False,
        "model": analysis_model,
        "account": account or None,
        "message": "",
    }
    if not result.ok:
        ai_analysis["message"] = result.error or "Model inspection call failed."
        report["ai_analysis"] = ai_analysis
        report["global_recommendation"] = "Using metadata-derived local model profiles only."
        return report
    try:
        payload = loads_text(result.output)
    except ValueError as exc:
        ai_analysis["message"] = f"Inspection output was not valid JSON: {exc}"
        report["ai_analysis"] = ai_analysis
        report["global_recommendation"] = "Using metadata-derived local model profiles only."
        return report
    ai_models = payload.get("models", []) if isinstance(payload, dict) else []
    ai_by_id = {
        str(item.get("id", "")).strip(): item
        for item in ai_models
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    }
    merged_models: list[dict[str, object]] = []
    for item in catalog:
        merged = dict(item)
        candidate = ai_by_id.get(str(item.get("id")))
        if isinstance(candidate, dict):
            for key in ("summary", "agentic_fit", "tool_support_risk"):
                value = candidate.get(key)
                if isinstance(value, str) and value.strip():
                    merged[key] = value.strip()
            for key in ("strengths", "weaknesses", "best_for"):
                value = candidate.get(key)
                if isinstance(value, list):
                    merged[key] = [str(entry).strip() for entry in value if str(entry).strip()]
        merged_models.append(merged)
    ai_analysis["ok"] = True
    ai_analysis["message"] = "AI synthesis applied to discovered local model inventory."
    report["models"] = merged_models
    report["ai_analysis"] = ai_analysis
    report["global_recommendation"] = (
        str(payload.get("global_recommendation", "")).strip()
        if isinstance(payload, dict) and str(payload.get("global_recommendation", "")).strip()
        else "Prefer models with high agentic fit and lower tool support risk."
    )
    return report


def _render_provider_model_inspection(report: dict[str, object]) -> str:
    lines = [
        f"Provider-model inspection for {report.get('provider', 'unknown')}:",
        f"- provider_model_filter: {report.get('provider_model') or 'all'}",
        f"- catalog_source: {report.get('catalog_source', 'unknown')}",
    ]
    ai = report.get("ai_analysis", {}) if isinstance(report.get("ai_analysis"), dict) else {}
    lines.append(
        f"- ai_analysis: attempted={ai.get('attempted', False)} ok={ai.get('ok', False)} "
        f"model={ai.get('model') or 'none'} account={ai.get('account') or 'none'}"
    )
    if ai.get("message"):
        lines.append(f"- ai_message: {ai.get('message')}")
    if report.get("global_recommendation"):
        lines.append(f"- recommendation: {report.get('global_recommendation')}")
    models = [item for item in report.get("models", []) if isinstance(item, dict)]
    if not models:
        lines.append("- models: none")
        return "\n".join(lines)
    lines.append("Models:")
    for item in models:
        lines.append(
            f"- {item.get('id')}: fit={item.get('agentic_fit')} tool_support_risk={item.get('tool_support_risk')} "
            f"availability={item.get('availability')} summary={item.get('summary')}"
        )
        strengths = ", ".join(str(entry) for entry in item.get("strengths", []) if str(entry).strip()) or "none"
        weaknesses = ", ".join(str(entry) for entry in item.get("weaknesses", []) if str(entry).strip()) or "none"
        best_for = ", ".join(str(entry) for entry in item.get("best_for", []) if str(entry).strip()) or "none"
        lines.append(f"  strengths: {strengths}")
        lines.append(f"  weaknesses: {weaknesses}")
        lines.append(f"  best_for: {best_for}")
    return "\n".join(lines)
