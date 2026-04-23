# Stagewarden Handoff

Author: Donato Pepe

License: MIT

Last updated: 2026-04-22

## Purpose

This file is the human-readable project handoff for Stagewarden. It complements the runtime `.stagewarden_handoff.json` file and must stay updated with implementation decisions, pending work, recovery lanes, validation evidence, and Codex/Claude-inspired behaviours to reproduce.

The working rule is PRINCE2-style controlled execution:

- plan work as explicit stages
- execute only stages that are `ready` or `in_progress`
- persist handoff context continuously
- record git boundaries
- require wet-run validation
- create recovery lanes for exception paths
- keep model handoff context available without requiring manual resume
- adapt governance to task size and risk: small work stays lightweight, complex work gets stronger controls
- reduce ceremony, never principles
- communication and traceability rule: the AI agent must inform the user of every action it is about to perform, every material action it performs, and every relevant result; each action must also be recorded in handoff/log context with enough evidence to reconstruct what happened
- no silent action rule: shell commands, file edits, model handoffs, role-tree changes, git snapshots, web/download/compression operations, approvals, force overrides, and recovery actions must never be invisible to the user or absent from handoff
- model roles are not limited to a flat one-role/one-model map: PRINCE2 organization can be hierarchical, delegated, combined, or split by domain while preserving accountability
- clarification gate: for every user request, Stagewarden must identify all ambiguous points and ask every necessary clarification before execution starts; work may begin only after no material ambiguity remains or the user explicitly authorizes assumptions
- clarification gate must stay proportional: simple unambiguous requests can proceed immediately, but any uncertainty about scope, files, provider/model/account, permissions, destructive effects, external network use, expected output, validation/wet-run, git/push boundary, or PRINCE2 role ownership must be resolved first
- user-experience baseline is Codex CLI plus Claude Code: command feel, shell flow, status surfaces, transcript visibility, auth flow, model/provider selection, and conversational shell ergonomics must be learned from the locally cloned sources and reproduced in Stagewarden where compatible with project goals

## Current Baseline

- Repository: `https://github.com/donatopepe/Stagewarden`
- Main package: `stagewarden`
- Runtime CLI: `stagewarden`
- Runtime handoff: `.stagewarden_handoff.json`
- Human handoff: `HANDOFF.md`
- Runtime model config: `.stagewarden_models.json`
- Runtime permission config: `.stagewarden_settings.json`
- Runtime trace: `.stagewarden_trace.ljson`
- Runtime PRINCE2 PID: `.stagewarden_prince2_pid.json`
- Agent manifesto: `AGENT_MANIFESTO.md`
- Agent policy: `AGENT_POLICY.md`
- Machine-readable policy: `AGENT_POLICY.json`
- Local-only Codex resume helpers: `codex-resume.command` and `codex-resume.bat`

Latest known baseline at the time of this handoff:

- Local implementation snapshot: `9b0861d chore: ignore codex resume bat`
- Last confirmed pushed baseline before this pass: `9b0861d chore: ignore codex resume bat`

## Current Implementation Pass

Status: pushed, continuing with incremental blocks

Implemented in this pass:

- Added local Codex resume helper files for the active conversation:
- `codex-resume.command`
- `codex-resume.bat`
- Both contain `codex resume 019da0a4-552a-76b0-9cc9-b690a91cb34c`.
- Both files are intentionally ignored by git; only `.gitignore` rules were committed.
- Pushed commits:
- `f2d924e chore: ignore codex resume command`
- `9b0861d chore: ignore codex resume bat`
- Persisted structured provider limit snapshots in `.stagewarden_models.json`.
- Added model-level and account-level limit snapshots with sanitized fields only.
- Captured limit metadata automatically when executor sees provider block messages.
- Exposed persisted limit metadata through `status --full --json`.
- Exposed compact reset/usage fields through `statusline --json`.
- Kept provider status read-only commands free from model calls and token output.

Stored limit snapshot fields:

- `status`
- `reason`
- `blocked_until`
- `primary_window`
- `secondary_window`
- `credits`
- `rate_limit_type`
- `utilization`
- `overage_status`
- `overage_resets_at`
- `overage_disabled_reason`
- `stale`
- `captured_at`
- `raw_message`

Validation evidence:

- `python3 -m unittest tests/test_persistence.py tests/test_executor.py tests/test_trace_cli.py` passed, 108 tests.
- `python3 -m unittest discover -s tests` passed, 203 tests.
- `python3 -m stagewarden.main status --full --json` passed as wet-run.
- `python3 -m stagewarden.main statusline --json` passed as wet-run.

Follow-up implemented after this pass:

- Added `model limits` and `models limits` interactive/CLI commands.
- Added `stagewarden "model limits" --json` machine-readable output.
- Added concise human rendering for provider/account limit state.
- Updated interactive help and README examples.
- Added stale detection for provider limit snapshots based on `captured_at`.
- Added `model limit-record <model> <message>` to persist pasted provider limit messages safely.
- Added `account limit-record <model> <account> <message>` for account-specific provider limits.
- Added `model limit-clear <model>` and `account limit-clear <model> <account>` to remove stored limit snapshots, messages, and temporary blocks.
- Switched `account login chatgpt <profile>` to a Codex-style browser flow backed by `codex login`.
- Switched `account logout chatgpt <profile>` to Codex-backed logout plus local profile marker cleanup.
- Corrected CLI/status terminology: provider and provider-model are now rendered separately.
- Added explicit `provider_model` and `provider_model_selection` fields to model/status JSON reports.
- Route rendering now shows `provider=...` and `provider_model=...` instead of conflating provider with model.
- Added provider-model catalog metadata with supported `reasoning_effort` values.
- Added persisted provider-model params per provider, currently including `reasoning_effort`.
- Added CLI commands `model params`, `model param set`, and `model param clear`.

Additional validation evidence:

