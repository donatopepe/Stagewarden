# Agent Handoff

## Current objective
Completed the elimination of the `main = _main()` lazy import pattern across the entire codebase and stripped `stagewarden/main.py` to a minimal entry point. All modules now use direct imports from owner modules instead of accessing symbols through `main.`.

## Current state
`stagewarden/main.py` is now reduced to ~80 lines: just the entry point `main()`, `BASELINE_CAPABILITY_GROUPS`, and `BASELINE_REMEDIATION_BY_GROUP` constants (kept there to avoid circular imports between `status_views.py` and `status_dashboard_views.py`). All 16 files that previously used the `main = _main()` pattern have been converted to direct imports:
- 8 files had dead patterns (no actual `main.` usage) - removed completely
- 3 project flow modules (`role_command_flow.py`, `tree_flow.py`, `role_flow.py`) now import directly from sibling/parent modules
- 5 view modules (`status_views.py`, `status_dashboard_views.py`, `status_limits_views.py`, `battery_views.py`, `design_flow.py`) now import directly from owner modules

All focused trace CLI batches pass (shell, status, auth, permission, project, roles, sources, boundary, handoff, completion, help, executor, agent integration).

## Recent changes
- Removed dead `_main()` patterns from 8 files: `project/start_flow.py`, `project/role_views.py`, `project/role_runtime_views.py`, `project/role_tree_views.py`, `project/model_recommendation.py`, `mode_views.py`, `model_inspection_views.py`, `report_views.py`.
- Broke `main = _main()` in `project/role_command_flow.py` - replaced `main._*` calls with `_project_role_flow._*` calls.
- Broke `main = _main()` in `project/tree_flow.py` - added direct imports from `.flow`, `..modelprefs`, `..role_tree`.
- Broke `main = _main()` in `project/role_flow.py` - added direct imports from `.flow`.
- Broke `main = _main()` in `status_views.py` - added direct imports for `ALLOWED_MODEL_ACTIONS`, `MODEL_BACKENDS`, `REGISTRY_MODELS`, `provider_capability`, `load_ai_models_catalog`, `catalog_entries_for_provider`, `catalog_entry_for_provider_model`, `detect_runtime_capabilities`.
- Broke `main = _main()` in `status_dashboard_views.py` - added direct imports for `REGISTRY_MODELS`, `provider_capability`.
- Broke `main = _main()` in `status_limits_views.py` - added direct imports for `REGISTRY_MODELS`, `provider_capability`, `account_key`, `MODEL_BACKENDS`, `detect_runtime_capabilities`. Fixed variable shadowing issue where local `provider_capability` shadowed the imported function.
- Broke `main = _main()` in `battery_views.py` - added direct import for `PlanStep`.
- Broke `main = _main()` in `project/design_flow.py` - added direct import for `detect_runtime_capabilities`.
- Fixed circular import between `status_views.py` and `status_dashboard_views.py` by moving `BASELINE_CAPABILITY_GROUPS`/`BASELINE_REMEDIATION_BY_GROUP` back to `main.py` (which has no imports from view modules).
- Fixed `report_views.py` to import `_project_handoff_views` directly instead of through `_main()`.
- Stripped `stagewarden/main.py` from 429 lines to ~80 lines - removed all thin wrapper functions and unused imports.
- Validation: all focused trace CLI batches pass.

## Important files
- `stagewarden/main.py`: now minimal entry point (~80 lines) with only `main()`, `BASELINE_CAPABILITY_GROUPS`, and `BASELINE_REMEDIATION_BY_GROUP`.
- `stagewarden/status_views.py`: now uses direct imports for all previously `main.`-accessed symbols.
- `stagewarden/project/role_flow.py`, `project/tree_flow.py`, `project/role_command_flow.py`: now use direct imports from sibling/parent modules.

## Technical decisions
- Kept `BASELINE_CAPABILITY_GROUPS`/`BASELINE_REMEDIATION_BY_GROUP` in `main.py` to avoid circular imports between `status_views.py` and `status_dashboard_views.py`. This is acceptable since `main.py` is now minimal and these constants are conceptually part of the CLI surface definition.
- Used `SUPPORTED_MODELS as REGISTRY_MODELS` alias pattern to maintain backward compatibility with existing code that expects `REGISTRY_MODELS`.
- Fixed variable shadowing in `status_limits_views.py` where local `provider_capability` shadowed the imported function.

## Open issues
- Bugs: `pytest` is unavailable in this environment; use `python3 -m unittest` for verification here.
- Risks: None identified - all focused test batches pass.
- Unknowns: None.

## Next steps
1. Consider running the full `tests.test_trace_cli` suite to catch any edge cases.
2. Commit this refactor slice.
3. Future work: further cleanup of any remaining unused imports across the codebase.

## Commands
```bash
# test
python3 -m unittest tests.test_agent_integration.AgentIntegrationTests.test_agent_closes_recovery_gate_after_recovery_lane_wet_run
python3 -m unittest tests.test_trace_cli
python3 -m unittest tests.test_prince2
```
