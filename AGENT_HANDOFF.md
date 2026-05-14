# Agent Handoff

## Current objective
 Keep Stagewarden broad and cross-platform by covering common utility tasks directly in-repo, preferring optional well-known libraries where they help and stdlib fallbacks where they do not. The active refactor must converge on an MVC-style layout across the module tree: model/catalog/provider logic in model modules, render/report helpers in view modules, and orchestration/dispatch in controller-style modules. The agent should also be able to receive commands, recurse through controlled self-instantiation of sub-agents when that helps decompose work, and route those recursive command trees explicitly rather than hiding them in monolithic entrypoints. The tool-surface slice is now in place; the active slice is continuing the refactor by deleting legacy duplicates from `main.py` and keeping `project_handoff.py` thin while `project_handoff_runtime.py` owns the active PRINCE2 runtime / messaging / persistence helpers behind wrappers. `executor_prompting.py` now owns the prompt/context construction helpers that were still inside `executor.py`, `stagewarden/project/brief.py` now owns the real project-brief guidance and clarification flow with `project_brief_flow.py` kept only for compatibility, `stagewarden/project/flow.py` now carries the shared project brief/tree wrapper bridge, `stagewarden/project/tree_flow.py` now carries the project-tree proposal/approval/report bridge so `main.py` can keep shrinking, `stagewarden/project/model_recommendation.py` now owns the tree model-selection helpers, `stagewarden/project/start_flow.py` now owns the project-start gate and clarification helpers, `stagewarden/project/design_flow.py` now owns the project design packet/report and now treats runtime-discovered local candidates as valid readiness so `project start` can proceed without a pre-approved cloud baseline and now owns the local-execution candidates report helper too, `stagewarden/project/role_tree_views.py` now owns the remaining PRINCE2 role domains/tree/baseline render helpers and excludes the rollback lane from the active local-fallback count, `stagewarden/project/role_command_flow.py` now owns the project-start and roles command dispatch bridge, `stagewarden/cli_dispatch.py` now owns the main CLI task dispatcher, `stagewarden/shell_views.py` now owns the interactive shell loop plus its permission/rate-limit approval and interactive completion helpers, `stagewarden/auth_views.py` now owns provider auth status, `stagewarden/model_inspection_views.py` now owns local/provider model inspection, `stagewarden/project_handoff_views.py` now owns the handoff/resume/board/register/transcript operational reports, `stagewarden/ui_views.py` now owns the help/slash UI helpers, `stagewarden/account_views.py` now owns the account command block and the account report, `stagewarden/command_views.py` now owns the shell/git/file/session/patch command cluster, `stagewarden/report_views.py` now owns the remaining board/boundary/permissions/risks/issues/quality/exception/lessons/todo report helpers, `stagewarden/mode_views.py` now owns the mode/status/project/report dispatch bridge that was still living in `main.py`, and `stagewarden/model_views.py` now owns the model/catalog/provider-selection block that was still living in `main.py` including catalog status/refresh/search plus model params/preset/variant flows and the guided model-choice flow. `stagewarden/battery_views.py` now owns the battery report/render slice, the old inline battery report body and inline battery renderer were removed from `main.py`, `stagewarden/status_views.py` now also owns the model-usage, cost-sidebar, full-status, provider-limit, and model-status helpers, and `stagewarden/model_views.py` now owns the catalog helper block that was still living in `main.py` including catalog status/refresh/search. The focused battery regression batch is green again after the split, and the model-command regression batch is green again after the model slice split. The next structural step is to keep organizing the code into clear subfolders by area so the growing surface remains navigable, then continue trimming the remaining role command helpers and any other legacy duplicates out of `main.py`. Refactoring must be treated as a permanent cyclic phase across the whole organizational tree, including nodes, roles, stages, and microtasks. The role command bridge was just corrected after an indentation bug in the generated extraction, and the focused `role`/`roles` regression batch is green again. The `project start` CLI path now goes through the structured `project_start_report` again so `next_missing_field` stays in the JSON payload. The interactive shell loop and completion helpers have now been split into `stagewarden/shell_views.py`, and the shell/role budget/question regression batch is green again after the split. The `project start` gate now treats runtime-discovered local candidates as valid AI readiness, so initial projects can proceed with local fallback discovery instead of being blocked by missing cloud providers or a missing approved baseline. `status` and `statusline` now resolve through the report paths again, and the local-fallback count excludes the rollback lane so the fallback readiness report matches the regression contract. The guided model-choice flow is now a bridge into `stagewarden/model_views.py`, and the interactive shell keeps its own completion/approval helpers in `stagewarden/shell_views.py`. `stagewarden/project/design_flow.py` now also owns the local execution candidates report helper that was still living in `main.py`. `stagewarden/status_views.py` now also owns the agent capability-surface report helper that feeds `roles context`, so the role-context report stays aligned with the status/report logic. `stagewarden/account_views.py` now also owns the accounts report helper and `stagewarden/status_views.py` now also owns the permissions and runtime-status helpers, so the last remaining account/status report bodies can stay out of `main.py`.

 `stagewarden/status_views.py` now also owns the agent capability-surface report helper that feeds `roles context`, so the role-context report stays aligned with the status/report logic.

 `stagewarden/status_views.py` now also owns the overview, health, and remediations render helpers, so the remaining dashboard bodies no longer live in `main.py`.
 `stagewarden/project/role_views.py` now also owns the PRINCE2 role assignments render helper, and the bridge in `main.py` now points at the correct module after the extraction.
 `stagewarden/project/role_flow.py` now also owns the project tolerance profile plus the role tolerance margin set/reset helpers, so the tolerance-specific PRINCE2 bodies no longer live in `main.py`.
 `stagewarden/cli_dispatch.py` now also owns the parser builder, so the CLI option surface no longer lives inline in `main.py`.
 `stagewarden/cli_dispatch.py` now also owns the parser builder internally without recursive delegation through `main.py`.
 `stagewarden/project/role_views.py` now also owns the PRINCE2 role assignments render helper, so the role assignment lines no longer live in `main.py`.