- `python3 -m unittest tests/test_trace_cli.py` passed, 78 tests.
- `python3 -m stagewarden.main "model limits" --json` passed as wet-run.
- `python3 -m stagewarden.main "model limits"` passed as wet-run.
- `python3 -m unittest discover -s tests` passed, 204 tests.
- Stale detection validation passed through `test_model_limits_cli_json_outputs_persisted_snapshots`.
- `python3 -m stagewarden.main "model limit-record chatgpt Usage limit reached until 2026-05-01T18:30." --json` passed as wet-run.
- `python3 -m stagewarden.main "model limit-clear chatgpt" --json` passed as wet-run and restored local provider availability.
- `python3 -m unittest discover -s tests` passed, 206 tests.
- `python3 -m unittest tests/test_auth.py tests/test_trace_cli.py` passed, 84 tests after browser-login migration.
- `python3 -m unittest discover -s tests` passed, 209 tests after browser-login migration.
- Interactive wet-run with stubbed `codex` backend confirmed `account login chatgpt personale` updates the active profile and stores a sanitized Codex marker.
- `python3 -m stagewarden.main models --json` passed as wet-run and now exposes `preferred_provider`, `provider_model`, and `provider_model_selection`.
- `python3 -m stagewarden.main statusline --json` passed as wet-run and now exposes active provider/provider-model separately.
- `python3 -m stagewarden.main "model list chatgpt"` passed as wet-run and renders the provider-model catalog plus supported reasoning levels.
- `python3 -m stagewarden.main "model variant chatgpt gpt-5.3-codex"` + `model param set chatgpt reasoning_effort high` + `model params chatgpt` passed as wet-run.
- Interactive guided model selection has been added through `model choose [provider]`, with menu-driven provider, provider-model, and reasoning-effort selection.
- Guided menus now also cover `model preset <provider>` and `account choose [provider]` inside the interactive shell.
- `python3 -m unittest tests/test_trace_cli.py` passed, 86 tests.
- `python3 -m unittest discover -s tests` passed, 214 tests.
- Interactive wet-run passed with `model choose chatgpt`, selecting `gpt-5.4` plus `reasoning_effort=medium`, and `models` then showed the persisted provider-model state.
- `python3 -m unittest tests/test_trace_cli.py` passed again, 88 tests, after adding guided preset/account menus.
- `python3 -m unittest discover -s tests` passed again, 216 tests, after adding guided preset/account menus.
- Interactive wet-run passed with `model preset chatgpt`, selecting `balanced`, and `model params chatgpt` then showed `provider_model=gpt-5.1-codex-mini` plus `reasoning_effort=medium`.
- Interactive wet-run passed with `account choose openai`, selecting `personale`, and `accounts` then showed the active profile change.
- `model preset <provider>` without an explicit preset value now opens the provider-model picker instead of the preset picker.
- Interactive wet-run passed with `model preset chatgpt`, selecting `gpt-5.4`, and `model params chatgpt` then showed `provider_model=gpt-5.4` plus `reasoning_effort=medium`.
- Interactive shell commands now require the `/` prefix in the real shell; input without `/` is treated as a task for the agent loop.
- Test harness compatibility was preserved for scripted `StringIO` command inputs so the shell command suite remains verifiable without changing task semantics.
- `python3 -m unittest tests/test_trace_cli.py` passed again, 88 tests, after slash-command routing.
- `python3 -m unittest discover -s tests` passed again, 216 tests, after slash-command routing.
- Interactive wet-run passed with bare `status`, which was treated as a task and rejected by governance as expected.
- Interactive wet-run passed with `/status`, which was treated as a shell command and rendered the status dashboard.
- `study/` remains developer-only learning material and is not exposed in agent prompts, status, doctor output, or runtime behavior.
- PRINCE2 role routing is implemented as an initial flat baseline: `/roles`, `/roles propose`, `/roles setup`, `/role configure [role]`, `/role clear <role>`, and `/project start`.
- Important correction: this flat baseline is not the final PRINCE2 organization model. Stagewarden must evolve to support role trees, delegated roles, many model assignments per role node, and context scoped by responsibility/domain.
- Role assignments persist provider, provider-model, reasoning parameters, account, mode, and source in `.stagewarden_models.json`.
- Project handoff now synchronizes PRINCE2 role assignments so model calls receive implicit role ownership context without a manual resume.
- Provider rate-limit recovery now records blocked-until metadata, switches automatically to an available provider/account, and asks the user whether to wait/stop when no alternative exists.
- `python3 -m unittest tests/test_trace_cli.py` passed, 91 tests, after role routing and `study/` runtime removal.
- `python3 -m unittest tests/test_persistence.py` passed, 7 tests, after role/handoff persistence.
- `python3 -m unittest tests/test_executor.py` passed, 25 tests, after rate-limit recovery decision support.
- `python3 -m unittest discover -s tests` passed, 220 tests, after role routing and rate-limit recovery.
- `status` now includes a PRINCE2 role baseline section and explicitly suggests `/project start` or `/roles setup` when role ownership is missing.
- Wet-run `python3 -m stagewarden.main status` confirmed the missing-role operational hint in the real workspace.
- `python3 -m unittest tests/test_trace_cli.py` passed, 91 tests, after the status role-baseline section.
- `python3 -m unittest discover -s tests` passed, 220 tests, after the status role-baseline section.
- PRINCE2 role automation now routes execution by role domain: Project Manager for planning/control, Team Manager for implementation, Project Assurance for validation, Change Authority for exceptions/changes/tolerance breaches, Project Executive for business stop-go, Senior User for acceptance/benefits, Senior Supplier for technical feasibility, and Project Support for records/traceability.
- Role-assigned models now receive scoped context only: unrelated risks/issues/exception plans/logs are omitted unless the active PRINCE2 role owns that domain.
- Executor tests verify Team Manager routing uses the configured provider/model/params and does not expose business risk or exception-plan content outside the Team Manager domain.
- `roles domains` now renders each PRINCE2 role responsibility and context boundary so model assignments can be reviewed before project startup.
- `roles domains --json` now exposes the same role-domain matrix with stable fields: command, rule, roles, role, label, responsibility, and context_scope.
- Wet-run `python3 -m stagewarden.main "roles domains"` passed and shows all role domains.
- Wet-run `python3 -m stagewarden.main "roles domains" --json` passed and emits the machine-readable role-domain matrix.
- `python3 -m unittest tests/test_executor.py tests/test_trace_cli.py` passed, 119 tests, after role-domain CLI support.
- `python3 -m unittest tests/test_trace_cli.py` passed, 93 tests, after role-domain JSON support.
- `python3 -m unittest discover -s tests` passed, 223 tests, after role-domain CLI support.
- `sources status` is implemented as a read-only external reference verifier for `docs/source_references.md`.
- `sources status` reports local path presence, Git repository state, HEAD, upstream URL match with `.git` suffix normalization, and shallow-clone state.
- Wet-runs `python3 -m stagewarden.main "sources status"` and `python3 -m stagewarden.main "sources status" --json` passed in the real workspace and reported Caveman, Codex, and Claude references as OK.
- `python3 -m unittest tests/test_trace_cli.py` passed, 92 tests, after the sources status command.
- `python3 -m unittest discover -s tests` passed, 221 tests, after the sources status command.
- Command discovery Phase 1 started: `stagewarden.commands` now provides a structured registry with command name, group, description, usage, aliases, interactive support, JSON support, and handler family.
- `commands` now renders a human command catalog from the registry.
- `commands --json` now emits a machine-readable command catalog for future slash palette/menu integration.
- Interactive slash completion now uses registry phrases as its first source before legacy compatibility phrases.
- Help topics for models, accounts, permissions, handoff/PRINCE2, and git now render command rows from the registry while preserving examples.
- Registry-backed help preserves command aliases such as `handoff export | handoff md`, `resume | resume context | resume --show`, and provider-specific login hints.
- Wet-run `python3 -m stagewarden.main commands` passed in the real workspace.
- Wet-run `python3 -m stagewarden.main commands --json` passed in the real workspace.
- `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_commands_catalog_cli_and_json tests.test_trace_cli.TraceAndCliTests.test_interactive_completion_candidates_include_core_commands` passed after command catalog implementation.
- Wet-run `printf '/help accounts\n/help handoff\n/exit\n' | python3 -m stagewarden.main` passed and confirmed slash-command routing with registry-backed help.
- `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_supports_category_help tests.test_trace_cli.TraceAndCliTests.test_interactive_completion_candidates_include_core_commands tests.test_trace_cli.TraceAndCliTests.test_commands_catalog_cli_and_json` passed after registry-backed help.
- Agent-to-model communication has started migrating from flat prompt concatenation to a structured turn packet in the executor.
- The packet now separates thread start identity, turn context, model context files, handoff summary, stage view, PRINCE2 role automation, scoped registers, typed transcript items, and execution contract.
- Typed transcript items currently include `handoff_log`, `execution_log`, and `tool_transcript`, inspired by Codex thread items and Claude transcript/resume behaviour.
- The renderer remains deterministic plain text for backend compatibility, but the executor no longer builds the prompt as one unstructured block.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/executor.py tests/test_executor.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests/test_executor.py` passed, 27 tests, after structured turn packet adoption.
- Status and resume UX have been upgraded with a shared operational focus snapshot inspired by Codex/Claude status surfaces.
- `status`, `status --full`, `resume --show`, and `resume context` now expose the active route, current step, next action, boundary decision, latest evidence, and active provider-limit state in a more action-oriented form.
- JSON reports now carry a `focus` or `active_route` section so downstream tools and future slash/status widgets can reuse the same snapshot without reparsing prose.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/main.py tests/test_trace_cli.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests/test_trace_cli.py` passed, 104 tests, after status/resume focus snapshot adoption.
- Slash UX has started converging toward Codex/Claude discoverability: a new `/slash [prefix]` command renders a readable slash-command palette with descriptions instead of requiring Tab completion only.
- The slash palette is driven by the structured command registry, so future completion, palette, and help surfaces can share one command source of truth.
- Validation 2026-04-22: `python3 -m unittest tests/test_trace_cli.py` passed, 105 tests, after slash palette adoption.
- Interactive slash completion now has contextual value suggestions for providers, roles, shell backends, and configured account names, instead of only flat prefix matching.
- Completion ranking now prefers exact/prefix matches and useful contextual expansions, moving Stagewarden closer to Codex/Claude guided slash UX.
- Validation 2026-04-22: `python3 -m unittest tests/test_trace_cli.py` passed, 106 tests, after contextual slash completion adoption.
- `/slash` now also renders lightweight operational hints from the current workspace state: enabled providers, active accounts, blocked providers, and command-specific hint summaries where relevant.
- This keeps slash discovery aligned with Codex/Claude-style operator feedback: command discovery plus current runtime context in one surface.
- Validation 2026-04-22: `python3 -m unittest tests/test_trace_cli.py` passed, 106 tests, after slash operational hint adoption.
- Slash completion and palette now expose second-level model guidance: `provider_model` candidates for `model variant` and `reasoning_effort` candidates for `model param set`.
- This brings model selection closer to Codex/Claude guided UX by surfacing valid next choices directly from the provider-model catalog.
- Validation 2026-04-22: `python3 -m unittest tests/test_trace_cli.py` passed, 106 tests, after provider-model and reasoning-effort suggestion adoption.
- Guided menus now render current selection context before choices: enabled providers, preferred provider, active accounts, blocked providers, selected provider, current provider-model, current reasoning effort, and configured accounts.
- `role configure` now also renders the PRINCE2 role responsibility and context scope before asking for provider/model/account, making role assignment decisions explicit and auditable.
- Validation 2026-04-22: `python3 -m unittest tests/test_trace_cli.py` passed, 106 tests, after guided menu context adoption.
- Slash palette now has a reusable JSON report (`slash [prefix] --json`) exposing prefix, workspace context, command entries, aliases, JSON support, handler, and operational hints.
- Text `/slash` rendering is now generated from the same report used by JSON output, avoiding divergence between operator UX and automation surfaces.
- Validation 2026-04-22: `python3 -m unittest tests/test_trace_cli.py` passed, 107 tests, after slash palette JSON report adoption.
- Documentation parity updated for the Codex/Claude-style UX work.
- `README.md` now links to Italian documentation and documents `/slash`, slash JSON output, contextual completion, guided menu context, and `role configure` role-scope visibility.
- Added `README_IT.md` with Italian setup, shell usage, slash UX, model/provider commands, PRINCE2 handoff behaviour, validation rules, JSON examples, and credits.
- Validation 2026-04-22: `python3 -m stagewarden.main "slash mo" --json` passed as a wet-run after documentation update.
- Phase B mini-block started: PRINCE2 role-tree baseline can now be approved and persisted.
- `project start`, `roles propose`, and `roles setup` now persist an approved role-tree baseline after applying role assignments.
- Added `roles tree approve` to approve the current PRINCE2 role tree explicitly.
- Added `roles baseline` and `roles baseline --json` to inspect the persisted baseline.
- The baseline stores tree, authorized flow, readiness check, matrix, approval timestamp, source, status, and version in `.stagewarden_models.json`.
- `.stagewarden_handoff.json` now syncs the same role-tree baseline so future role-routed handoffs have an implicit governance tree without manual resume.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/modelprefs.py stagewarden/project_handoff.py stagewarden/main.py stagewarden/commands.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_roles_tree_approve_persists_role_tree_baseline tests.test_trace_cli.TraceAndCliTests.test_project_start_applies_role_baseline` passed.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "roles baseline"` passed and rendered the missing-baseline guidance.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "roles tree approve" --json` passed and persisted the baseline in the real workspace.
- Validation 2026-04-22: `python3 -m unittest discover -s tests` passed, 250 tests, after role-tree baseline persistence.
- Phase B mini-block continued: executor now reads the approved role-tree baseline before falling back to the flat role map.
- Role-routed prompts now include active node id, parent node, level, accountability boundary, delegated authority, context include rules, and context exclude rules from the approved baseline.
- Baseline node assignment can route provider/provider-model/params even when the flat `prince2_roles` map is absent, preserving implicit PRINCE2 governance handoff.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/executor.py tests/test_executor.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests.test_executor.ExecutorTests.test_executor_prefers_approved_role_tree_baseline_assignment_and_context tests.test_executor.ExecutorTests.test_executor_routes_step_through_configured_prince2_role` passed.
- Validation 2026-04-22: `python3 -m unittest tests/test_executor.py` passed, 28 tests.
- Validation 2026-04-22: `python3 -m unittest discover -s tests` passed, 251 tests, after executor baseline-node routing.
- Phase B mini-block continued: added scriptable delegated role-tree node management.
- `role add-child <parent_node> <role_type> [node_id]` adds a delegated/subordinate node to the approved baseline, inheriting PRINCE2 context rules from the selected role type while preserving parent accountability.
- `role assign <node_id> <provider> <provider_model> [reasoning_effort=<value>] [account=<name>]` assigns a provider-model, params, and optional account to a specific baseline node.
- Baseline checks and matrix can now be recomputed from an arbitrary baseline tree payload, not only from the static flat PRINCE2 layout.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/role_tree.py stagewarden/main.py stagewarden/commands.py tests/test_trace_cli.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_role_add_child_and_assign_updates_role_tree_baseline tests.test_trace_cli.TraceAndCliTests.test_roles_tree_approve_persists_role_tree_baseline` passed.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "role add-child management.project_manager team_manager delivery.docs_team_20260422"` passed in the real workspace.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "role assign delivery.docs_team_20260422 local provider-default"` passed in the real workspace.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "roles baseline" --json` passed and showed the delegated node with assigned local provider.
- Validation 2026-04-22: `python3 -m unittest discover -s tests` passed, 252 tests, after delegated node management.
- Phase B mini-block continued: executor now selects a delegated baseline node when task/step text explicitly mentions the node id.
- This allows multiple nodes with the same PRINCE2 role type, such as several Team Manager sub-teams, while preserving each node's provider-model assignment and context boundary.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/executor.py tests/test_executor.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests.test_executor.ExecutorTests.test_executor_selects_delegated_node_when_step_mentions_node_id tests.test_executor.ExecutorTests.test_executor_prefers_approved_role_tree_baseline_assignment_and_context` passed.
- Validation 2026-04-22: `python3 -m unittest tests/test_executor.py` passed, 29 tests.
- Validation 2026-04-22: `python3 -m unittest discover -s tests` passed, 253 tests, after delegated node selection.
- Phase B mini-block continued: `role add-child` and `role assign` now open guided menus when called without arguments.
- Guided node creation shows the PRINCE2 delegated-node rule, lets the user choose a parent node, choose a role type, and optionally enter a node id.
- Guided node assignment shows the no-context-widening rule, lets the user choose a specific node, provider, provider-model, reasoning effort, and account.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/main.py stagewarden/commands.py tests/test_trace_cli.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_guided_role_node_add_child_and_assign tests.test_trace_cli.TraceAndCliTests.test_role_add_child_and_assign_updates_role_tree_baseline` passed.
- Wet-run note 2026-04-22: unprefixed interactive inputs were correctly treated as natural-language tasks and rejected by the PRINCE2 gate, confirming command/context separation.
- Wet-run 2026-04-22: prefixed interactive flow `/roles propose`, `/role add-child`, `/role assign`, `/roles baseline`, `/exit` passed in the real workspace.
- Validation 2026-04-22: `python3 -m unittest discover -s tests` passed, 254 tests, after guided delegated node menus.
- Phase B mini-block continued: role-tree node assignment now supports `pool=primary`, `pool=reviewer`, and `pool=fallback`.
- `pool=primary` preserves the existing node `assignment`; `pool=reviewer` and `pool=fallback` append routes under `assignment_pool` without changing node context.
- Executor now uses a same-node fallback route when the primary provider is blocked or inactive, preserving PRINCE2 context boundaries.
- Role baseline matrix payload now exposes `reviewer_routes` and `fallback_routes`; note that top-level `roles matrix` still renders the static role layout and a future baseline matrix view should be added.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/main.py stagewarden/executor.py stagewarden/role_tree.py stagewarden/commands.py tests/test_trace_cli.py tests/test_executor.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_role_assign_supports_reviewer_and_fallback_pools tests.test_trace_cli.TraceAndCliTests.test_interactive_shell_guided_role_node_add_child_and_assign tests.test_executor.ExecutorTests.test_executor_uses_node_fallback_pool_when_primary_provider_blocked` passed.
- Wet-run 2026-04-22: CLI `role add-child` plus three `role assign` calls with `pool=primary`, `pool=reviewer`, and `pool=fallback` passed in the real workspace.
- Wet-run 2026-04-22: `roles baseline --json` showed reviewer and fallback routes for `delivery.pool_team_20260422`.
- Validation 2026-04-22: `python3 -m unittest discover -s tests` passed, 256 tests, after role node route pools.
- Phase B mini-block continued: added `roles baseline matrix` and `roles baseline matrix --json` to expose the approved baseline matrix directly, without opening the full baseline payload.
- This closes the visibility gap for delegated nodes and reviewer/fallback pools while keeping `roles matrix` backward-compatible as the static layout view.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/main.py stagewarden/commands.py tests/test_trace_cli.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_roles_baseline_matrix_shows_delegated_nodes_and_route_pools` passed.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "roles baseline matrix" --json` passed in the real workspace and exposed delegated nodes plus route pools directly.
- Validation 2026-04-22: `python3 -m unittest discover -s tests` passed, 257 tests, after baseline matrix command addition.
- Validation 2026-04-22: `python3 -m unittest tests/test_trace_cli.py` passed, 107 tests, after documentation parity update.
- Phase B mini-block continued: added `project design` and `project design --json` as the explicit pre-design packet for future AI-assisted PRINCE2 tree construction.
- `project design` now exposes two mandatory prompt inputs before any AI organization-tree proposal is accepted: `agent_capability_specification` and `project_specification`.
- The report also surfaces `clarification_gaps`, so missing task/governance/runtime context is visible before a model designs or re-baselines the role tree.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/main.py stagewarden/commands.py tests/test_trace_cli.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests/test_trace_cli.py` passed, 113 tests, after project-design packet adoption.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "project design"` passed in the real workspace.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "project design" --json` passed in the real workspace.
- Phase B mini-block continued: `project start` now renders the `project design` packet before applying the automatic PRINCE2 role baseline.
- If `project design` still contains clarification gaps, `project start` now marks the startup baseline as provisional instead of silently hiding the gap.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/main.py tests/test_trace_cli.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_project_start_applies_role_baseline tests.test_trace_cli.TraceAndCliTests.test_project_design_report_exposes_capability_spec_project_spec_and_gaps` passed.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "project start"` passed in the real workspace and rendered the design packet before the approved baseline.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "project start" --json` passed in the real workspace.
- Phase B mini-block continued: added structured `project brief` persistence inside `.stagewarden_handoff.json`.
- `project brief`, `project brief set <field> <value>`, and `project brief clear [field]` now manage the explicit project-specification fields that future AI-assisted tree design must consume.
- `project design` now embeds the persisted brief under `project_specification.brief` and turns missing key brief fields into explicit clarification gaps.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/project_handoff.py stagewarden/main.py stagewarden/commands.py tests/test_trace_cli.py` passed.
- Validation 2026-04-22: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_project_design_report_exposes_capability_spec_project_spec_and_gaps tests.test_trace_cli.TraceAndCliTests.test_project_brief_commands_persist_and_feed_project_design` passed.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "project brief set objective Build a proportional PRINCE2 role tree"` passed in the real workspace.
- Wet-run 2026-04-22: `python3 -m stagewarden.main "project brief"` and `python3 -m stagewarden.main "project brief" --json` passed in the real workspace.
- Validation 2026-04-22: `python3 -m unittest discover -s tests` passed, 259 tests, after project-brief adoption.
- Phase B mini-block continued: added `project tree propose` and `project tree propose --json`.
- The proposal uses the structured project brief plus local proportional PRINCE2 rules to add delegated nodes only when justified by the brief.
- The proposal is review-only: it does not persist the role-tree baseline and explicitly requires user/Project Board approval before persistence.
- Current local rules can propose delegated implementation, validation assurance, user acceptance, and model-routing change-authority nodes.
- Validation 2026-04-23: `python3 -m py_compile stagewarden/main.py stagewarden/commands.py tests/test_trace_cli.py` passed.
- Validation 2026-04-23: `python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_project_tree_propose_builds_proportional_review_proposal_from_brief tests.test_trace_cli.TraceAndCliTests.test_project_tree_propose_reports_missing_brief_gaps` passed.
- Wet-run 2026-04-23: `python3 -m stagewarden.main "project tree propose"` passed in the real workspace and reported missing brief fields as clarification gaps.
- Wet-run 2026-04-23: `python3 -m stagewarden.main "project tree propose" --json` passed in the real workspace.
- Phase B mini-block continued: added `project tree approve` and `project tree approve --force`.
- `project tree approve` blocks when the proportional proposal still has clarification gaps; `--force` persists the baseline with `proposal.forced=true` so the governance exception remains explicit.
- Approved project-tree baselines preserve proposal metadata: source, assumptions, added nodes, clarification gaps, project brief snapshot, and forced flag.
- Validation 2026-04-23: `python3 -m py_compile stagewarden/main.py stagewarden/commands.py stagewarden/modelprefs.py tests/test_trace_cli.py` passed.
- Validation 2026-04-23: targeted project-tree approval tests passed for blocked approval, persisted approval, and proposal generation.
- Wet-run 2026-04-23: `python3 -m stagewarden.main "project tree approve"` blocked in the real workspace because `scope` and `expected_outputs` are missing.
- Wet-run 2026-04-23: `python3 -m stagewarden.main "project tree approve --force"` approved and persisted the proposal baseline with `delivery.implementation_team`.
- Wet-run 2026-04-23: sequential `python3 -m stagewarden.main "roles baseline" --json` confirmed `source=project_tree_approve_force`, 9 nodes, and preserved proposal metadata.
- Phase B mini-block continued: `project start` now uses the controlled `project design -> project tree propose -> project tree approve` path instead of silently applying the static role baseline.
- `project start` blocks startup when the project brief/proposal has unresolved clarification gaps and gives explicit next actions.
- Startup ignores only the expected generative design gaps `missing_role_tree_baseline` and `role_tree_not_ready`, because creating that baseline is the purpose of startup.
- Validation 2026-04-23: targeted project-start and project-tree approval tests passed.
- Wet-run 2026-04-23: `python3 -m stagewarden.main "project start"` blocked in the real workspace because `scope` and `expected_outputs` are still missing.
- Validation 2026-04-23: `python3 -m unittest discover -s tests` passed, 264 tests, after startup gate integration.

Next implementation roadmap:

Roadmap rule:

- Work in grouped implementation blocks, not one-line micro changes. Each group should combine coherent code changes and run one grouped validation pack before commit/push.
- Mini-blocks are still allowed inside a group for reasoning, but they should not force separate commits when one grouped wet-run can validate the whole feature slice.
- Each grouped block must add wet-run evidence, unit tests where feasible, handoff notes, and a git boundary.
- Priority override from the current directive: UX parity with Codex CLI and Claude Code is now the baseline governing principle for all new CLI/shell interaction work.
- Priority order is governed by operational risk: shell/runtime safety first, then PRINCE2 routing, then network/file artifact tools, then UX polish.
- UX parity is not postponed to polish only: when a control surface affects prompting, shell conversation, slash commands, status, auth, resume, or model/provider selection, it must be designed against the Codex/Claude baseline during the implementation phase itself.
- Mandatory transparency: all future implementation blocks must add or preserve user-facing action announcements and durable handoff/log entries for the action path being changed.
- Technical execution order after regrouping on 2026-04-23:
- Remaining grouped blocks: 5.
- Runtime `.stagewarden_handoff.json` currently exposes 6 generic placeholder steps, but the actionable implementation plan is the grouped plan below.
- `G1` Model communication and provider telemetry: finish structured agent<->model turn packets, provider-limit/credit/window persistence, token/context accounting, safe redaction, rate-limit fallback prompts, and richer status/statusline surfaces.
- `G1 test pack`: parser unit tests, stale-limit tests, redaction tests, model packet tests, status JSON schema tests, `status --full --json`, `statusline --json`, `auth status chatgpt --json`, `auth status claude --json`, and full unittest suite.
- `G2` PRINCE2 context-flow enforcement: finish AI proposal schema fields, role-node payload slicing on every flow edge, explicit escalation/context-expansion records, assurance independence checks, and fallback-without-context-widening tests.
- `G2 test pack`: role-tree/flow/matrix tests, AI proposal stub tests, context-slice tests, executor role routing tests, `project design --json`, `project tree propose --ai`, `project start --ai`, `roles flow --json`, `roles matrix --json`, and full unittest suite.
- `G2` status: implemented and pushed as `f3bebcd`.
- `G2` validation: targeted role-flow/context tests passed, `project design --json`, `project tree propose --ai`, controlled-block `project start --ai`, `roles flow --json`, `roles matrix --json`, and `python3 -m unittest discover -s tests` passed with 273 tests.
- `G3` Governed external IO: implement web search, download, checksum evidence, MIME/size/sandbox controls, compression, archive verification, transcript entries, and handoff action records.
- `G3 test pack`: local HTTP server wet-run, small-file download, checksum validation, blocked URL/path tests, compression and archive verification wet-run, JSON command tests, transcript/handoff evidence tests, and full unittest suite.
- `G3` status: implemented locally; pending push boundary.
- `G3` implementation: added `stagewarden.tools.external_io.ExternalIOTool` with governed HTTP/HTTPS download, SHA-256 checksum, gzip compression, gzip verification, and JSON/HTML web-search parsing.
- `G3` implementation: added commands `web search`, `download`, `checksum`, `compress`, and `archive verify` to CLI, interactive slash shell, command registry, help topic, transcript, and durable handoff action records.
- `G3` safety controls: URLs are restricted to HTTP/HTTPS, destination paths must remain inside the workspace, downloads enforce `--max-bytes`, outputs include content type and SHA-256, and failed operations are recorded as controlled external IO errors.
- `G3` validation: standard sandbox suite passed with `python3 -m unittest discover -s tests`, 277 tests, 3 skips for local HTTP bind unavailable in sandbox.
- `G3` wet-run: elevated local HTTP server tests passed for real download, checksum, web-search endpoint parsing, transcript evidence, and handoff actions.
- `G3` wet-run: `python3 -m stagewarden.main "checksum README.md" --json` passed in the real workspace and recorded checksum evidence.
- `G3` wet-run: interactive `/help external_io` rendered the governed IO help topic.
- `G4` Source and self-update governance: implement `sources status --strict`, `sources update`, `update status`, `update check --json`, `update apply` with confirmation, rollback boundary, source head tracking, and handoff evidence.
- `G4 test pack`: temp git repo tests for strict failures and ff-only update states, self-update no-update/update-available parser tests, JSON schema tests, `sources status --strict`, `update status`, and full unittest suite.
- `G4` partial status: source governance slice implemented locally; self-update commands still pending.
- `G4` implementation: added `sources status --strict` to fail closed when any local source reference is missing, mismatched, or not a git repository.
- `G4` implementation: added `sources update` to fast-forward local external source repositories with before/after HEAD evidence and durable `sources_update` handoff action.
- `G4` validation: temp local Git remote fast-forward test passed for strict status, update, and handoff action evidence.
- `G4` wet-run: `python3 -m stagewarden.main "sources status --strict" --json` passed in the real workspace and confirmed Caveman, Codex CLI, and Claude Code references are coherent.
- `G4` validation: `python3 -m unittest discover -s tests` passed with 278 tests and 3 expected sandbox HTTP skips.
- `G4` status: self-update governance implemented locally; pending push boundary.
- `G4` implementation: added `update status`, `update check --json`, and `update apply --yes` with branch, HEAD, upstream, ahead/behind, dirty state, and update availability.
- `G4` safety controls: `update apply` requires explicit `--yes`, performs fetch/check only after confirmation, refuses dirty worktrees, uses `git pull --ff-only`, and records before/after evidence in `update_apply` handoff actions.
- `G4` validation: temp Git remote tests passed for no-update, update-available, confirmation block, fast-forward apply, and invalid/dirty repository refusal.
- `G4` wet-run: `python3 -m stagewarden.main "update status" --json` passed in the real workspace; interactive `/update apply` blocked without confirmation as expected.
- `G4` validation: `python3 -m unittest discover -s tests` passed with 280 tests and 3 expected sandbox HTTP skips.
- `G5` Codex/Claude-style operator UX and extension architecture: implement slash palette with fuzzy filtering/cursor selection/non-TTY fallback, registry-backed examples/topic metadata, extension layout for commands/roles/skills/hooks/MCP, and bilingual README parity.
- `G5 test pack`: command registry tests, fuzzy matcher tests, non-TTY slash fallback tests, guided menu tests, scaffolded extension discovery tests without untrusted execution, README/README_IT command parity checks, manual interactive wet-run, and full unittest suite.
- `G5` partial status: slash palette fuzzy/example discovery implemented locally; extension scaffold and cursor-selection UI still pending.
- `G5` implementation: command registry entries now support examples, `/slash` uses fuzzy/example matching, JSON palette entries expose examples, and completion falls back to fuzzy query results when direct matches fail.
- `G5` wet-run: `python3 -m stagewarden.main "slash scarica" --json` found `download`; interactive `/slash upgrade stagewarden` found `update apply`.
- `G5` validation: targeted slash palette, command catalog, completion, and JSON tests passed.
- `G5` partial status: safe extension scaffold/discovery implemented locally; cursor-selection UI remains pending.
- `G5` implementation: added `.stagewarden/extensions/<name>/` scaffold with `commands/`, `roles/`, `skills/`, `hooks/`, `mcp/`, and `extension.json`.
- `G5` safety controls: extension discovery is read-only and does not execute untrusted extension code; `.stagewarden/` is ignored by git by default.
- `G5` wet-run: `python3 -m stagewarden.main "extension scaffold local-tools" --json` created a local scaffold; `python3 -m stagewarden.main "extensions" --json` discovered it.
- `G5` validation: `python3 -m unittest discover -s tests` passed with 283 tests and 3 expected sandbox HTTP skips.
- `G5` implementation: added `/slash choose [query]` as a portable guided command chooser; it returns the selected command text without executing it, preventing accidental mutating actions.
- `G5` wet-run: interactive `/slash choose upgrade` selected `/update apply --yes` and did not create an `update_apply` action.
- `G5` implementation: CLI `stagewarden "slash choose <query>"` now uses chooser semantics too, instead of falling back to raw slash filtering; `--json` returns the top chooser candidates.
- `G5` wet-run: `python3 -m stagewarden.main "slash choose upgrade"` rendered numbered candidates; `--json` returned `update apply`.
- `G5` validation: `python3 -m unittest discover -s tests` passed with 285 tests and 3 expected sandbox HTTP skips.
- `G5` implementation: `/help` topic metadata for update/external-io/extensions is now registry-driven from `stagewarden.commands`, reducing drift between help, command catalog, and slash surfaces.
- `G5` wet-run: interactive `/help update`, `/help io`, and `/help extension` rendered the registry-backed topic content in the real shell.
- `G5` validation: `python3 -m unittest discover -s tests` passed with 286 tests and 3 expected sandbox HTTP skips.
- Documentation parity is mandatory: when user-facing behaviour changes, update both English README and Italian README.

Codex/Claude UX baseline now explicitly includes:

- slash-command discoverability and completion
- shell-first conversational loop
- readable status surfaces with provider/account/model/limit context
- typed transcript and resume-ready context
- browser/device auth flows that feel native
- guided provider-model selection with minimal ambiguity
- visible routing/handoff context instead of opaque execution

Phase A - OS-aware shell runtime and preflight:

- Status: in progress.
- Implemented mini-block 2026-04-22: added `stagewarden/runtime_env.py` with OS-family normalization, shell capability discovery for bash/zsh/PowerShell/cmd, default shell reporting, line-ending/path-separator reporting, and `select_shell_backend()` for `auto` or explicit backend selection.
- Implemented mini-block 2026-04-22: `stagewarden status`, `status --json`, `status --full --json`, `doctor`, and `doctor --json` now expose runtime/shell capabilities without initializing git during doctor.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/runtime_env.py stagewarden/main.py` passed.
- Validation 2026-04-22: targeted runtime/status/doctor tests passed.
- Validation 2026-04-22: wet-run `python3 -m stagewarden.main status --json` reported macOS Darwin arm64, default shell `/bin/zsh`, recommended shell `zsh`, bash available, PowerShell/cmd unavailable.
- Validation 2026-04-22: wet-run `python3 -m stagewarden.main doctor --json` reported runtime capabilities and repository state successfully.
- Validation 2026-04-22: full suite `python3 -m unittest discover -s tests` passed with 230 tests.
- Git boundary 2026-04-22: runtime mini-block committed locally as `7b54391 stagewarden: initialize workspace` by Stagewarden wet-run auto-snapshot.
- Implemented mini-block 2026-04-22: `ShellTool` now uses the configured runtime shell backend (`auto` by default), rejects missing explicit backends, prefers detected zsh/bash on POSIX, keeps PowerShell/cmd command construction on Windows, and writes `shell_backend` plus executable into command previews.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/config.py stagewarden/runtime_env.py stagewarden/tools/shell.py` passed.
- Validation 2026-04-22: targeted shell backend tests passed.
- Validation 2026-04-22: wet-run `ShellTool(...).run("pwd")` executed in `/Users/donato/Stagewarden` with `shell_backend=zsh executable=/bin/zsh`.
- Validation 2026-04-22: full suite `python3 -m unittest discover -s tests` passed with 232 tests.
- Git boundary 2026-04-22: shell backend mini-block committed locally as `154758b stagewarden: initialize workspace` by Stagewarden wet-run auto-snapshot.
- Implemented mini-block 2026-04-22: added `preflight` and `preflight --json` as read-only readiness checks combining doctor, runtime/shell capabilities, git state, PRINCE2 role check, provider limits, sources status, permissions, handoff stage view, and remediation actions.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/main.py stagewarden/commands.py` passed.
- Validation 2026-04-22: targeted `preflight`, command catalog, and completion tests passed.
- Validation 2026-04-22: wet-run `python3 -m stagewarden.main preflight --json` reported runtime macOS/zsh, git dirty state, role-check warnings, provider limits, sources status, and remediation list without initializing or mutating git.
- Validation 2026-04-22: wet-run `python3 -m stagewarden.main preflight` rendered the human diagnostic summary.
- Validation 2026-04-22: full suite `python3 -m unittest discover -s tests` passed with 234 tests.
- Implemented mini-block 2026-04-22: `status`, `status --json`, `status --full`, and `status --full --json` now include a remediation section derived from preflight signals.
- Status remediations currently cover dirty git state, incomplete PRINCE2 role baseline, blocked provider limits, missing source references, and active recovery/exception lane.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/main.py` passed.
- Validation 2026-04-22: targeted status/preflight remediation tests passed.
- Validation 2026-04-22: wet-run `python3 -m stagewarden.main status --json` and `python3 -m stagewarden.main status --full` rendered remediation actions for dirty git, missing role baseline, and active recovery state.
- Validation 2026-04-22: full suite `python3 -m unittest discover -s tests` passed with 235 tests.
- Git boundary 2026-04-22: status remediation mini-block committed locally as `e4867a9 stagewarden: initialize workspace` by Stagewarden wet-run auto-snapshot.
- Implemented mini-block 2026-04-22: added `stagewarden/shell_compat.py` for shell-specific env references, quoting, path literals, Windows PowerShell/cmd translations for simple read commands, and clear POSIX-only rejection for Windows backends.
- Implemented mini-block 2026-04-22: `ShellTool` now prepares Windows backend commands through `shell_compat`, including PowerShell/cmd session markers.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/shell_compat.py stagewarden/tools/shell.py` passed.
- Validation 2026-04-22: targeted tests passed for env/quote/path formatting, Windows command translation, POSIX-only rejection, and ShellTool backend preparation.
- Validation 2026-04-22: wet-run `ShellTool(...).run("pwd")` on macOS still executed with `shell_backend=zsh executable=/bin/zsh` and returned `/Users/donato/Stagewarden`.
- Validation 2026-04-22: full suite `python3 -m unittest discover -s tests` passed with 240 tests.
- Git boundary 2026-04-22: shell compatibility mini-block committed locally as `2dc8d8a stagewarden: initialize workspace` by Stagewarden wet-run auto-snapshot.
- Implemented mini-block 2026-04-22: shell backend control now defaults to automatic detection, with optional manual override through `shell backend` and `shell backend use <auto|bash|zsh|powershell|cmd>`.
- Implemented mini-block 2026-04-22: configured backend is now surfaced in `status`, `status --full`, `doctor`, and `preflight`; command catalog/help expose the shell backend commands.
- Implemented mini-block 2026-04-22: `.stagewarden_settings.json` is now treated as a local runtime artifact and ignored by git/runtime checkpoint governance.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/main.py stagewarden/commands.py` passed.
- Validation 2026-04-22: targeted shell-backend status/command tests passed.
- Validation 2026-04-22: wet-run `python3 -m stagewarden.main shell backend --json` reported `configured=auto` and `selected=zsh` on macOS.
- Validation 2026-04-22: wet-run `python3 -m stagewarden.main shell backend use zsh` and then `shell backend use auto` confirmed optional override works while preserving automatic default.
- Validation 2026-04-22: wet-run `python3 -m stagewarden.main preflight` now reports the configured shell backend.
- Validation 2026-04-22: full suite `python3 -m unittest discover -s tests` passed with 242 tests.
- Git boundary 2026-04-22: shell backend control mini-block committed locally as `f3d3c32 stagewarden: initialize workspace` by Stagewarden wet-run auto-snapshot.
- Implemented mini-block 2026-04-22: Windows shell enforcement now distinguishes bash-required/POSIX-required commands and rejects them early with a backend-specific error before execution.
- Implemented mini-block 2026-04-22: `status` and `preflight` now emit Windows shell readiness remediation when bash is unavailable on a Windows runtime, making the future rejection visible before task execution.
- Validation 2026-04-22: `python3 -m py_compile stagewarden/shell_compat.py stagewarden/tools/shell.py stagewarden/main.py` passed.
- Validation 2026-04-22: targeted tests passed for bash-required command detection, ShellTool enforcement, Windows readiness remediation, and shell backend command flow.
- Validation 2026-04-22: full suite `python3 -m unittest discover -s tests` passed with 245 tests.
- Git boundary 2026-04-22: Windows shell readiness/enforcement mini-block committed locally as `4ef007f stagewarden: initialize workspace` by Stagewarden wet-run auto-snapshot.
- Add an OS/runtime capability module that reports OS family, platform release, architecture, cwd, default shell, shell executable, bash availability/version, PowerShell availability/version, cmd availability on Windows, path separator, and line-ending convention.
- Add explicit shell backend selection: `shell=auto`, `shell=bash`, `shell=zsh`, `shell=powershell`, and `shell=cmd`.
- On macOS/Linux, `shell=auto` should prefer the configured POSIX shell and support bash when available.
- On Windows, `shell=auto` must execute PowerShell commands and cmd.exe commands, prefer PowerShell for structured work, and fall back to cmd only when appropriate or explicitly requested.
- Add path translation, quoting rules, environment variable syntax differences, executable discovery, and clear rejection for POSIX-only commands that cannot be translated.
- Surface OS/shell capabilities in `status`, `status --full --json`, future `preflight`, and shell tool transcript entries.
- Validation: unit tests for OS detection normalization, shell backend selection, Windows PowerShell command construction, Windows cmd command construction, path/quote translation, missing bash detection, unsupported-shell rejection, status JSON fields, and a real wet-run on the current macOS workspace.

Phase B - PRINCE2 role tree routing:

- Status: partially implemented.
- New cross-cutting requirement: every PRINCE2 routing action must be announced to the user and recorded in handoff/log context, including proposal generation, approvals, forced approvals, role-node changes, route-pool changes, fallback decisions, and escalation/exception transitions.
- Completed: `roles tree`, `roles tree --json`, `roles check`, and `roles check --json`.
- Current role-tree nodes expose node id, role type, parent, level, accountability boundary, delegated authority, responsibility domain, context scope, include/exclude rules, expansion events, assignment, fallback pool, and readiness.
- Completed: `roles flow` and `roles flow --json` render authorized PRINCE2 transitions between role-tree nodes.
- Current flow edges expose trigger, source node, target node, flow type, payload scope, decision authority, expected evidence, validation condition, tolerance boundary, and return path.
- Completed: `roles matrix` and `roles matrix --json` combine role tree, flow, assignments, provider-models, params, accounts, provider/account limit state, readiness, context slices, and findings.
- Completed: `role add-child <parent_node> <role_type> [node_id]` adds delegated/subordinate nodes to the approved role-tree baseline.
- Completed: `role assign <node_id> <provider> <provider_model> [reasoning_effort=<value>] [account=<name>]` assigns provider-models to a specific node.
- Completed: guided menu equivalents for delegated/subordinate nodes and node assignment.
- Completed: node assignment supports primary/reviewer/fallback model pools.
- Completed: top-level baseline matrix command `roles baseline matrix` makes delegated nodes and route pools visible without opening the full `roles baseline --json` payload.
- Completed: `project design` now emits the explicit capability/project packet and clarification-gap surface required before AI-assisted tree design.
- Completed: `project start` now invokes the project-design stage first and exposes any open clarification gaps before baseline application.
- Completed: structured project-brief fields are now persisted in runtime handoff and exposed inside `project design`.
- Completed: local proportional tree proposal is available through `project tree propose` without persisting a baseline.
- Completed: `project tree approve` persists reviewed proposals and blocks unresolved gaps unless `--force` is explicit.
- Completed: `project start` is connected to the proposal/approval path and no longer silently applies the static baseline.
- Completed: `ProjectHandoff.record_action()` now provides a generic durable action log for user-visible operational actions.
- Completed: `project start` records `project_start_blocked` and `project_start_approved` handoff entries with design/proposal gap details, approval status, forced flag, and proposed added nodes.
- Completed: `project tree approve` records `project_tree_approval_blocked` or `project_tree_approval` with gaps, proposal status, forced flag, source, node count, and added-node metadata.
- Wet-run 2026-04-23: sequential inspection of `.stagewarden_handoff.json` confirmed `project_start_blocked` is recorded with missing `scope` and `expected_outputs` details.
- Completed: `handoff actions [limit]` and `handoff actions [limit] --json` expose durable action/audit entries directly from runtime handoff.
- This closes the discoverability gap for the transparency rule: the user can inspect operational actions without opening `.stagewarden_handoff.json`.
- Completed: `status`, `status --json`, and `statusline --json` now surface the latest durable handoff action in the focus/statusline payloads.
- This strengthens the transparency rule: every user-visible status surface can show the last tracked operational action without requiring a separate handoff command.
- Next: add AI-assisted proposal generation that consumes `project design` plus structured brief, then compare/merge with the local proportional proposal before approval.
- `project start` must use an available AI model through the handoff system to propose the initial project tree and node definitions when local rules are insufficient.
- AI-assisted tree design must still obey cost control and rate-limit rules: prefer local/cheap models first, escalate only when complexity requires it, and use fallback models without widening node context.
- Completed: `project tree propose --ai` builds a prompt from `project design` plus the local proposal, calls the selected model only through `RUN_MODEL`, validates suggested tree patches, and merges valid nodes into the review-only proposal without approval/persistence.
- Completed: AI tree proposal reports `ai_requested`, model/account used, valid added nodes, rejected nodes, and fallback/local-only status for auditability.
- Completed: `project start` now detects high-complexity/high-risk brief signals and can invoke the AI-assisted proposal path before approval; `project start --ai` forces the same path explicitly.
- Completed: approved AI-assisted startup baselines persist proposal AI metadata and valid AI-added nodes, while blocked startup entries record AI attempt/fallback metadata in handoff.
- Completed: explicit `project tree propose` and `project tree propose --ai` commands now record durable `project_tree_proposal` / `project_tree_proposal_ai` handoff actions with status, source, AI metadata, added nodes, gaps, and node count.
- Completed G1 slice: `ModelCommunicationPacket` is now machine-serializable for inspection/tests, and model JSON responses can expose safe `usage` / `token_usage` / `context_window` metadata.
- Completed G1 slice: memory records input/output/current/context-window token metadata only when the provider output exposes it, aggregates it in `models usage`/budget stats, and `statusline --json` now reports context-window usage from memory.
- Completed G2 slice: role-routed prompts now expose active incoming/outgoing PRINCE2 flow edges, triggers, payload scopes, and validation conditions, making context movement explicit to the model.
- Completed G2 slice: AI project-tree patches can carry responsibility domain, context scope, context include/exclude slices, tolerance boundary, validation condition, and open questions; valid fields are merged into review-only proposals.
- Completed G2 slice: `roles check` warns when an assigned delegated node has no explicit PRINCE2 flow edge, so context movement remains visible and reviewable before execution.
- Critical context rule: AI-assisted tree design must start from two explicit inputs in the prompt packet, not assumptions:
- agent capability specification: real Stagewarden capabilities, available tools, shell/file/git/web/download/compression abilities, permission mode, OS/runtime constraints, provider/model/account availability, rate-limit state, and known validation/wet-run obligations.
- project specification: task objective, scope, constraints, expected outputs, quality gates, stakeholders/roles, delivery mode, uncertainty, risk tolerance, and any user-provided governance requirements.
- The tree-design packet must tell the model what the agent can actually do now, so node planning is grounded in executable capabilities instead of generic PRINCE2 theory.
- The tree-design packet must also tell the model what project is being designed, so node structure, delegations, and escalation paths are proportional to the real project instead of the static default tree.
- Missing capability context or missing project specification must be treated as a clarification gap before accepting an AI-proposed organization tree baseline.
- The AI proposal must produce structured output: project assumptions, tree nodes, role type, parent, responsibility domain, context include/exclude slices, delegated authority, tolerances, primary/reviewer/fallback model suggestions, validation conditions, and open questions.
- The AI proposal must be treated as a recommendation, not an approved baseline; the user/Project Board must review and approve or edit it before persistence.
- Handoff must record the design model used, prompt purpose, proposal summary, selected tree baseline, unresolved assumptions, and git boundary.
- Add `project design`, `project design --json`, or equivalent guided flow as the explicit first stage behind `project start`.
- Completed: approved role-tree baseline persists in handoff and `.stagewarden_models.json` through `project start`, `roles propose`, `roles setup`, and `roles tree approve`.
- Completed: `roles baseline` and `roles baseline --json` render the approved baseline.
- Completed: executor model calls now prefer approved role-tree node assignment/context before falling back to the flat role map.
- Context rule: every model call receives only the selected node context; context expansion is allowed only by PRINCE2 events such as escalation, exception, stage boundary, delegated change, assurance review, or board decision.
- Rate-limit rule: fallback changes provider/model/account but must never widen the role-node context.
- Flow rule: PRINCE2 defines movement between nodes, not only node ownership. Stagewarden must model controlled handoff flow between role nodes: Board authorization -> Project Manager planning/control -> Team Manager work package delivery -> Project Support records -> Project Assurance review -> Change Authority exception/change decisions -> Board stage/exception/closure decisions.
- Each node transition must define trigger, source node, target node, payload/context slice, decision authority, expected evidence, validation condition, tolerance boundary, and return path.
- Normal flow examples: Project Executive authorizes initiation/project/stage; Project Manager issues work package to Team Manager; Team Manager returns checkpoint/completion evidence; Project Support records baseline/register updates; Project Assurance reviews quality/risk evidence independently.
- Exception flow examples: Team Manager escalates forecast tolerance breach to Project Manager; Project Manager escalates stage/project exception to Board or delegated Change Authority; Change Authority approves/rejects/re-baselines within delegated limits; Board handles out-of-tolerance decisions.
- Context must move only along approved flow edges. A target node receives only the payload needed for its role and decision; broader context requires a formal PRINCE2 escalation/event and handoff record.
- Add future `roles flow` and `roles flow --json` commands to render node transitions, allowed triggers, payload scopes, and escalation paths.
- Add future tests for flow graph validity: no orphan nodes, no unauthorized direct delivery-to-board bypass except escalation, assurance remains independent, and exception/change flows respect delegated authority.
- Validation: role-tree persistence tests, context-slice filtering tests, delegated node tests, matrix JSON tests, `project start` wet-run, and regression tests for current flat-role compatibility.

Phase C - governed web research, download, and compression:

- Status: planned.
- Add controlled web research capability governed by PRINCE2 role context, permission policy, citations, and handoff evidence.
- Add `web search <query>` and `web search --json <query>` for operator-visible research; model-initiated research must route through executor/tool transcript.
- Add `download <url> [path]`, `download --json <url> [path]`, and `download status`.
- Download rules: explicit permission checks, URL validation, max-size limits, destination sandboxing, checksum recording, MIME/type detection, license/copyright risk recording, and failure-safe partial-file cleanup.
- Add `compress <path>`, `compress --json <path>`, and `compress verify <archive>`.
- Compression rules: preserve originals unless overwrite is explicitly approved, verify archive integrity with a real extraction/integrity wet-run, and reject dry-run-only checkpoints.
- Handoff rule: every search/download/compression operation records PRINCE2 role node, purpose, source URL/query, output path, checksum, size, validation result, timestamp, and git boundary.
- Validation: local HTTP server wet-run for small-file download, checksum verification, compression, archive verification, transcript entry, and handoff entry.

Phase D - preflight and status remediation:

- Status: planned.
- Add `preflight` and `preflight --json` combining doctor, OS/shell capabilities, roles check, model limits, sources status, git status, auth/account state, permissions, and active exception plan state.
- Add remediation section to `status` and `status --full`: missing role baseline, active exception plan, dirty git, blocked providers/accounts, missing auth, missing source references, restrictive permissions, missing bash for bash-required tasks, and Windows shell backend readiness.
- Validation: CLI JSON schema tests and wet-run in current workspace.

Phase E - source and self-update governance:

- Status: planned.
- Add `sources status --strict` to fail on missing repos, dirty repos, wrong remote, missing HEAD, or unexpected shallow state.
- Add `sources update` to run `git pull --ff-only` in each reference repo and record old/new heads in handoff.
- Add `update status`, `update check --json`, and `update apply` for controlled self-update from GitHub.
- Self-update must show current version/head, target version/head, changelog or commit summary, rollback boundary, and require confirmation before applying changes.
- Validation: temp-repo tests for strict source failures, update-available/no-update states, JSON schema tests, and a wet-run `update status`.

Phase F - provider status and usage accounting:

- Status: planned.
- Add provider-specific parsers for richer Codex/Claude status where machine-readable outputs are available.
- Extend persisted limit snapshots with reset windows, utilization, overage fields, stale detection, and safe redacted raw-message previews.
- Add token/context-window accounting to memory/handoff only when provider output exposes safe metadata.
- Validation: parser unit tests, stale-limit tests, redaction tests, and status JSON schema tests.

Phase G - command UX and extension architecture:

- Status: partially implemented for command registry.
- Completed: structured command registry, `commands`, `commands --json`, registry-backed completion seed, and registry-backed rendering for main help topics.
- Next: move overview/topic metadata and examples into the registry or a companion metadata module.
- Next: implement Codex-style slash palette opened by `/` with filtering, fuzzy/substring matching, command descriptions, cursor selection, Enter selection, Esc/cancel, and non-TTY fallback.
- Next: define extension layout inspired by Claude Code plugins: commands, role agents, skills, hooks, MCP definitions, and README per extension.
- Validation: command matching tests, non-TTY fallback tests, manual palette wet-run, and scaffolded test extension discovery without executing untrusted code.

Phase H - bilingual documentation:

- Status: planned.
- Add `README.it.md` as the Italian companion to the English `README.md`.
- Keep both README files aligned on purpose, install/setup, interactive shell, slash commands, provider/account configuration, PRINCE2 role tree, handoff, OS-aware shell execution, web/download/compression governance, tests, license, and acknowledgements.
- Add cross-links: English README links to Italian README; Italian README links back to English README.
- Avoid embedding copyrighted PRINCE2 study material; describe only Stagewarden behaviour and high-level PRINCE2-inspired governance concepts.
- Validation: documentation test or policy check ensuring `README.md` and `README.it.md` exist, include MIT license reference, author Donato Pepe, Caveman/Codex/Claude acknowledgements where applicable, and no `study/` content references.

## UX Reference Analysis: Codex CLI, Claude Code, Caveman

Status: analyzed local downloaded references

Reference boundary:

- Sources are local study references only: `external_sources/codex`, `external_sources/claude-code`, `external_sources/caveman`.
- Stagewarden should reproduce interaction patterns and product behavior where useful, not copy source code.
- Any future direct code reuse requires license review and explicit attribution before implementation.

Codex CLI UX lessons to apply:

- Slash command behavior should be centralized in one command registry reused by composer, popup, completion, help, and dispatch.
- Slash command visibility should support feature/context gating, similar to Codex built-in command flags.
- Fuzzy matching should support partial command discovery instead of requiring exact command memory.
- The slash command popup should preserve predictable Enter/Tab semantics and avoid surprising submission behavior while the popup is active.
- Status should be a full operational dashboard, not a login-only output: model, provider, account, cwd, permissions, session/thread identity, token/context usage, agents, rate limits, credits, and stale/missing limit state.
- Provider limit snapshots should distinguish available, stale, unavailable, and missing states, with a 15-minute stale threshold as a reference target.

Claude Code UX lessons to apply:

- Stagewarden should behave like a terminal-native coding partner: user enters a project folder, runs one command, and works through natural language plus slash commands.
- Command/plugin architecture should support discoverable workflows, custom commands, specialized agents/roles, skills, hooks, and MCP-style extensions over time.
- `/bug`-style feedback/reporting should be considered for future operator issue capture.
- Plugin-style structure suggests future Stagewarden extension points: commands, role agents, skills, hooks, MCP definitions, and README-level documentation per extension.
- Hook examples reinforce that command/tool validation should happen before execution and should fail safely.

Caveman UX lessons to apply:

- Mode state should be lightweight, visible, and persisted in a simple local state file.
- Statusline/badge-style output is useful to keep active mode visible without bloating every response.
- SessionStart/UserPromptSubmit hook concepts map to Stagewarden startup checks and per-turn reinforcement of active mode/governance.
- Natural language activation/deactivation should coexist with slash commands for common modes.
- Readability and install accuracy are product requirements, not cosmetic documentation.

Stagewarden UX target:

- Start with `stagewarden` in any repo and immediately show a concise shell with `/help`, `/status`, model/account visibility, permission posture, git state, and PRINCE2 boundary state.
- Typing `/` should open an interactive command palette with command labels, descriptions, filtering, and cursor selection.
- Commands should be grouped by operator intent: core, models, accounts, roles, PRINCE2 handoff, git, permissions, sources, Caveman, LJSON, diagnostics.
- Every important shell surface should have a JSON equivalent where useful for automation.
- Status surfaces should include next-action remediation when something blocks delivery: missing role baseline, active exception plan, dirty git, blocked provider/account, missing auth, missing source references, or restrictive permission mode.
- Role-driven model assignment and context isolation must stay visible through `roles`, `roles domains`, future `roles tree`, future `roles check`, and future `roles matrix --json`.
- PRINCE2 role routing must support a hierarchy of role nodes, not a fixed one-model-per-role table.

Immediate next mini-block:

- Implement Phase 1 command discovery foundation before the interactive palette. This reduces duplicate command definitions and gives the palette a reliable metadata source.
- First deliverable: `commands` and `commands --json` backed by a minimal registry for existing shell commands.
- Do not implement cursor UI until the registry is in place.

## Implemented Capabilities

- Codex-style agent loop: plan, call model through handoff, execute tool, observe, retry, escalate, validate, persist state.
- Multi-model routing: local, cheap, ChatGPT/OpenAI, Claude with escalation and fallback.
- Provider/account configuration: model add/remove/use/list/variant/block/unblock, account add/use/remove/block/unblock/login.
- Online usage-limit capture: usage-limit messages such as `try again at 8:05 PM` are persisted as blocked-until metadata.
- Device-code style OpenAI login flow scaffolded for real browser login, without browser token scraping.
- Claude credential handling aligned to provider-style credential files and account profiles.
- Interactive shell mode: start in a folder and run `stagewarden`, then use commands or natural task input.
- Rich interactive help with model, account, permission, handoff, git, LJSON, and Caveman commands.
- Git prerequisite governance: repository initialization, runtime ignores, local snapshot commits, history inspection.
- Git shell commands: status, log, history, show, show stat.
- Git tool actions for autonomous execution: status, log, show, file history.
- Permission engine: workspace settings, default modes, allow/ask/deny rules.
- Permission modes: `default`, `accept_edits`, `plan`, `auto`, `dont_ask`.
- Fast mode aliases: `mode plan`, `mode auto`, `mode accept-edits`, `mode dont-ask`, `mode default`.
- Session-only permissions: `permission session mode`, `permission session allow|ask|deny`, `permission session reset`.
- Live permission refresh: active agent tools reload permission policy after shell permission changes.
- Approval prompt flow: interactive `ask` decisions support `y`, `n`, `always`, `session`, and `deny`; non-interactive tools remain fail-closed.
- Tool invocation transcript: tool calls are recorded in memory, persisted as LJSON, and exposed through `transcript`/`trace`.
- Shell execution across OS families: POSIX shell, bash/zsh where available, PowerShell, cmd fallback.
- Planned explicit OS/shell awareness: status/preflight must expose current OS, shell backend, bash availability, and shell transcript metadata.
- File tools: read, write, patch, patch files, list, search.
- Planned network/file artifact tools: governed web search, controlled downloads, checksum evidence, and verified compression with handoff recording.
- Wet-run enforcement: dry-run or narrative completion is not accepted as final checkpoint.
- LJSON core: encode/decode, numeric-key variant, gzip, schema version, streaming chunk support, benchmark examples.
- LJSON use for runtime trace.
- ASCII/confusable safety for generated and tool output.
- Caveman mode: inspired by Julius Brussee's Caveman, with command ergonomics, review/commit/compress commands, README acknowledgements.
- PRINCE2 governance gate: task assessment, PID generation, project controls, closure checks.
- Persistent PRINCE2 handoff: plan, stage, latest observation, git boundary, registers, exception plan, lessons.
- Dedicated registers: risks, issues, quality, lessons, exception plan.
- Operational posture: governance summary, stage health, next action, active stage, git boundary.
- Stage boundary view: closed stages, active stage, PID boundary, decision, registers, exception plan.
- Implementation backlog in handoff: persisted `planned`, `ready`, `in_progress`, `blocked`, `done` lifecycle states.
- Planner stage gating: only `ready` and `in_progress` stages are executed.
- Automatic promotion: next `planned` stage becomes `ready` after controlled completion.
- Recovery lane: exception plans generate explicit `recovery-step-*` stages.
- Recovery resume: recovery stages can be resumed from handoff.
- Recovery boundary states: `exception_active`, `recovery_active`, `recovery_cleared`, `none`.
- Recovery closure gate: completed recovery lanes close open issues/risks, clear exception controls, close covered failed stages, and resume normal planned stages.
- Handoff Markdown auto-export: `handoff export` and `handoff md` update the generated runtime section in `HANDOFF.md` with redaction.
- Safer command classification: shell permission checks now distinguish read-only git commands from write/high-risk operations, redirection, package installs, and mutating commands.

## Codex/Claude-Inspired Behaviours To Apply

These are the implementation items still worth applying, based on prior source/research review and Stagewarden's current architecture.

### 1. Approval Prompt Flow

Status: implemented

Implement an interactive approval flow similar to Codex/Claude tool approvals.

Implemented behaviour:

- When permission decision is `ask`, the interactive shell prompts the user with capability, target, and rule.
- Supported answers: `y`, `n`, `always`, `session`, and `deny`.
- `always` persists an allow rule in `.stagewarden_settings.json` and removes the matching ask rule.
- `session` adds a session-only allow rule.
- `deny` persists a deny rule.
- Non-interactive tools remain fail-closed for `ask`.

Validation:

- Unit tests cover allow precedence over matching ask rules.
- CLI tests cover `session` approval without workspace allow persistence.
- CLI tests cover `always` approval with workspace allow persistence and ask removal.
- Tool tests confirm non-interactive ask remains blocked.

### 2. Tool Invocation Transcript

Status: implemented

Implement a Codex-like visible transcript for tool calls.

Implemented behaviour:

- Tool actions produce compact transcript entries.
- Entries include iteration, step, tool, action type, success/failure, summary, detail preview, duration where available, and error type.
- Transcript is persisted in `.stagewarden_memory.json` as LJSON.
- Shell commands `transcript` and `trace` render recent tool calls.

Validation:

- Memory tests cover transcript persistence and rendering.
- Executor tests cover transcript recording from tool actions.
- CLI tests cover `transcript` rendering after an actual agent run.

### 3. Stronger Patch Application UX

Status: implemented

Improve patch handling toward Codex-style editing discipline.

Implemented behaviour:

- Prefer unified patch application for multi-file edits.
- Multi-file patches return per-file summaries such as `add path`, `update path`, and `delete path`.
- Duplicate patch targets in one diff are rejected as ambiguous before any write occurs.
- Executor outcomes keep before/after git head metadata for patching steps through the standard step outcome.
- `preview_patch_files` validates and summarizes a unified diff without writing, including in plan mode.

Validation:

- Patch tests cover add, update, delete, failed hunk, duplicate targets, and plan-mode preview.
- Plan mode allows preview but blocks write.
- Wet-run file content checks verify patch results after application.
- Executor tests cover model-dispatched patch preview and transcript recording.

### 4. Model Context Files

Status: implemented

Expose persistent handoff and logs to model prompts more deliberately.

Implemented behaviour:

- Include concise handoff summary in every model prompt.
- Include recent LJSON trace summary.
- Include current recovery state and backlog status.
- Include git boundary and dirty state.
- Keep prompt bounded with truncation rules.
- Add a dedicated `Model context files` prompt section naming `.stagewarden_handoff.json`, `.stagewarden_memory.json`, and `.stagewarden_trace.ljson`.

Validation:

- Executor prompt tests assert context file names, recovery state, backlog status, git boundary, and dirty state are present.
- Prompt size remains bounded and truncation markers are asserted for oversized registers.

### 5. Provider Capability Registry

Status: implemented

Move model/provider capabilities into a registry closer to Claude/Codex provider abstractions.

Implemented behaviour:

- Provider capabilities are centralized in `stagewarden/provider_registry.py`: auth type, model aliases, default model, context assumptions, account profiles, browser login, API-key support, env vars, URLs, and login hints.
- `handoff.py`, `modelprefs.py`, `router.py`, `secrets.py`, and CLI model/account rendering consume the registry.
- `model list` now shows capability metadata in addition to variants.
- `chatgpt` plan login semantics are explicitly separate from OpenAI API-key semantics.
- Keep no token scraping and no hidden browser extraction.

Validation:

- Provider registry unit tests cover auth/capability data and variant/backend derivation.
- Model list CLI tests assert different login hints for `chatgpt`, `openai`, and `claude`.
- Routing and handoff tests still pass.

### 6. Shell Sessions As First-Class Tools

Status: implemented

Expand persistent shell sessions toward Codex/Claude terminal behaviour.

Implemented behaviour:

- Expose interactive commands: `sessions`, `session list`, `session create [cwd]`, `session send <id|last> <command>`, and `session close <id|last>`.
- Persist shell session IDs only for current process, not repo.
- Track cwd and return code.
- Keep permission checks per command.

Validation:

- Tool tests cover create/list/send/close with marker-based command output.
- CLI tests cover `last` alias, cwd visibility, return-code preview, and close.
- CLI tests verify plan-mode permission denial works inside a persistent session.

### 7. Resume Command Over Handoff

Status: implemented

Even though Stagewarden uses implicit handoff resume, add explicit commands for operator control.

Implemented behaviour:

- `resume` reloads current handoff context into the active agent and reruns the task stored in handoff.
- `resume --show` prints task, current step, next action, and stage view.
- `resume --clear` archives current handoff as `.stagewarden_handoff.archive.<timestamp>.json` and starts fresh.
- Preserve implicit resume as default.

Validation:

- CLI tests verify `resume --show` uses existing `current_step_id`.
- CLI tests verify `resume --clear` archives the old handoff, creates a fresh context, and leaves the archive inspectable.

### 8. Recovery Closure Gate

Status: implemented

Make `recovery_cleared` perform a formal PRINCE2 closure action instead of only rendering next action.

Implemented behaviour:

- When all `recovery-step-*` stages complete with wet-run evidence, the agent closes the recovery gate.
- Open issues and risks are closed with recovery evidence.
- Failed non-recovery stages covered by recovery are marked completed.
- Exception plan is cleared only after recovery evidence closes open issues.
- The next planned normal stage is promoted to `ready`.

Validation:

- Integration tests cover a project starting in exception, executing recovery steps, closing registers, clearing exception plan, and completing the resumed normal stage.
- Wet-run gate remains enforced by the executor before any recovery stage can complete.

### 9. Handoff Markdown Auto-Update

Status: implemented

Keep this file updated automatically from runtime handoff and implementation backlog.

Implemented behaviour:

- Commands `handoff md` and `handoff export` update the generated runtime section in `HANDOFF.md`.
- Export includes task, status, plan status, active stage, git boundary, PID boundary, recovery state, next action, registers, backlog, and recent entries.
- Manual roadmap content is preserved outside stable generated markers.
- Token-like values, bearer secrets, and JWT-like strings are redacted.

Validation:

- CLI tests cover export command, marker insertion, manual content preservation, and secret redaction.

### 10. Board Review Command

Status: implemented

Add a PRINCE2 board-level summary command.

Implemented behaviour:

- Command: `board` or `stage review`.
- Show business justification, current boundary decision, open issues, open risks, quality status, recovery state, and recommended authorization.
- Distinguish continue, stop, recover, close.

Validation:

- Closed clean project recommends closure.
- Open issues recommend review before closure.
- Recovery active recommends recovery execution.

### 11. Safer Command Classification

Status: implemented

Improve shell permission classification beyond first token.

Implemented behaviour:

- `git status`, `git log`, `git show`, `git diff`, and other inspection commands are classified as read.
- Mutating git commands such as `git add`, `commit`, `push`, `checkout`, `merge`, and `rebase` are no longer treated as read-only.
- Shell redirection and tee-style output are classified as write.
- Package installation and mutating npm/python/node/test commands are classified as write/network-risk.
- Delete/move/copy/install-style operations are classified as write.

Validation:

- Tool tests verify read-only git commands are not blocked by plan mode policy.
- Tool tests verify write git commands are blocked in plan mode.
- Tool tests verify redirection and package install commands are blocked in plan mode.

### 12. Rich Help Reorganization

Status: implemented

Current help is complete but long. Reorganize it like modern CLIs.

Implemented behaviour:

- `help` shows compact categories and fast examples.
- `help models`, `help accounts`, `help permissions`, `help handoff`, `help git`, and `help ljson` show focused command lists and examples.
- `help caveman` remains wired to Caveman-specific help for compatibility.
- Keep examples in each category.

Validation:

- CLI tests cover compact top-level help.
- CLI tests cover category help for models, accounts, permissions, handoff, git, and LJSON.

### 13. Model Handoff Result Schema

Status: implemented

Harden model output parsing with a stricter schema.

Implemented behaviour:

- Accept strict JSON object with `summary`, `action`, `confidence`, `risks`, and `validation`.
- Preserve compatibility with simpler `{summary, action}` responses.
- Validate optional schema fields when present.
- Reject unknown destructive action types before tool execution.
- Invalid output is recorded through the existing executor memory/handoff failure path.

Validation:

- Executor tests cover valid strict schema execution.
- Executor tests cover invalid schema rejection and failure memory.
- Executor tests cover denial of an unknown destructive action.

### 14. Cost-Aware Execution Budget

Status: implemented

Make cost control explicit in router and handoff.

Implemented behaviour:

- Track model usage counts from persisted execution attempts.
- Record model chosen per step in handoff through existing step completion entries.
- Expose budget policy: prefer local, then cheap, then ChatGPT/OpenAI/Claude for complex or failing tasks.
- Expose `models usage` and `cost` shell commands.

Validation:

- Memory tests cover model usage counts, failures, step coverage, and cost tiers.
- CLI tests cover `models usage` and `cost` alias.
- Existing router tests continue to validate local-first/simple-task routing.
- Failures escalate according to policy.
- Usage summary is visible in shell.

### 15. Cross-OS Setup Verification

Status: implemented

Strengthen setup scripts for macOS, Linux, and Windows.

Implemented behaviour:

- `stagewarden doctor` validates Python 3.11+, Git availability, PATH launcher visibility, and repository state.
- `doctor` reports provider capabilities for each configured model family: auth type, profile support, browser login, API-key support, token env state, and default model.
- `doctor` does not install prerequisites and does not initialize git.
- Interactive shell command `doctor` exposes the same report.
- Setup scripts for Unix and Windows now perform a best-effort post-install `doctor` check through `python -m stagewarden.main doctor`.
- If the post-install check cannot run successfully, setup prints an explicit next-step command instead of silently skipping validation.
- Do not auto-install git silently; report prerequisite clearly.

Validation:

- CLI tests verify `stagewarden doctor` reports Python/Git/PATH/repository state and does not create `.git`.
- Interactive shell tests verify `doctor` rendering.
- Setup script tests verify post-install doctor wiring and still pass.

## Immediate Next Implementation Order


## Recently Completed

### Setup Post-Install Doctor

Status: implemented

Implemented behaviour:

- `scripts/setup_unix.sh` and `scripts/setup_windows.ps1` now run a best-effort `doctor` check immediately after install.
- Successful validation emits `Post-install check: stagewarden doctor OK`.
- Failed validation falls back to an explicit command suggestion for the operator.

Validation:

- Setup script tests cover doctor invocation wiring and Unix fallback execution path.
- Full suite remains green after the setup changes.

### Doctor JSON Output

Status: implemented

Implemented behaviour:

- `stagewarden doctor --json` emits a stable machine-readable report for automation.
- The JSON report includes Python, Git, PATH launcher, repository state, provider capabilities, and policy flags.
- Human-readable `stagewarden doctor` output remains unchanged for operators.

Validation:

- CLI tests parse the JSON output and verify provider and policy fields.

### Final Summary Cost/Budget

Status: implemented

Implemented behaviour:

- Final agent summaries now include a dedicated `Cost and budget:` section.
- The section reports routing policy, per-model usage counts, highest cost tier reached, and failed model call count.
- The summary is driven by execution memory so it reflects the actual run, not static configuration.

Validation:

- Memory tests cover budget summary rendering.
- Agent integration tests verify the final user-facing summary includes the budget section.

### Resume Wet-Run

Status: implemented

Implemented behaviour:

- Interactive `resume` now has an end-to-end wet-run test with a success stub backend.
- The test starts from persisted handoff context, resumes execution, creates the target artifact, and verifies handoff closure.
- `resume` now reports the original resumed step id, not the mutated post-run step id.

Validation:

- CLI tests cover `resume --show`, `resume --clear`, and full `resume` execution against a fake model binary.

### Richer Model Usage and Cost Reporting

Status: implemented

Implemented behaviour:

- `models usage` and `cost` now include totals, failure rate, highest tier reached, last model used, and escalation path.
- Memory now exposes `model_usage_stats()` as a machine-readable aggregate for automation and future JSON/telemetry output.
- Budget summaries reuse the same aggregated stats to avoid divergent reporting.

Validation:

- Memory tests cover machine-readable usage stats and richer summaries.
- Interactive shell tests verify enriched `models usage` and `cost` output.

### Model Usage JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden "models usage" --json` and `stagewarden cost --json`.
- The JSON output reuses `model_usage_stats()` and includes routing budget policy metadata.

