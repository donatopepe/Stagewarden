# Agent Handoff

## Current objective
Completed tenth round of deep codebase analysis. Identified ~341 lines of dead code in `status_views.py` and significant duplication across view modules.

## Current state
`stagewarden/main.py` is minimal (~80 lines). All `_main()` patterns eliminated. All bugs from rounds 1-8 fixed. Round 9 cleanup removed 139 lines from `tool_reports.py`. Round 10 analysis identified dead code but has NOT yet been removed.

### Tests
- 82 focused tests pass (executor, handoff, ljson, json_schema_registry, caveman, auth, prince2).
- Full `tests.test_trace_cli` suite times out at 10+ min (200 tests).

## Round 10 findings: Dead code in `status_views.py`

ALL of the following functions in `status_views.py` are DEAD CODE. Every external caller uses the `status_dashboard_views.py` version instead:

| Function | Lines | Called by |
|---|---|---|
| `_render_preflight` | 1958-1971 (~14) | Nothing (external callers use `_status_dashboard_views._render_preflight`) |
| `_render_report` | 1974-2008 (~35) | Nothing (external callers use `_status_dashboard_views._render_report`) |
| `_render_doctor` | 2011-2060 (~50) | Nothing (external callers use `_status_dashboard_views._render_doctor`) |
| `_status_remediation_report` | 1708-1752 (~45) | Nothing (line 1224 uses `_status_dashboard_views._status_remediation_report`) |
| `_preflight_report` | 1755-1806 (~52) | Only called by dead `_render_preflight` |
| `_report_report` | 1809-1853 (~45) | Only called by dead `_render_report` |
| `_doctor_report` | 1856-1955 (~100) | Only called by dead `_render_doctor` and dead `_preflight_report` |

**Total dead code: ~341 lines** (lines 1708-2060 of `status_views.py`, minus the `_preflight_remediations` function at 1597-1706 which IS used).

### Verified NOT dead (used internally by `status_views.py`)
- `_preflight_remediations` (line 1597) - Called by `_status_remediation_report` (dead) AND `_preflight_report` (dead). BUT also called at line 1767 inside `_status_dashboard_report` which IS used. So this function is ALIVE.
- `_render_shell_backend` (line 97) - Called at line 1352 in `_render_status_full`.
- `_shell_backend_report` (line 84) - Called at lines 280, 1720, 1770, 1787, 2018.

## Round 10 findings: Duplicate functions across modules

### 1. `_render_shell_backend` - IDENTICAL (~12 lines each)
- `shell_views.py:455` - Used by `cli_dispatch.py`, `command_views.py` via `_shell_views`
- `status_views.py:97` - Used internally at `status_views.py:1352`
- **Action**: Keep `shell_views.py` version, have `status_views.py` import from `_shell_views`.

### 2. `_shell_backend_report` - NEARLY IDENTICAL (~11 lines each)
- `shell_views.py:203` - Reads configured value from settings file via `_configured_shell_backend()`
- `status_views.py:84` and `status_dashboard_views.py:30` - Read from `config.shell_backend` attribute (set at startup by `cli_dispatch.py:92`)
- **Note**: Should return same value in normal operation. `shell_views.py` version does disk I/O each call; others use in-memory cache.

### 3. `_preflight_remediations` - NEARLY IDENTICAL (~110 lines each)
- `status_views.py:1597` and `status_dashboard_views.py:159`
- Each file only calls its own version. Same logic, different formatting.
- **Action**: Consolidate to single location.

### 4. `report_views.py` - NOT duplicates (intentional proxy pattern)
- All `_render_*` functions delegate to `_project_handoff_views` or `ProjectHandoff` methods.
- This is intentional re-export for different command routing paths.

## Important files
- `stagewarden/status_views.py` (2060 lines) - Contains ~341 lines of dead code (lines 1708-2060 minus `_preflight_remediations`).
- `stagewarden/status_dashboard_views.py` (502 lines) - Contains the ACTIVE versions of all dashboard functions.
- `stagewarden/shell_views.py` (1052 lines) - Contains canonical `_shell_backend_report` and `_render_shell_backend`.

## Technical decisions
- Dead code in `status_views.py` is safe to remove: all external callers explicitly import from `status_dashboard_views`.
- `_render_shell_backend` consolidation requires updating `status_views.py:1352` to use `_shell_views._render_shell_backend`.

## Open issues
- Bugs: `pytest` unavailable; use `python3 -m unittest`.
- Risks: ~341 lines of dead code in `status_views.py` ready for removal. ~220 lines of duplicate logic across view modules.
- Unknowns: None.

## Next steps
1. **HIGH PRIORITY**: Remove dead code from `status_views.py` (lines 1708-1752, 1755-1806, 1809-1853, 1856-1955, 1958-1971, 1974-2008, 2011-2060). Keep `_preflight_remediations` (1597-1706) as it is used by `_status_dashboard_report`.
2. **MEDIUM PRIORITY**: Consolidate `_render_shell_backend` - remove `status_views.py:97-108`, update `status_views.py:1352` to use `_shell_views._render_shell_backend`.
3. **LOW PRIORITY**: Consolidate `_preflight_remediations` and `_shell_backend_report` duplicates.

## Commands
```bash
# test
python3 -m unittest tests.test_trace_cli.TraceAndCliTests.test_agent_writes_ljson_trace
python3 -m unittest tests.test_executor tests.test_handoff tests.test_ljson tests.test_json_schema_registry tests.test_caveman tests.test_auth tests.test_prince2
```