## Current state
- The executor now verifies mutating actions after execution instead of trusting tool success blindly.
- The repository now has a broader cross-platform utility surface in addition to the existing files, git, shell, and PRINCE2 flows.
- `stagewarden/model_views.py` now owns the model preference load/save/apply and PRINCE2 role-sync helpers, so `main.py` only keeps thin bridges for those flows.
- `stagewarden/command_views.py` now owns the shared `parse_limit` helper and `stagewarden/cli_dispatch.py` now owns the LJSON path helpers, so the last utility bodies can stay out of `main.py`.
- `stagewarden/ui_views.py` now owns `interactive_help_text`, so the remaining help text no longer lives inline in `main.py`.
- `stagewarden/shell_views.py` now owns the shell backend settings/report helpers, so the last shell-backend bodies can stay out of `main.py`.
- `stagewarden/tools/system.py` provides `system info`, `disk usage`, `process list`, `process kill`, `port check`, clipboard access, and browser opening with optional `psutil` / `pyperclip` support and stdlib fallbacks.
- `stagewarden/tools/external_io.py` now exposes generic hashing plus archive listing, extraction, and creation for zip/tar-style formats.
- `stagewarden/tools/browser.py` now provides browser fetch/open/screenshot flows with stdlib parsing plus optional Playwright screenshots.
- `stagewarden/tools/watch.py` now provides filesystem event observation with watchdog when available and polling fallback otherwise.
- `stagewarden/command_dispatch.py` now centralizes the parsing and execution of external-io, browser, watch, and system tool commands, and `stagewarden/tool_reports.py` centralizes the related text/report/evidence helpers so `stagewarden/main.py` can stay thinner.
- `stagewarden/project_state_views.py` now centralizes goal, budget, and question state/report helpers so the project-state commands no longer live inline in `stagewarden/main.py`.
- `stagewarden/executor_quality.py` now centralizes the response-quality scorer so `stagewarden/executor.py` can stay thinner.
- `stagewarden/project_handoff_state.py` now centralizes the persisted budget, goal, and user-question state helpers that were still living inside `stagewarden/project_handoff.py`.
- `stagewarden/project_handoff_views.py` now centralizes the handoff/resume/board/register/transcript operational reports that were still living inside `stagewarden/project_handoff.py`.
- `stagewarden/model_views.py` now owns the model/catalog/provider-selection block that was still living in `main.py`, including catalog status/refresh/search and model params/preset/variant flows.
- `stagewarden/account_views.py` now owns the account command block that was still living in `main.py`, including account add/login/logout/env/import/use/choose/remove/block/unblock/limit commands and the account report.
- `stagewarden/command_views.py` now owns the shell/git/file/session/patch command cluster that was still living in `main.py`, while `stagewarden/shell_views.py` now owns the permission approval, rate-limit decision, and interactive completion helpers used by the interactive shell.
- `stagewarden/report_views.py` now owns the remaining board/boundary/permissions/risks/issues/quality/exception/lessons/todo report helpers that were still living in `main.py`.
- `stagewarden/project_handoff_runtime.py` now centralizes the PRINCE2 runtime, message-flow, persistence, and node-token/cost helpers that were still living inside `stagewarden/project_handoff.py`.
- The remaining legacy method bodies were removed from `stagewarden/project_handoff.py`; the file is now a thin wrapper plus dynamic bindings around `stagewarden/project_handoff_runtime.py`.
- `stagewarden/executor_prompting.py` now centralizes the prompt, packet, schema, and role-context helpers that were still living inside `stagewarden/executor.py`.
- `stagewarden/project/brief.py` now centralizes the project-brief fields, guidance, and clarification helpers inside the new `stagewarden/project/` subpackage, `stagewarden/project/flow.py` now carries the wrapper bridge that `main.py` used to keep inline, `stagewarden/project/tree_flow.py` now carries the project-tree proposal/approval/report bridge, and `stagewarden/project_brief_flow.py` is compatibility only.
- `stagewarden/project/tree_flow.py` is now the active project-tree proposal/approval/report bridge and passes the focused project-tree regression batch.
- The legacy project-tree implementation bodies were removed from `stagewarden/main.py`, leaving only thin wrappers that delegate into `stagewarden/project/tree_flow.py`.
- `stagewarden/project/model_recommendation.py` now owns the tree model-selection helpers that were still duplicated in the tree bridge and main wrappers.
- `stagewarden/project/design_flow.py` now owns the project design packet/report helpers that were still living in `main.py`.
- `stagewarden/project/role_views.py` now owns the PRINCE2 role runtime/context report and render helpers that were still living in `main.py`.
- `stagewarden/project/role_runtime_views.py` now owns the PRINCE2 runtime, active, queues, control, and messages report/render helpers that were still living in `main.py`.
- `stagewarden/project/role_flow.py` now owns the PRINCE2 role-tree node discovery, navigation, detail, shell, provider-choice, action, and menu helpers that were still living in `main.py`.
- `stagewarden/project/role_tree_views.py` now owns the remaining PRINCE2 role domains/tree/baseline render helpers that were still living in `main.py`.
- `stagewarden/project/start_flow.py` now owns the `project start` gate, clarification records, and startup rendering helpers that were still living in `main.py`.
- `stagewarden/project_handoff_views.py` now owns the handoff/resume/board/register/transcript operational reports that were still living in `main.py`.
- `stagewarden/ui_views.py` now owns the help/slash UI helpers that were still living in `main.py`.
- `stagewarden/battery_views.py` now owns the battery report/render slice that was still living in `main.py`, the old inline battery report body and inline battery renderer were removed from `main.py`, leaving only the thin wrapper bridge, `stagewarden/status_views.py` now owns the model-usage helper slice, and the focused battery regression batch is green again after the split.
- `stagewarden/account_views.py` now owns the account command block that was still living in `main.py`, and the account/report regression batch is green again after the split.
- `stagewarden/command_views.py` now owns the shell/git/file/session/patch/permission command cluster that was still living in `main.py`, and the related CLI regression batch is green again after the split.
- `stagewarden/report_views.py` now owns the remaining board/boundary/permissions/risks/issues/quality/exception/lessons/todo report helpers that were still living in `main.py`, and the related CLI regression batch is green again after the split.
- The PRINCE2 role shell render now includes the `status_legend:` line and the `switch_hint:` line expected by the battery, and the antagonist KPI path now exposes `threat_count` so the role battery passes again.
- `stagewarden/status_views.py` now owns the first status/dashboard/statusline/overview/health helper slice, the `preflight`, `report`, and `doctor` helper slice, and the model-usage/cost-sidebar/full-status/provider-limit helper slice, while `stagewarden/main.py` shadows the old bodies with thin wrappers into that module.
- `stagewarden/status_views.py` now also owns the agent capability-surface helper used by `roles context`, while `stagewarden/main.py` keeps a thin bridge for compatibility.
- `stagewarden/shell_views.py` now also owns the shell backend, shell progress, prompt menu, and interactive command checks, while `stagewarden/main.py` keeps only thin bridges for compatibility.
- `stagewarden/shell_views.py` now also owns the shell command rewrite helper, while `stagewarden/main.py` keeps only thin bridges for compatibility.
- `stagewarden/project/role_flow.py` now also owns the PRINCE2 role assignment helper that was still living in `main.py`, and the focused role-assignment regression batch is green again.
- `stagewarden/status_views.py` now also owns the `sources` / `update` repo-health report helpers, while `stagewarden/main.py` keeps thin bridges for compatibility.
- `stagewarden/project/design_flow.py` now treats runtime-discovered local execution candidates as valid readiness, so `project start` can proceed in a fresh repo without a pre-approved cloud baseline.
- `stagewarden/project/role_tree_views.py` now excludes the rollback lane from the active local-fallback count so the readiness report matches the regression contract.
- `stagewarden/model_views.py` now owns the catalog helper block that was still living in `main.py`, and `main.py` now bridges those helpers through thin wrappers.
- `_focus_snapshot` was restored after the status slice cleanup so the battery and resume/status paths keep working.
- The duplicate legacy `overview/health/preflight/report` bodies were removed from `main.py`; only the thin wrapper definitions remain at the end of the file.
- The next structure slice should keep grouping related code into subfolders by concern so the module surface stays readable as the repo grows, then continue trimming the remaining status helpers and any other legacy duplicates out of `main.py`.
- `stagewarden/main.py`, `stagewarden/commands.py`, and `stagewarden/json_schema_registry.py` now route and document those new tool commands in both shell and JSON paths.
- `tests/test_tools.py`, `tests/test_trace_cli.py`, and `tests/test_json_schema_registry.py` now cover the new tool paths and registry entries.
- The live OpenRouter benchmark now uses three public suites: `general` (MMLU), `reasoning` (ARC-Challenge), and `truthfulness` (TruthfulQA-MC).
- `stagewarden/openrouter_benchmark.py` now returns a `suites` map, per-suite regression metadata, and an optional `history` block that compares the current run against the latest JSONL snapshot.
- The benchmark can append a history snapshot when `--openrouter-benchmark-history` is supplied, and it fails the run if the current accuracy regresses relative to the previous snapshot.
- The local PRINCE2 benchmark now runs through `--prince2-benchmark` and `prince2 benchmark`, with three prompt-driven suites: `governance`, `assurance`, and `recovery`.
- `stagewarden/prince2_benchmark.py` now derives orchestration from the live runtime graph, so the reported node count depends on the actual case execution rather than a hardcoded node list.
- `stagewarden/prince2_benchmark.py` now includes the full runtime payload for every case plus a rendered `detail` block that spells out nodes, roles, parent links, inbox/outbox counts, transitions, provider usage, provider-model variants, token totals, and timing in plain text.
- `data/prince2_benchmark_baseline.json` now uses more complex PRINCE2 prompts, and the escalation case explicitly includes `validate/review` language so the policy checker still marks it allowed while requiring escalation.
- `data/prince2_benchmark_baseline.json` now also includes an `advanced` suite built from public cloud-migration, records-governance, data-transformation, and procurement-delay traces.
- `data/prince2_benchmark_baseline.json` now also includes a `stress` suite with combined governance, recovery, and stakeholder-pressure cases.
- `data/prince2_benchmark_baseline.json` now also includes a `regulatory` suite with secure-by-design, DPIA, AI governance, and wet-run compliance cases.
- `data/prince2_benchmark_baseline.json` now also includes a `regulatory_stress` suite that mixes privacy incidents, audit readiness, AI change control, and compliance wet-run pressure.
- `data/prince2_benchmark_baseline.json` now also includes a `legal_stress` suite that mixes legal hold, contract risk, disclosure pressure, evidence preservation, and board escalation.
- `data/prince2_benchmark_baseline.json` now also includes an `incident_response` suite that mixes breach handling, outage recovery, rollback control, evidence preservation, and operational escalation.
- `data/prince2_benchmark_baseline.json` now also includes a `vendor_failure` suite that mixes supplier collapse, third-party risk, contract renegotiation, fallback planning, and board escalation.
- `data/prince2_benchmark_baseline.json` now also includes a `multi_vendor_crisis` suite that mixes cascading supplier failure, shared dependencies, fallback governance, and urgent board recovery decisions.
- `data/prince2_benchmark_baseline.json` now also includes a `supply_chain_failure` suite that mixes supply shortages, logistics collapse, procurement delays, inventory gaps, and continuity planning.
- `data/prince2_benchmark_baseline.json` now also includes a `regulatory_war_room` suite that mixes live board-room escalation, breach response, vendor risk, legal hold, and continuity control.
- `data/prince2_benchmark_baseline.json` now also includes a `board_crisis` suite that mixes quorum failure, executive escalation, crisis authority, and recovery decisions under pressure.
- `stagewarden/router.py` now scores routes dynamically with regulatory-aware profile detection and catalog-driven variant selection while preserving deterministic behavior for non-regulatory prompts.
- `stagewarden/provider_registry.py` now derives local model discovery automatically from Ollama plus LM Studio, and it now selects provider variants from catalog/runtime scores instead of preset model-name tables.
- `stagewarden/tools/system.py` adds the new cross-platform system utilities and gracefully falls back when optional deps are missing.
- `stagewarden/tools/external_io.py` adds hash/archive utilities and keeps the old download/checksum/compress/search behavior intact.
- `stagewarden/tools/browser.py` adds fetch/open/screenshot browser utilities with optional Playwright integration.
- `stagewarden/prince2_benchmark.py` now derives the project assurance assignment from the router instead of pinning it to `openai:gpt-5.4-mini`, and it now uses the router's active model set instead of a hardcoded `["local", "openai"]` whitelist; `stagewarden/modelprefs.py` now also derives role defaults from dynamic `provider_model_specs` scoring instead of hardcoded role-to-model tables; the current run shows `openai:gpt-5.4-nano` and one `cheap:openai/gpt-5.4-nano` assignment.
- `stagewarden/executor.py` now uses a structured response-quality scorer for completion attempts, and repeated insufficiency signals from critic/review/closure checks escalate first by variant and then by provider when the prompt still needs a stronger model; the score is now surfaced in the PRINCE2 benchmark report for completion cases.
- `stagewarden/executor.py` now verifies mutating file, shell, git-commit, and multi-file patch actions after execution, and it fails when the workspace proof is missing or mismatched.
- `stagewarden/prince2.py` now explicitly treats refactoring as a permanent cyclic phase across nodes, roles, stages, and microtasks inside the PRINCE2 checklist policy.
- `tests/test_provider_registry.py` now covers dynamic catalog presets plus automatic Ollama and LM Studio discovery.
- `tests/test_trace_cli.py`, `tests/test_prince2.py`, `tests/test_json_schema_registry.py`, and `stagewarden/commands.py` now cover the PRINCE2 benchmark command and schema registration.
- `tests/test_persistence.py`, `tests/test_prince2.py`, `tests/test_trace_cli.py`, `stagewarden/main.py`, `stagewarden/project_handoff.py`, `stagewarden/project_handoff_state.py`, `stagewarden/project_handoff_views.py`, `stagewarden/project_handoff_runtime.py`, `stagewarden/prince2.py`, `stagewarden/commands.py`, and `stagewarden/json_schema_registry.py` now cover project-budget handling and user-question/answer flow.
- `tests/test_trace_cli.py` now also covers `project start` clarification persistence.
- `tests/test_trace_cli.py` now also covers AI-assisted project-tree clarification persistence.
- `python3 -m stagewarden.main --prince2-benchmark` now prints the full default benchmark report with structured runtime data and readable per-case node/transition detail.
- The PRINCE2 benchmark tests pass after the escalation-prompt fix, advanced-suite expansion, stress-suite expansion, regulatory-suite expansion, and regulatory_stress-suite expansion; the full unittest suite still has one flaky live OpenRouter test unrelated to this slice.