Validation:

- CLI tests parse the JSON output and verify totals, failures, and escalation path.

### Transcript JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden transcript --json` and `stagewarden trace --json`.
- The JSON output exposes recent transcript entries from persisted workspace memory without parsing the text renderer.

Validation:

- Memory tests cover machine-readable transcript reports.
- CLI tests parse transcript JSON output and verify stored entry fields.

### Handoff and Resume JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden handoff --json`.
- Non-interactive CLI now supports `stagewarden "resume --show" --json`.
- Both outputs reuse runtime handoff/state logic instead of parsing text views.

Validation:

- CLI tests parse handoff JSON and resume-show JSON output and verify task, current step, next action, and boundary state.

### Status and Boundary JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden status --json`.
- Non-interactive CLI now supports `stagewarden boundary --json`.
- Outputs expose operational posture, permissions, model state, and PRINCE2 boundary control state without text parsing.

Validation:

- CLI tests parse status JSON and boundary JSON output and verify mode, stage view, and boundary decisions.

### Register JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `risks`, `issues`, `quality`, `exception`, `lessons`, and `todo` with `--json`.
- Outputs expose raw PRINCE2 registers and implementation backlog directly from runtime handoff state.

Validation:

- CLI tests parse register/backlog JSON output and verify representative fields for each command.

