# Agent Handoff

## Current objective
Continue trimming legacy bodies out of `stagewarden/main.py`, keeping the code organized by concern and subfolder while preserving CLI behavior and the existing tests. The current slice moved the project design/local-execution helpers off `main.py`, kept the project-tree/start flows on direct module calls, and preserved the trace contract.

## Current state
The worktree is dirty with the ongoing bridge-removal slice. `stagewarden/status_limits_views.py` already owns provider-limit extraction, and `stagewarden/status_views.py` delegates to it. The current edit moved the project design/local-execution helpers into `stagewarden/model_views.py` and `stagewarden/project/design_flow.py`, wired `stagewarden/project/tree_flow.py`, `stagewarden/project/start_flow.py`, and `stagewarden/project/role_flow.py` to those direct helpers, removed the corresponding `main.py` bridges, and kept the focused project-tree/project-start regression slice green.

## Recent changes
- `stagewarden/model_views.py`, `stagewarden/project/design_flow.py`, `stagewarden/project/tree_flow.py`, `stagewarden/project/start_flow.py`, and `stagewarden/project/role_flow.py`: now resolve local-execution and project-design helpers directly instead of through removed `main.py` wrappers.
- Validation: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_project_tree_propose_builds_proportional_review_proposal_from_brief tests.test_trace_cli.TraceAndCliTests.test_project_tree_propose_ai_attaches_local_execution_candidates_when_discovered tests.test_trace_cli.TraceAndCliTests.test_project_tree_propose_ai_merges_model_suggestions_without_approval tests.test_trace_cli.TraceAndCliTests.test_project_tree_propose_reports_missing_brief_gaps tests.test_trace_cli.TraceAndCliTests.test_project_start_blocks_when_design_or_brief_has_gaps tests.test_trace_cli.TraceAndCliTests.test_project_start_approves_ready_project_tree_proposal tests.test_trace_cli.TraceAndCliTests.test_project_start_preloads_local_delivery_fallbacks_when_discovered tests.test_trace_cli.TraceAndCliTests.test_project_start_ai_persists_valid_ai_tree_patch_after_approval tests.test_trace_cli.TraceAndCliTests.test_project_start_requests_clarification_for_missing_brief` passes.
- `stagewarden/project/tree_flow.py`, `stagewarden/project/start_flow.py`, `stagewarden/cli_dispatch.py`, and `stagewarden/shell_views.py`: now call project-tree and model helpers directly instead of relying on removed `main.py` bridges.
- `stagewarden/project/tree.py`: renamed the generated assurance node to `assurance.validation_assurance` / `Validation Assurance` to match the trace contract.
- `stagewarden/project/role_views.py`, `stagewarden/project/role_flow.py`, and `stagewarden/project/role_runtime_views.py`: now call `stagewarden/project/model_recommendation.py` directly for node recommendations.
- `stagewarden/main.py`: removed the `node_model_recommendation` bridge wrapper after the call sites moved out.
- Validation: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_shell_backend_cli_can_set_and_report_backend tests.test_trace_cli.TraceAndCliTests.test_status_json_reports_configured_shell_backend tests.test_trace_cli.TraceAndCliTests.test_status_full_cli_renders_remediations tests.test_trace_cli.TraceAndCliTests.test_model_list_shows_provider_model_reasoning_catalog tests.test_trace_cli.TraceAndCliTests.test_goal_cli_persists_and_surfaces_in_statusline tests.test_trace_cli.TraceAndCliTests.test_external_io_cli_download_records_evidence tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_status_and_mode_commands` passes.
- `stagewarden/project/role_views.py`: added `_prince2_roles_report()` and made `_render_prince2_roles()` use local report data.
- `stagewarden/model_views.py`: fixed the provider-model catalog render for `model list <provider>` so it matches the trace-cli contract.
- `stagewarden/main.py`: removed the remaining PRINCE2, model-preference, handoff, and capability-surface bridge wrappers after the status and role view modules switched to local helpers, including the `roles context` bridge.
- `stagewarden/project_handoff_views.py`: added the shared handoff-action recorder so command flows no longer need the `main.py` bridge.
- `stagewarden/status_views.py`, `stagewarden/status_dashboard_views.py`, and `stagewarden/status_limits_views.py`: removed the shell-backend/status recursion from the interactive status path, restored the `Provider limit status:` header, and aligned the `last_attempt` / provider configuration strings expected by the focused CLI tests.
- Validation: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_goal_cli_persists_and_surfaces_in_statusline tests.test_trace_cli.TraceAndCliTests.test_external_io_cli_download_records_evidence tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_status_and_mode_commands` passes.
- `stagewarden/cli_dispatch.py`: now dispatches `goal` directly through `stagewarden/project_state_views.py`, so the temporary `main.py` goal bridge was removed again.

## Important files
- `stagewarden/main.py`: legacy entrypoint still being reduced.
- `stagewarden/project/role_views.py`: new home for the PRINCE2 roles report/render slice.
- `stagewarden/status_limits_views.py`: completed provider-limit slice, useful as the current refactor pattern.

## Technical decisions
- Move one report/render slice at a time.
  - Reason: smallest safe refactor, easier regression control.
  - Trade-offs: main shrinks gradually, not all at once.
- Keep report logic near the view layer.
  - Reason: matches the MVC-ish split already used elsewhere.
  - Trade-offs: some modules still import back into `main.py` for shared helpers.

## Open issues
- Bugs: none known from the latest focused batch.
- Risks: additional `main.py` bridge removals can still perturb CLI formatting if done without a test pass.
- Unknowns: which remaining `main.py` block should be the next clean slice.

## Next steps
1. Inspect the next remaining legacy block in `stagewarden/main.py`.
2. Continue extracting the next isolated helper slice into the appropriate submodule.
3. Re-run the focused trace batch after the next bridge removal.

## Commands
```bash
# test
python3 -m unittest tests.test_trace_cli
python3 -m unittest tests.test_prince2
```