## Recent changes
- `stagewarden/project/role_flow.py`: extracted the PRINCE2 tolerance margin set/reset helpers out of `main.py`.
- `stagewarden/agent_setup_views.py`: extracted the agent workspace setup and runtime permission refresh helpers out of `main.py`.
- `stagewarden/json_schema_registry.py`: extracted the shared `with_json_schema()` helper out of `main.py`.
- `stagewarden/model_views.py`: now owns the model preference load/save/apply helpers, the catalog option suffix helper, and the PRINCE2 role-sync helpers that were still living in `main.py`.
- `stagewarden/command_views.py`: now owns the shared `parse_limit` helper and `stagewarden/cli_dispatch.py`: now owns the LJSON path helpers that were still living in `main.py`.
- `stagewarden/ui_views.py`: now owns `interactive_help_text`, which was still living in `main.py`.
- `stagewarden/shell_views.py`: now owns the shell backend settings/report helpers that were still living in `main.py`.
- `stagewarden/cli_dispatch.py`: project tree proposal now persists the clarification question when AI-assisted proposal still needs brief clarification.
- `stagewarden/project/tree_flow.py`: project tree proposal render now prints the clarification question when one exists.
- `stagewarden/model_views.py`: extracted the cloud-priority model chooser out of `main.py`.
- `stagewarden/status_views.py`: extracted the agent baseline render helper out of `main.py`.
- `stagewarden/project_handoff_state.py`: extracted the persisted budget, goal, and user-question state helpers out of `project_handoff.py`.
- `stagewarden/project_handoff.py`: now forwards the state helpers to `project_handoff_state.py` instead of keeping the full bodies inline.
- `stagewarden/project_handoff_views.py`: extracted the handoff summary and reporting/rendering helpers out of `project_handoff.py`.
- `stagewarden/model_views.py`: scaffolded the model/catalog/provider-selection extraction target that is still living in `main.py`.
- `stagewarden/command_dispatch.py`: extracted tool parsing/execution for external-io, browser, watch, and system commands out of `main.py`.
- `stagewarden/tool_reports.py`: extracted tool result formatting and handoff evidence recording for the same tool families.
- `stagewarden/project_state_views.py`: extracted goal, budget, and question state/report helpers from `main.py`.
- `stagewarden/executor_quality.py`: extracted the response-quality scorer from `executor.py`.
- `stagewarden/main.py`: now imports the dispatch/report helpers instead of keeping duplicated parser/executor bodies inline, and the focused validation batch passed after wiring the new callbacks through the shell and JSON paths.
- `stagewarden/shell_views.py`: extracted the permission approval, rate-limit decision, and interactive completion helpers out of `main.py` so the interactive shell owns its own approval and completion flow.
- `stagewarden/executor.py`: added post-action verification for mutating file, shell, git-commit, and multi-file patch actions.
- `stagewarden/prince2.py`: added an explicit cyclic refactor rule to the PRINCE2 adaptation policy and controls.
- `tests/test_executor.py`: added regression coverage for file read-back verification, verification failure on mismatched read-back, shell status-change verification, and git commit HEAD advancement.
- `stagewarden/main.py`: added project budget commands plus `question`/`answer` handling in both the shell and direct CLI paths, and the status renderers now show the current user-question state.
- `stagewarden/main.py`: added `project start` clarification persistence so incomplete briefs now store a pending question and show it in the blocked output.
- `stagewarden/main.py`: added `project tree propose --ai` clarification persistence so incomplete briefs now store a pending question and show it in the blocked output.
- `stagewarden/main.py`: added `project brief` guidance so the next missing field is shown after each edit and in the brief summary, and it is exposed in JSON.
- `stagewarden/main.py`: added `project start` and `project tree propose --ai` JSON guidance for the next missing field or gap.
- `stagewarden/project_handoff.py`: added persisted project budget and pending user-question state, including ask/answer helpers and stage-view reporting.
- `stagewarden/project/role_tree_views.py`: extracted the remaining PRINCE2 role domains/tree/baseline render helpers out of `main.py`.
- `stagewarden/project/design_flow.py`: extracted the project design packet/report helpers out of `main.py`, and then also took over the local execution candidates report helper.
- `stagewarden/model_views.py`: extracted the catalog-entry display helper out of `main.py`.
- `stagewarden/project/role_flow.py`: extracted the PRINCE2 role-node remove helper out of `main.py`.
- `stagewarden/project/role_flow.py`: extracted the PRINCE2 role baseline builder and node mutation helpers out of `main.py`.
- `stagewarden/extension_views.py`: extracted the extension discovery/report helpers out of `main.py`.
- `stagewarden/cli_dispatch.py`: now routes `extensions` through the dedicated extension module instead of `main.py`.
- `stagewarden/status_views.py`: extracted the source reference manifest helper out of `main.py`.
- `stagewarden/model_views.py`: extracted the provider-model display helpers out of `main.py`.
- `stagewarden/project/role_flow.py`: restored the PRINCE2 role shell contract expected by the battery, and `stagewarden/project_handoff_runtime.py` now exposes `threat_count` in antagonist decision KPIs.
- `stagewarden/status_views.py`: extracted the first status/dashboard/statusline/overview/health helper slice, the `preflight`, `report`, and `doctor` helper slice, and the model-usage/cost-sidebar/full-status helper slice, while `stagewarden/main.py` shadows the old bodies with wrappers into that module.
- `stagewarden/main.py`: now delegates the remaining PRINCE2 tree/baseline render helpers to `stagewarden/project/role_tree_views.py`.
- `stagewarden/main.py`: now delegates the project design packet/report helpers to `stagewarden/project/design_flow.py`.
- `stagewarden/project/tree_flow.py`, `stagewarden/project/role_flow.py`, `stagewarden/project/start_flow.py`, and `stagewarden/project/role_runtime_views.py`: now point the shared baseline/fallback rendering at `stagewarden/project/role_tree_views.py`.
- `stagewarden/main.py`: restored `_focus_snapshot` after the status cleanup so the battery/resume paths keep working.
- `stagewarden/main.py`: removed the duplicated legacy `overview/health/preflight/report` bodies after the status split, leaving only the wrapper layer at the end of the file.
- `stagewarden/prince2.py`: added clarification questions to the task assessment path so vague tasks can pause instead of going straight to rejection.
- `tests/test_persistence.py`: added persistence coverage for project budget and user-question roundtrips.
- `tests/test_trace_cli.py`: added shell coverage for budget control and user-question answer/resume flow.
- `tests/test_trace_cli.py`: added regression coverage for `project brief` showing the next missing field in both text and JSON.
- `tests/test_trace_cli.py`: added regression coverage for `project start` and `project tree propose --ai` JSON next-field guidance.
- `tests/test_trace_cli.py`: broader regression batch covering the brief/start/tree flows passed after the JSON guidance refactor.
- `tests/test_prince2.py`: updated the vague-task test so it expects a clarification pause instead of a hard rejection.
- `stagewarden/commands.py`: exposed the budget, question, and answer commands in the catalog and help text.
- `stagewarden/json_schema_registry.py`: registered the budget, question, and answer JSON schema names.
- `stagewarden/modelprefs.py`: accepted `manual_min` and `blocked` as first-class PRINCE2 assignment modes.
- `stagewarden/executor.py`: skips blocked PRINCE2 role assignments during routing.
- `stagewarden/role_tree.py`: added mnemonic/team metadata to nodes, tree rendering, and matrix rendering.
- `stagewarden/main.py`: surfaced mnemonic/team metadata in role commands and node detail views, added the cost sidebar/status summary, and added the node cost breakdown to `status full`.
- `stagewarden/project_handoff.py`: rewrote node messages into a chat-like transcript and surfaced node cost/token visibility in runtime views.
- `tests/test_executor.py`: added regression coverage for blocked role assignments being skipped.
- `tests/test_trace_cli.py`: added regression coverage for blocked mode rendering plus chat-style node messages.
- `stagewarden/modelprefs.py`: prepared for a third PRINCE2 assignment mode and broader role-tree normalization.
- `stagewarden/project_handoff.py`: already contains node runtime cost/token reporting that can be expanded into a chat-like message transcript.
- `stagewarden/role_tree.py` and `stagewarden/main.py`: currently expose the PRINCE2 tree, baseline, and node detail, but they still need mnemonic/team metadata surfaced consistently.
- `stagewarden/command_dispatch.py`: extracted command parsing/execution helpers for the common tool families.
- `stagewarden/tool_reports.py`: extracted command reporting/evidence helpers for the common tool families.
- `stagewarden/main.py`: added live tree decomposition nodes, continuous adaptation metadata, and richer project-tree reporting.
- `stagewarden/prince2.py`: tightened the adaptation policy, stage plan, controls, and boundary review language toward smallest-task decomposition.
- `stagewarden/modelprefs.py`: preserved decomposition and adaptation metadata when normalizing the approved role-tree baseline.
- `tests/test_trace_cli.py`: added regression coverage for micro-task decomposition and refresh-on-brief-change behavior.
- `stagewarden/openrouter_benchmark.py`: added opt-in JSONL history tracking and regression comparison.
- `stagewarden/main.py`: added `--openrouter-benchmark-history` and wired it into the live benchmark command.
- `data/openrouter_benchmark_baseline.json`: added per-suite `regression_tolerance` values alongside the 3-suite public baseline.
- `stagewarden/prince2_benchmark.py`: added a local PRINCE2 benchmark runner with prompt-driven governance and assurance cases.
- `stagewarden/main.py`: added `--prince2-benchmark` and `--prince2-benchmark-output`.
- `data/prince2_benchmark_baseline.json`: added the baseline suites and prompt cases for PRINCE2 benchmark coverage.
- `stagewarden/prince2_benchmark.py`: expanded the default report with the full runtime payload, dynamic orchestration selection, and rendered node/transition detail for every case.
- `data/prince2_benchmark_baseline.json`: rewrote the PRINCE2 prompts to be more complex and evaluative while preserving checker compatibility.
- `data/prince2_benchmark_baseline.json`: added the `advanced` suite based on public traces from Welsh Government, Dedalus/NHS, Staffordshire, Surrey, and World Bank case material.
- `data/prince2_benchmark_baseline.json`: added the `stress` suite with combined governance, recovery, and stakeholder-pressure cases.
- `data/prince2_benchmark_baseline.json`: added the `regulatory` suite with secure-by-design, privacy, AI governance, and compliance wet-run cases.
- `data/prince2_benchmark_baseline.json`: added the `regulatory_stress` suite with privacy, audit, AI governance, and wet-run pressure cases.
- `data/prince2_benchmark_baseline.json`: added the `legal_stress` suite with legal hold, contract risk, disclosure, and evidence-preservation cases.
- `data/prince2_benchmark_baseline.json`: added the `incident_response` suite with breach, outage, rollback, and incident-response cases.
- `data/prince2_benchmark_baseline.json`: added the `vendor_failure` suite with supplier collapse, third-party risk, and contingency cases.
- `data/prince2_benchmark_baseline.json`: added the `multi_vendor_crisis` suite with cascading supplier failure and shared-dependency cases.
- `data/prince2_benchmark_baseline.json`: added the `supply_chain_failure` suite with logistics, inventory, and continuity cases.
- `data/prince2_benchmark_baseline.json`: added the `regulatory_war_room` suite with live escalation, breach, vendor, and continuity cases.
- `data/prince2_benchmark_baseline.json`: added the `board_crisis` suite with quorum failure, executive recovery, and board-authority cases.
- `stagewarden/router.py`: added a regulatory-aware route recommendation path and catalog-aware variant scoring.
- `stagewarden/prince2_benchmark.py`: replaced the fixed project-assurance assignment with router-driven selection.
- `stagewarden/prince2_benchmark.py`: replaced the fixed `local/openai` benchmark whitelist with router-derived active models.
- `stagewarden/modelprefs.py`: replaced hardcoded role-to-model defaults with dynamic scoring over provider model specs.
- `stagewarden/executor.py`: added a structured completion-quality scorer plus insufficiency-aware escalation so weak or blocked responses can move to stronger variants/providers on retry, and surfaced the quality score in the benchmark report.
- `stagewarden/commands.py`: exposed `prince2 benchmark` in the command catalog.
- `stagewarden/json_schema_registry.py`: registered the new `prince2 benchmark` schema.
- `tests/test_prince2.py`: added a direct runner assertion for the PRINCE2 benchmark baseline.
- `tests/test_prince2.py`: added a regression test for the complex escalation prompt with validation language.
- `tests/test_router.py`: added a regulatory routing regression check.
- `tests/test_trace_cli.py`: added CLI coverage for `--prince2-benchmark` and the detail block.
- `tests/test_json_schema_registry.py`: updated registry coverage for the new schema command.