### Models and Accounts JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden models --json`.
- Non-interactive CLI now supports `stagewarden accounts --json`.
- Outputs expose provider routing state, preferred model, configured accounts, active account, token-store presence, and env mapping.

Validation:

- CLI tests parse models/accounts JSON output and verify preferred model, account activity, and token-store state.

### Permissions JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden permissions --json`.
- Output exposes workspace, session, and effective permission policy without relying on text rendering.

Validation:

- CLI tests parse permissions JSON output and verify workspace mode and allow/ask/deny rules.

### Git Read-Only JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports JSON output for `git status`, `git log`, `git history`, and `git show --stat`.
- Outputs include raw command text plus lightweight derived fields like `lines` or `commits` for easier automation.

Validation:

- CLI tests parse git JSON output and verify status, commit subjects, history path, and show-stat metadata.

### Shell Sessions JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden sessions --json` and `stagewarden "session list" --json`.
- Output exposes current process shell-session ids, cwd, and running/closed state.

Validation:

- CLI tests parse sessions JSON output and verify the empty-state contract.

### Handoff Export and Resume-Clear JSON Output

Status: implemented

Implemented behaviour:

- Non-interactive CLI now supports `stagewarden "handoff export" --json` and `stagewarden "handoff md" --json`.
- Non-interactive CLI now supports `stagewarden "resume --clear" --json`.
- Outputs expose target/archive path and operation outcome for automation workflows.

