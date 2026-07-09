# pi Agent Learning Benchmark

> Compiled from pi docs: prompt-templates, extensions, skills, SDK, TUI, sessions, RPC mode, packages.
> Study date: 2026-07-09

## 1. Prompt Templates

**pi pattern**: `.pi/prompts/*.md` with YAML frontmatter (`description`, `argument-hint`).  
Type `/name` to expand. Autocomplete shows available templates.

**Stagewarden alignment**: Already uses `.pi/prompts/*.md` with `description`+`argument-hint`.  
**Gap**: No `/name` interactive expansion in Stagewarden shell; templates are read at command-runtime but not as live agent prompts.

**Recommendation**: Expose prompt templates via `stagewarden> /goal-root <task>` slash command.

## 2. Extensions

**pi pattern**: TypeScript modules loaded from `~/.pi/agent/extensions/` or `.pi/extensions/`.  
Key capabilities: custom tools (`pi.registerTool()`), event interception (`onToolCall`), user interaction (`ctx.ui`), custom commands (`pi.registerCommand()`), session persistence (`pi.appendEntry()`).

**Stagewarden alignment**: Stagewarden has its own extension system under `.stagewarden/extensions/<name>/` with `commands/`, `roles/`, `skills/`, `hooks/`, `mcp/`.  
**Gap**: Stagewarden extensions are read-only scaffold; no runtime execution of extension code yet. No event lifecycle.

**Recommendation**: Enable extension execution in sandboxed contexts. Add lifecycle hooks (onNodeStart, onNodeComplete) for goal-loop integration.

## 3. Skills (Agent Skills Standard)

**pi pattern**: Self-contained `.md` files with a `SKILL.md` entry point. Follows [agentskills.io](https://agentskills.io/specification).  
Skills provide specialized workflows, setup instructions, helper scripts.

**Stagewarden alignment**: No skill loading system independent of extensions.  
**Recommendation**: Adopt Agent Skills standard in Stagewarden for reusable goal-loop subroutines.

## 4. SDK / Embedding

**pi pattern**: `createAgentSession()` from `@earendil-works/pi-coding-agent` for embedding agent capabilities in other apps.  
Full control over session lifecycle, model registry, auth storage.

**Stagewarden alignment**: Stagewarden runs as a standalone CLI, not embeddable.  
**Recommendation**: Expose a `GoalLoopSession` that external tools can call to programmatically start/stop loop runs.

## 5. RPC Mode

**pi pattern**: `pi --mode rpc` provides JSONL protocol over stdin/stdout.  
Commands: `prompt`, `continue`. Events: `message_update`, `turn_end`, `tool_call`, etc.

**Stagewarden alignment**: Stagewarden has `--json` output but no streaming RPC.  
**Recommendation**: Add `--mode rpc` to goal-loop commands for headless integration.

## 6. Session Control

**pi pattern**: `--session-control` enables per-session control socket under `~/.pi/session-control`.  
External tools can send messages to running sessions.

**Stagewarden alignment**: No session-control equivalent.  
**Recommendation**: Add control socket for goal-loop sessions so external tools can inject messages or abort nodes.

## 7. TUI Components

**pi pattern**: `@earendil-works/pi-tui` provides Component interface with render/handleInput/invalidate.  
Supports custom UI, focusable inputs, IME, styled output.

**Stagewarden alignment**: No TUI component system. Uses shell-based interaction.  
**Recommendation**: Not needed for Stagewarden's current domain; acknowledge but de-prioritize.

## 8. Packages

**pi pattern**: npm packages with `pi.extensions`, `pi.skills`, `pi.promptTemplates`, `pi.themes` entries in `package.json`.  
Shareable via npm or git.

**Stagewarden alignment**: Stagewarden extensions are project-local only.  
**Recommendation**: Enable Stagewarden package discovery for sharing goal-loop templates and orchestrator plugins.

## Priority Roadmap

1. **Prompt template slash commands** – low effort, high impact for goal-loop interactivity
2. **Extension runtime execution** – unlocks custom node implementations
3. **RPC mode for goal loop** – enables CI/CD integration
4. **Control socket** – enables external node injection and real-time monitoring
5. **Skills standard adoption** – aligns with industry agent-skills ecosystem