## Important files
- `stagewarden/openrouter_benchmark.py`: live benchmark runner, history writer, and regression comparator.
- `data/openrouter_benchmark_baseline.json`: public prompt baseline used by the benchmark.
- `stagewarden/prince2_benchmark.py`: local PRINCE2 benchmark runner and executor harness.
- `data/prince2_benchmark_baseline.json`: prompt-driven PRINCE2 benchmark baseline.
- `tests/test_trace_cli.py`: CLI, history, and smoke-coverage assertions.
- `tests/test_prince2.py`: PRINCE2 policy and benchmark assertions.
- `tests/test_json_schema_registry.py`: schema command coverage.
- `stagewarden/commands.py`: command catalog exposure for `prince2 benchmark`.
- `scripts/test_chatgpt_flow.sh`: live smoke entrypoint.
- `stagewarden/json_schema_registry.py`: schema contract registry for machine-readable outputs.

## Technical decisions
- Decision: treat `blocked` as a first-class PRINCE2 assignment mode in addition to `auto` and `manual`.
  - Reason: a node-level assignment must be able to opt out of active routing, not only express a provider/model choice.
  - Trade-offs: the routing code needs to treat blocked assignments as non-routable, but the UI can still show the blocked target for auditability.
- Decision: surface mnemonic and team metadata on every node.
  - Reason: the user wants complete visibility into name, role, and team membership for every PRINCE2 node.
  - Trade-offs: the tree/report rows get wider, but the node identity becomes much easier to audit.