Validation:

- CLI tests parse export/reset JSON output and verify target/archive metadata.

### Overview Command

Status: implemented

Implemented behaviour:

- Added `overview` as a compact operational command for operators.
- Added `stagewarden overview --json` as a single machine-readable snapshot aggregating status, board, handoff, model usage, and transcript signals.

Validation:

- CLI tests parse overview JSON and verify authorization, model-usage totals, transcript count, and handoff task.

## Recently Completed

## Autonomous Backlog

### Provider Limit Status Across Active Providers

Status: implemented

Current state already implemented:

- Stagewarden is already multiprovider at routing level: `local`, `cheap`, `chatgpt`, `openai`, and `claude`.
- Provider and account usage-limit messages are already parsed into `blocked-until` metadata.
- The executor already blocks the failing model or account until the reported reset time and retries another eligible route.
- Current operator visibility is partial:
  - `models` and `status` show enabled/active/preferred state and `blocked-until` at model level.
  - `accounts` shows configured accounts, active account, stored token presence, env mapping, and `blocked-until` at account level.
  - `models usage` / `cost` shows Stagewarden-internal usage history, not provider-native remaining quota.

Implemented behaviour:

- `status` now includes a dedicated `Provider limit status:` section.
- `status --json` now includes a stable `provider_limits` object.
- For each enabled provider, Stagewarden now exposes:
  - enabled/active/preferred
  - routed variant
  - active account
  - model `blocked_until`
  - blocked accounts with `blocked_until`
  - last known error reason from recorded attempts
  - last attempt route/status
  - last successful use
- The implementation keeps a strict distinction between:
  - Stagewarden-internal usage history
  - provider/account temporary lockouts
  - provider-native remaining quota, which remains unsupported unless an official source exists
- The latest provider-reported limit message is now persisted per model/account together with `blocked_until`.
- Provider-limit views now expose both the lock time and the last known lockout cause text.
- Provider-limit views now classify lockout causes as `usage_limit`, `rate_limit`, `credits_exhausted`, or `provider_unavailable` when the provider message supports it.

Explicit non-goal for now:

- Do not invent fake remaining credits/messages for ChatGPT, Claude, or other providers when the upstream provider does not expose an official remaining-quota source to this agent.

Validation:

- CLI tests verify `status --json` includes provider-limit state for mixed multiprovider scenarios.
- Interactive shell tests verify `status` renders provider-limit posture together with resume context.
- Test coverage includes model-level blocks, account-level blocks, and recent error/success state.
- `overview` and `report` now also surface compact provider-limit summaries for faster operator reading.
- `overview --json` and `report --json` now carry provider-limit posture in machine-readable form.
- Persistence tests verify roundtrip storage of last limit messages in model preferences.
- Executor tests verify classification of provider limit messages.


### Caveman Help Snapshot

Status: implemented

Implemented behaviour:

- Added a CLI snapshot-style test for `help caveman`.
- The test protects supported levels, aliases, and key commands from accidental regression.