- Decision: render node messages as a chat-like transcript by default.
  - Reason: inbox/outbox tuples are too terse for operational review; a transcript makes message flow and responsibility clearer.
  - Trade-offs: the shell output is longer, but it matches the requested visibility model.
- Decision: keep cost and business-case control visible in the runtime report path for automatic and semi-automatic routing.
  - Reason: escalation should never hide the cost impact on the business case.
  - Trade-offs: more report fields, but better governance visibility.
- Decision: extract tool command parsing and execution into `stagewarden/command_dispatch.py`.
  - Reason: `main.py` had become too dense with nearly identical dispatch blocks.
  - Trade-offs: one more module to maintain, but the orchestration entrypoint is much easier to read.
- Decision: use a fixed OpenRouter model in the live test wrappers.
  - Reason: `openrouter/auto` had shown flaky routing behavior on some prompts.
  - Trade-offs: less routing variance in tests, but still real OpenRouter traffic.
- Decision: keep the benchmark output keyed by suite id.
  - Reason: it makes comparisons across benchmark families explicit.
  - Trade-offs: slightly larger report, but clearer downstream parsing.
- Decision: make history tracking opt-in via `--openrouter-benchmark-history`.
  - Reason: the benchmark should stay side-effect free unless the caller explicitly wants durable snapshots.
  - Trade-offs: one extra CLI flag, but no accidental runtime files.