Validation:

- CLI test verifies Caveman help still exposes levels, aliases, and review/commit/compress commands.

## Recently Completed

### Resume Context Command

Status: implemented

Implemented behaviour:

- Added `resume context` to the shell and non-interactive CLI.
- The command exposes the latest implicit execution context without opening `HANDOFF.md`.
- Output includes the current task/step, latest model attempt, routed account/variant, latest tool evidence, and latest git snapshot.

Validation:

- CLI tests verify `resume context --json` returns structured route, tool, and git snapshot data.
- Interactive shell tests verify `resume context` renders the latest execution evidence in human-readable form.

### Shell UX Direction

Status: decided

Decision:

- Keep mini-block shell rendering as the preferred interaction style.
- Do not collapse shell progress and agent result output into a single compact status line.
- Favor short titled sections such as `Running task:`, `Shell progress (before|after):`, and `Agent result:`.

### Interactive Model Streaming In Shell

Status: implemented

Implemented behaviour:

- Interactive shell sessions now forward live `run_model` stdout through a streaming callback while still capturing the full final payload for strict JSON parsing.
- Streaming is attached only to the interactive shell agent path; non-interactive CLI commands keep the previous buffered behavior.
- Stream output is prefixed with a compact marker such as `[model-stream local]`.
- Added session-scoped shell controls `stream on`, `stream off`, and `stream status`.
- Interactive task execution is now framed with `Running task:` before execution and `Agent result:` before the final summary.
- Interactive shell now prints a compact `Shell progress (before|after)` block with active step, stage health, boundary decision, recovery state, and git head.
- Shell progress blocks now also show route context: planned model/account/variant before execution and actual model/account/variant after execution.
- The `after` shell progress block now also shows the latest local git checkpoint recorded for the run.
- Shell output now also includes a `Last step outcome:` mini-block between the final agent summary and the `after` progress block.
- `Last step outcome:` now also shows the concrete evidence source from the latest tool transcript, including tool, tool action, and duration when available.
- Runtime handoff markdown export now includes an `Execution Resume Context` block with latest model attempt, route, latest tool evidence, and latest git snapshot.