- Decision: fail the benchmark when the current snapshot regresses against the previous snapshot.
  - Reason: the benchmark is meant to detect real quality drift, not just threshold failures.
  - Trade-offs: stricter gating, but much better baseline control over time.
- Decision: make the PRINCE2 benchmark prompt-driven and local.
  - Reason: PRINCE2 needs to measure governance, critic gating, wet-run evidence, and prompt-packet context, not just answer quality.
  - Trade-offs: the cases are synthetic, but they exercise the actual executor and critic paths deterministically.
- Decision: include a recovery suite that uses the real agent recovery lane.
  - Reason: PRINCE2 should measure exception handling and recovery closure, not only steady-state execution.
  - Trade-offs: the benchmark is slower, but it covers the flow that matters when a stage goes wrong.
- Decision: include node runtime and transition snapshots by default.
  - Reason: the benchmark should be useful for analysis and statistics without requiring a separate inspection command.
  - Trade-offs: the JSON is larger, but every case now carries the context needed to compare nodes, roles, and transitions over time.
  - Verification: `python3 -m stagewarden.main --prince2-benchmark` now emits the full runtime payload and readable node/transition detail for every case by default.
- Decision: derive benchmark orchestration from the live runtime graph rather than a fixed node list.
  - Reason: the node count should follow actual case execution and prompt-driven state changes.
  - Trade-offs: counts can differ across cases, but the report now reflects real orchestration instead of a static slice.
- Decision: keep the PRINCE2 escalation case complex but explicitly validated.
  - Reason: the benchmark should remain realistic and evaluative without tripping the policy gate on missing validation language.
  - Trade-offs: the prompt is slightly more verbose, but it stays complex while still exercising allowed+escalate behavior.
- Decision: add an `advanced` benchmark suite sourced from public project traces.
  - Reason: the baseline needed harder, more realistic cases with conflict, recovery, and governance pressure.
  - Trade-offs: more verbose prompts and more cases to maintain, but better coverage for real PRINCE2 stress conditions.
- Decision: add a `stress` suite that mixes multiple trace themes in one benchmark family.
  - Reason: a second layer of harder cases helps catch regressions in combined governance, recovery, and stakeholder pressure scenarios.
  - Trade-offs: the baseline grows again, but the benchmark becomes more representative of real project turbulence.
- Decision: add a `regulatory` suite and make the router compliance-aware.
  - Reason: regulatory work is where model selection should bias toward deeper reasoning, auditability, and better evidence handling.
  - Trade-offs: the router is a little more complex, but it stays deterministic for non-regulatory prompts and becomes more useful where it matters.
- Decision: remove the hardcoded `openai:gpt-5.4-mini` benchmark override and derive the project-assurance assignment from the router.
  - Reason: the old setup forced the same model regardless of case complexity and hid actual routing behavior.
  - Trade-offs: the benchmark is more dynamic and less repetitive, but model usage can vary between runs.
- Decision: remove the hardcoded `["local", "openai"]` benchmark whitelist and use the router's active model set.
  - Reason: model selection should follow the live router/config state rather than a benchmark-specific allowlist.
  - Trade-offs: the harness is more dynamic, but output can vary as the active model inventory changes.
- Decision: remove hardcoded role-to-model tables from `modelprefs` and derive defaults from provider model specs.
  - Reason: role defaults should follow available model metadata instead of a fixed mapping.
  - Trade-offs: the default model selection is more adaptive, but model choice can change as the registry changes.
- Decision: remove hardcoded variant presets from the router and provider registry.
  - Reason: model variants should be chosen from live catalog/runtime scores instead of static names like `gpt-5.4-mini` or `opusplan`.
  - Trade-offs: variant selection is more adaptive, but model choice can shift as the catalog changes.
- Decision: escalate on insufficiency signals, not only on hard failure counts.
  - Reason: a node response can be technically valid but still too weak for the prompt, and that should trigger a stronger retry path.
  - Trade-offs: the executor is slightly more opinionated, but retry routing now reacts to critic and closure evidence instead of only API failures.
- Decision: gate the quality scorer only on completion attempts.
  - Reason: file and inspection actions are valid intermediate work and should not be downgraded by the completion rubric.
  - Trade-offs: the scorer is narrower, but it avoids false positives on operational steps while still catching weak closures.
- Decision: expose response-quality scores in the PRINCE2 benchmark report.
  - Reason: the report should show why a completion passed or failed without a second inspection command.
  - Trade-offs: the per-case JSON gets slightly larger, but the benchmark becomes more explainable.
- Decision: make the project tree proposal emit explicit micro-task decomposition nodes and live adaptation metadata.
  - Reason: the tree should show the smallest independent work packages, not just describe them in prose.
  - Trade-offs: the proposal tree grows, but the decomposition and refresh behavior are visible and auditable.
- Decision: preserve decomposition and adaptation metadata in the approved role-tree baseline.
  - Reason: the same policy must survive persistence, not only the transient proposal.
  - Trade-offs: the baseline JSON gets a bit richer, but the approved tree remains explainable and refresh-aware.
- Decision: discover local models automatically from both Ollama and LM Studio.
  - Reason: local availability should follow whichever local runtime is actually reachable without manual wiring.
  - Trade-offs: local model lists can change at runtime, but the local path now reflects the real machine state.
- Decision: add a `regulatory_stress` suite to combine compliance, privacy, audit, and wet-run pressure in a single benchmark family.
  - Reason: the benchmark needed at least one harder family that forces the router and executor to deal with overlapping governance constraints.
  - Trade-offs: the baseline grows again, but the resulting cases are closer to the real conflicts the project is meant to handle.