Validation:

- Handoff tests verify the streaming callback receives live model output.
- Interactive shell tests verify streamed model output is visible during task execution.
- Interactive shell tests verify stream toggling and suppression when streaming is disabled.
- Interactive shell tests verify the task/result framing is present around streamed execution.
- Interactive shell tests verify progress blocks are rendered around task execution.
- Memory and shell tests verify account and variant route details are preserved and rendered.
- Interactive shell tests verify the latest git snapshot is surfaced in the `after` block.
- Interactive shell tests verify the focused `Last step outcome:` block is rendered.
- Interactive shell tests verify the focused outcome block includes tool evidence details.
- Interactive shell export tests verify `HANDOFF.md` includes execution resume context and redacts sensitive values in latest observations and tool details.

### Multi-Account Failover Across Primary And Fallback Models

Status: implemented

Implemented behaviour:

- The executor now iterates across all available non-blocked accounts for the selected model instead of stopping after a single alternate profile.
- The same account failover logic now also applies to the fallback model after a primary model failure.
- Usage-limit messages continue to block the specific account that failed, and the next eligible account is tried automatically.

Validation:

- Executor tests verify repeated same-model account failover until success.
- Executor tests verify fallback-model account failover when the first fallback account is also blocked.

### PRINCE2 Git Step Checkpoints

Status: implemented

Implemented behaviour:

- Per-step automatic git snapshots now use structured commit messages with explicit PRINCE2 context.
- Step checkpoint commits now include step id, resulting status, stage health, boundary decision, and a compact task label.
- The git history is therefore usable as a lightweight control timeline, not just as a generic autosave stream.

Validation:

- Agent integration tests inspect real `git log --oneline` output and verify PRINCE2 boundary annotations are present in snapshot commits.

### Project Report Command

Status: implemented

Implemented behaviour:

- Added `report` as a compact human-readable summary for issue updates, project closure notes, and operator handoff.
- Added `stagewarden report --json` as a machine-readable summary with task, project status, stage health, governance status, authorization recommendation, next action, open controls, model activity, recent lessons, and backlog preview.
- Interactive shell now supports `report`.
- README now documents `report` together with `overview`, `health`, and `board`.

Validation:

- CLI tests parse `report` JSON output and verify task, authorization, issue count, model calls, lessons, and backlog preview.
- Interactive shell tests verify `report` rendering and backlog visibility.

### Interactive Shell History And Completion

Status: implemented

Implemented behaviour:

- Added optional `readline` integration for the interactive shell.
- Interactive sessions now persist history per workspace in `.stagewarden_history` when `readline` is available.
- Added TAB completion for core shell commands and targeted workspace-path completion for `git history`, `patch preview`, and `session create`.
- The feature degrades safely on platforms without `readline`; the shell still works normally without history/completion.

Validation:

- CLI tests verify command completion candidates include core shell commands.
- CLI tests verify workspace-path completion candidates for `git history` and `patch preview`.

### Health Command

Status: implemented

Implemented behaviour:

- Added `health` as a compact operational command for quick automation and shell inspection.
- Added `stagewarden health --json` as a stable machine-readable readiness snapshot.
- The report exposes authorization, boundary decision, open issues, open risks, open quality items, recovery state, next action, model failures, model calls, and transcript count.
- Interactive shell now supports `health` with a concise human-readable rendering.
- Help and README now document `health` alongside `overview`, `board`, and `doctor`.

Validation:

- CLI tests parse `health` JSON output and verify readiness, authorization, issue count, failure count, and transcript count.
- Interactive shell tests verify `health` rendering for a clean closed project.

### Patch Preview Command

Status: implemented

Implemented behaviour:

- Interactive shell command `patch preview <diff-file>` reads a unified diff file from the workspace.
- The command validates the diff through `preview_patch_files` and returns per-file summaries without writing.
- The command works in plan mode because it performs only read/validation operations.

Validation:

- CLI test covers plan-mode preview and verifies target file contents remain unchanged.

## Validation Standard

Every implementation must include:

- unit tests
- integration or CLI tests where applicable
- wet-run verification
- git snapshot
- push to remote

Dry-run alone is not a valid checkpoint.

## External Source Base

Status: initialized

Local reference directory:

- `external_sources/` is ignored by Git and contains shallow clones for study only.
- Tracked manifest: `docs/source_references.md`.

Cloned upstream references:

- Caveman: `external_sources/caveman`, upstream `https://github.com/JuliusBrussee/caveman`, current shallow head `84cc3c1`.
- OpenAI Codex CLI: `external_sources/codex`, upstream `https://github.com/openai/codex`, current shallow head `2a17b32`.
- Claude Code public repo: `external_sources/claude-code`, upstream `https://github.com/anthropics/claude-code`, current shallow head `0385848`.

Important source boundary:

- Do not vendor or republish third-party source in Stagewarden.
- Do not use leaked or unofficial Claude Code mirrors.
- Prefer reimplementing behavior from documented interfaces and observed public source.
- Copy code only when the upstream license permits it and attribution is added.

Study targets to extract into Stagewarden:

- Codex `tui/src/status/card.rs`: status card structure, configurable status line items, model/account/sandbox/approval display.
- Codex protocol model: token usage updates, rate-limit snapshots, model reroute events, auth status responses.
- Codex auth flow: `codex login status`, device/browser login, ChatGPT plan usage-limit parsing, retry-until time extraction.
- Codex sandbox/approval model: read-only/workspace-write/full-access, command approval decisions, network approval context.
- Claude Code public docs/plugins: plugin packaging, command discovery, setup conventions.
- Claude Code npm bundle, official package only: `claude auth status`, rate-limit headers, `rate_limit_event`, `resetsAt`, `rateLimitType`, `overageStatus`, `billing_error`, `authentication_failed`.
- Caveman: command grammar, hook activation, statusline integration, compression skills, benchmark/test structure.

Next implementation candidates:

- Add `sources update` command that runs `git pull --ff-only` in each reference repo and writes a handoff event with old/new heads.
- Add `sources status --strict` for CI/operator preflight checks.
- Extend Stagewarden `status` remediation output with explicit next commands for incomplete PRINCE2 role baseline, active exception plan, dirty git state, and blocked provider limits.
- Add Claude-style provider-limit fields: `rate_limit_type`, `utilization`, `resets_at`, `overage_status`, `overage_resets_at`, `overage_disabled_reason`.

## Status Research: Codex and Claude

Status: completed initial study

Detailed notes:

- `docs/status_research.md`

Codex findings to implement:

- Treat status as a full operational dashboard, not only login state.
- Render model, provider, cwd, permissions, agents, account, thread/session, token usage, context window, limits, credits, and stale/missing limit state.
- Use a 15-minute stale threshold for provider-limit snapshots.
- Represent limits as primary and secondary windows with `usedPercent`, `windowDurationMins`, and `resetsAt`.
- Represent credits separately with `hasCredits`, `unlimited`, and `balance`.
- Use `rateLimitReachedType` to distinguish generic rate limit from workspace credits/usage exhaustion.
- Never print raw auth tokens; Codex only includes tokens when explicitly requested by app-server clients.

Claude findings to implement:

- Expose auth status as machine-readable JSON equivalent to `claude auth status --json`.
- Track statusline-style fields: workspace, version, model, output style, context window, current usage, worktree, and rate limits.
- Track Claude rate-limit events with `status`, `resetsAt`, `rateLimitType`, `utilization`, `overageStatus`, `overageResetsAt`, `overageDisabledReason`, `isUsingOverage`, and `surpassedThreshold`.
- Distinguish `authentication_failed`, `billing_error`, `rate_limit`, `invalid_request`, `server_error`, `unknown`, and `max_output_tokens`.
- Surface long retry/reset waits immediately so the agent does not appear stuck.

Backlog from study:

- Add `status --full` grouped as Identity, Model, Account, Limits, Workspace, Permissions, Git, Handoff, Usage, Quality Gates.
- Add `statusline --json` for prompt/status scripts.
- Add `auth status <provider> --json` wrappers for Codex/OpenAI and Claude without token disclosure.
- Extend provider-limit persistence with Claude overage/rate-limit fields.
- Add token/context-window accounting to handoff and memory events.
- Add tests for status redaction, stale limits, missing limits, provider auth status, and JSON schema stability.

## Status Implementation Pass

Status: implemented partial

Implemented:

- `stagewarden status --full` and `stagewarden "status full"` render a Codex-style grouped dashboard.
- `stagewarden status --full --json` returns sections: identity, model, account, limits, workspace, permissions, git, handoff, usage, quality_gates.
- `stagewarden statusline --json` returns a Claude-style compact JSON surface for prompt/status scripts.
- `stagewarden auth status chatgpt --json` shells to `codex login status` and reports login state without token output.
- `stagewarden auth status claude --json` shells to `claude auth status --json` and reports login state without token output.
- CLI parser now accepts unquoted multi-word commands such as `stagewarden auth status chatgpt --json`.
- Read-only status commands use a read-only agent configuration and no longer create Git snapshots.

Validation:

- `python3 -m unittest tests/test_trace_cli.py` passed with 77 tests.
- Wet-run `python3 -m stagewarden.main status --full --json` passed.
- Wet-run `python3 -m stagewarden.main statusline --json` passed.
- Wet-run `python3 -m stagewarden.main auth status chatgpt --json` passed and detected ChatGPT login through Codex.
- Wet-run `python3 -m stagewarden.main auth status claude --json` passed and detected not-logged-in Claude state.

Remaining:

- Persist real provider-limit windows/credits when upstream CLIs expose them.
- Add first-class Claude overage fields to `.stagewarden_models.json` instead of only dashboard placeholders.
- Add token/context-window accounting from actual model calls.

<!-- STAGEWARDEN_RUNTIME_HANDOFF_START -->
## Runtime Handoff Export

Generated: 2026-04-19T11:06:05

### Current State

- task: unknown
- project_status: idle
- plan_status: unknown
- recovery_state: none
- stage_health: stable
- next_action: review current handoff and confirm next stage
- current_step: none
- git_boundary: baseline=unknown current=unknown
- pid_boundary: project_status=idle updated_at=2026-04-19T09:06:05+00:00

### Registers

governance=clean risks_open=0 risks_closed=0 issues_open=0 issues_closed=0 quality_open=0 quality_accepted=0 exception_plan_items=0

### Implementation Backlog

Implementation backlog:
- none

### Risks

Risk register:
- none

### Issues

Issue register:
- none

### Quality

Quality register:
- none

### Lessons

Lessons log:
- none

### Recent Entries

- none

<!-- STAGEWARDEN_RUNTIME_HANDOFF_END -->