- Decision: add a `legal_stress` suite to force legal-hold, contract, and disclosure pressure through the same PRINCE2 controls.
  - Reason: legal and contractual conflict is another real-world stress axis that should influence routing and recovery behavior.
  - Trade-offs: the benchmark grows again, but the model-selection path now sees another high-pressure governance signal.
- Decision: add an `incident_response` suite to force breach, outage, and rollback pressure through the same PRINCE2 controls.
  - Reason: incident handling is another high-pressure path where the router should prefer more capable providers and the benchmark should verify recovery behavior.
  - Trade-offs: the benchmark grows again, but it now reflects operational incidents in addition to compliance and legal stress.
- Decision: add a `vendor_failure` suite to force supplier collapse and third-party risk through the same PRINCE2 controls.
  - Reason: vendor failure is a realistic delivery shock that should influence routing, recovery planning, and board escalation.
  - Trade-offs: the benchmark grows again, but it now covers contingency behavior under supplier pressure.
- Decision: add a `multi_vendor_crisis` suite to force cascading supplier failure and dependency collapse through the same PRINCE2 controls.
  - Reason: multi-supplier failures are a harsher version of vendor risk and should stress the router and recovery paths further.
  - Trade-offs: the benchmark grows again, but it now covers coordinated fallback behavior across multiple dependencies.
- Decision: add a `supply_chain_failure` suite to force logistics, inventory, and procurement pressure through the same PRINCE2 controls.
  - Reason: supply-chain shocks are another realistic continuity hazard that should influence routing and recovery planning.
  - Trade-offs: the benchmark grows again, but it now covers procurement and logistics continuity under pressure.
- Decision: add a `regulatory_war_room` suite to combine breach, vendor outage, legal hold, and regulatory escalation in one benchmark family.
  - Reason: the hardest real-world failures are the ones where multiple governance paths collide at once.
  - Trade-offs: the benchmark grows again, but it now stresses the router and executor with a true crisis-room blend.
- Decision: add a `board_crisis` suite to combine quorum failure, executive escalation, and board-authority pressure in one benchmark family.
  - Reason: board deadlock is a distinct failure mode that should drive routing and recovery behavior.
  - Trade-offs: the benchmark grows again, but it now covers governance failure at the top of the decision chain.

## Open issues
- Bugs: none known in the current blocked/manual_min/mnemonic/chat/cost-sidebar/status-full slice.
- Risks: TruthfulQA-style prompts and PRINCE2 wet-run markers can still be sensitive to wording, so any future prompt edits should be re-wet-run before landing.
- Risks: dynamic local discovery now depends on whichever of Ollama or LM Studio is actually reachable on the machine, so local catalog changes can affect routing and should be smoke-tested.
- Risks: the new tree decomposition policy can add more delegated nodes as briefs get bigger, so the proposal should stay proportional.
- Risks: the agent codebase is getting hard to read as tools and dispatch paths keep growing; refactoring must stay a continuous cyclic activity across the full organizational tree, and the next major slice should keep trimming `main.py` while also organizing related code into subfolders because the surface is still spreading.
- Unknowns: none tracked for the current slice.

## Next steps
1. Keep the verification helper conservative for shell commands so read-only commands are not mislabeled as writes.
2. Extend the same post-action verification path to any new mutating tool action types that appear later.
3. Keep `AGENT_HANDOFF.md`, `HANDOFF.md`, and `.stagewarden_handoff.json` synchronized after the next change.
4. `Ritornando al discorso funzionale di Stagewarden: utente fa richiesta > agente analizza richiesta ma sopratutto tutti i punti ambigui; l'IA non deve fare assunzioni e deve chiedere all'utente tutte le delucidazioni; solo quando non ci sono punti ambigui parte con il progetto; suddivide il progetto in microtask o stage; se nascono punti ambigui ci si ferma e si chiede all'utente delucidazioni, mai assunzioni; l'utente puo' fare nuove richieste che modificano il progetto quindi si ripete l'intero ciclo; i nodi possono modificare gli stage loro assegnati e possono essere anche cancellati o creati nuovi nodi in base alle nuove specifiche di progetto; l'intero sistema deve essere il più dinamico possibile continuando a seguire le regole PRINCE2 quindi anche tolleranze, limiti di stage, report nodo team e ad pm, business case, ecc... rileggi libro PRINCE2 per tutte le regole.`
5. Continue the refactor by trimming the remaining large helpers in `main.py` and related dispatch/report modules so the codebase stays readable as the surface grows.
6. Organize related code into subfolders by concern so the growing module surface stays easy to navigate.
7. Keep refactoring as a cyclic phase for the entire Stagewarden tree, including nodes, roles, stages, and microtasks, so organizational structure stays dynamically readable over time.

## Commands
```bash
./scripts/test_chatgpt_flow.sh
python3 -m unittest discover -s tests
python3 -m unittest tests.test_provider_registry tests.test_router
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_openrouter_benchmark_cli_reports_multi_suite_baseline
python3 -m stagewarden.main --prince2-benchmark
python3 -m unittest tests.test_prince2.Prince2Tests.test_prince2_benchmark_reports_prompt_baseline
python3 -m unittest tests.test_prince2.Prince2Tests.test_policy_allows_complex_escalation_prompt_with_validation_language
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_prince2_benchmark_cli_reports_prompt_baseline
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_project_brief_commands_persist_and_feed_project_design tests.test_trace_cli.TraceAndCliTests.test_project_brief_set_reports_next_missing_field tests.test_trace_cli.TraceAndCliTests.test_project_tree_propose_reports_missing_brief_gaps tests.test_trace_cli.TraceAndCliTests.test_project_tree_propose_ai_requests_clarification_for_missing_brief tests.test_trace_cli.TraceAndCliTests.test_project_start_requests_clarification_for_missing_brief tests.test_trace_cli.TraceAndCliTests.test_project_tree_approve_blocks_until_brief_is_complete tests.test_trace_cli.TraceAndCliTests.test_project_tree_approve_persists_reviewed_proposal_baseline
```
