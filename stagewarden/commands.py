from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CommandSpec:
    name: str
    group: str
    description: str
    usage: str
    aliases: tuple[str, ...] = ()
    interactive: bool = True
    json: bool = False
    handler: str = ""

    def phrases(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["aliases"] = list(self.aliases)
        return payload


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec("help", "core", "Show interactive help.", "help [topic]", aliases=("commands help",), handler="help"),
    CommandSpec("slash", "core", "Show slash-command palette with workspace hints.", "slash [prefix]", json=True, handler="commands"),
    CommandSpec("commands", "core", "Show the structured command catalog.", "commands [--json]", json=True, handler="commands"),
    CommandSpec("exit", "core", "Close the interactive shell.", "exit", aliases=("quit",), handler="session"),
    CommandSpec("reset", "core", "Reset the in-memory agent session.", "reset", handler="session"),
    CommandSpec("overview", "core", "Show concise project overview.", "overview", json=True, handler="status"),
    CommandSpec("health", "core", "Show health signals.", "health", json=True, handler="status"),
    CommandSpec("report", "core", "Show execution report.", "report", json=True, handler="status"),
    CommandSpec("status", "core", "Show workspace, model, permission, handoff, and provider status.", "status [--full|--json]", json=True, handler="status"),
    CommandSpec("statusline", "core", "Emit compact statusline JSON.", "statusline", json=True, handler="status"),
    CommandSpec("preflight", "core", "Run read-only readiness checks before agent work.", "preflight [--json]", json=True, handler="status"),
    CommandSpec("stream on", "core", "Enable streaming output.", "stream on", handler="session"),
    CommandSpec("stream off", "core", "Disable streaming output.", "stream off", handler="session"),
    CommandSpec("stream status", "core", "Show streaming mode.", "stream status", handler="session"),
    CommandSpec("doctor", "core", "Validate local prerequisites and configuration.", "doctor [--json]", json=True, handler="doctor"),
    CommandSpec("shell backend", "core", "Show configured shell backend.", "shell backend", json=True, handler="shell"),
    CommandSpec("shell backend use", "core", "Set configured shell backend.", "shell backend use <auto|bash|zsh|powershell|cmd>", handler="shell"),
    CommandSpec("models", "models", "Show configured providers and provider-model selections.", "models", json=True, handler="models"),
    CommandSpec("models usage", "models", "Show recent model usage.", "models usage", json=True, handler="models"),
    CommandSpec("models limits", "models", "Show provider/account limit status.", "models limits", aliases=("model limits",), json=True, handler="models"),
    CommandSpec("model use", "models", "Set preferred provider.", "model use <local|cheap|chatgpt|openai|claude>", handler="models"),
    CommandSpec("model choose", "models", "Open guided provider/model/parameter menu.", "model choose [local|cheap|chatgpt|openai|claude]", handler="models"),
    CommandSpec("model preset", "models", "Apply or choose a provider preset.", "model preset <provider> [preset]", handler="models"),
    CommandSpec("model add", "models", "Enable a provider.", "model add <local|cheap|chatgpt|openai|claude>", handler="models"),
    CommandSpec("model remove", "models", "Disable a provider.", "model remove <local|cheap|chatgpt|openai|claude>", handler="models"),
    CommandSpec("model list", "models", "List provider-specific models.", "model list [local|cheap|chatgpt|openai|claude]", json=True, handler="models"),
    CommandSpec("model params", "models", "Show provider-model parameters.", "model params <local|cheap|chatgpt|openai|claude>", json=True, handler="models"),
    CommandSpec("model variant", "models", "Pin provider-specific model variant.", "model variant <provider> <variant>", handler="models"),
    CommandSpec("model variant-clear", "models", "Clear provider model variant pin.", "model variant-clear <provider>", handler="models"),
    CommandSpec("model block", "models", "Block provider until a known unlock time.", "model block <provider> until YYYY-MM-DDTHH:MM", handler="limits"),
    CommandSpec("model unblock", "models", "Clear provider block.", "model unblock <provider>", handler="limits"),
    CommandSpec("model limit-record", "models", "Record provider limit from message.", "model limit-record <provider> <message>", handler="limits"),
    CommandSpec("model limit-clear", "models", "Clear provider limit state.", "model limit-clear <provider>", handler="limits"),
    CommandSpec("model param set", "models", "Set one provider-model parameter.", "model param set <provider> <key> <value>", handler="models"),
    CommandSpec("model param clear", "models", "Clear one provider-model parameter.", "model param clear <provider> <key>", handler="models"),
    CommandSpec("model clear", "models", "Clear preferred provider.", "model clear", handler="models"),
    CommandSpec("cost", "models", "Show cost and routing summary.", "cost", json=True, handler="models"),
    CommandSpec("accounts", "accounts", "Show account profiles.", "accounts", json=True, handler="accounts"),
    CommandSpec("auth status", "accounts", "Show provider authentication status.", "auth status <provider>", json=True, handler="accounts"),
    CommandSpec("account add", "accounts", "Add provider account profile.", "account add <provider> <name> [ENV_VAR]", handler="accounts"),
    CommandSpec("account choose", "accounts", "Open guided account selection menu.", "account choose [provider]", handler="accounts"),
    CommandSpec("account login", "accounts", "Start provider login and save credentials.", "account login <chatgpt|openai> <name>", handler="accounts"),
    CommandSpec("account login-device", "accounts", "Start OpenAI/ChatGPT device-code login.", "account login-device <chatgpt|openai> <name>", handler="accounts"),
    CommandSpec("account import", "accounts", "Import provider-owned credentials.", "account import <provider> <name> [path]", handler="accounts"),
    CommandSpec("account env", "accounts", "Set account token environment variable.", "account env <provider> <name> <ENV_VAR>", handler="accounts"),
    CommandSpec("account use", "accounts", "Select active account profile.", "account use <provider> <name>", handler="accounts"),
    CommandSpec("account logout", "accounts", "Delete saved account token.", "account logout <provider> <name>", handler="accounts"),
    CommandSpec("account remove", "accounts", "Remove account profile.", "account remove <provider> <name>", handler="accounts"),
    CommandSpec("account block", "accounts", "Block account until a known unlock time.", "account block <provider> <name> until YYYY-MM-DDTHH:MM", handler="limits"),
    CommandSpec("account unblock", "accounts", "Clear account block.", "account unblock <provider> <name>", handler="limits"),
    CommandSpec("account limit-record", "accounts", "Record account limit from message.", "account limit-record <provider> <name> <message>", handler="limits"),
    CommandSpec("account limit-clear", "accounts", "Clear account limit state.", "account limit-clear <provider> <name>", handler="limits"),
    CommandSpec("account clear", "accounts", "Clear active account for provider.", "account clear <provider>", handler="accounts"),
    CommandSpec("roles", "prince2", "Show PRINCE2 role-to-model assignments.", "roles", json=True, handler="roles"),
    CommandSpec("project brief", "prince2", "Show the persisted structured project brief.", "project brief [--json]", json=True, handler="roles"),
    CommandSpec("project brief set", "prince2", "Set one structured project-brief field.", "project brief set <field> <value>", handler="roles"),
    CommandSpec("project brief clear", "prince2", "Clear one or all structured project-brief fields.", "project brief clear [field]", handler="roles"),
    CommandSpec("project tree propose", "prince2", "Propose a proportional PRINCE2 organization tree from the project brief; add --ai to ask an available model for review-only tree patches.", "project tree propose [--ai] [--json]", json=True, handler="roles"),
    CommandSpec("project tree approve", "prince2", "Approve and persist the current project-tree proposal.", "project tree approve [--force] [--json]", json=True, handler="roles"),
    CommandSpec("roles setup", "prince2", "Open guided PRINCE2 role setup.", "roles setup", handler="roles"),
    CommandSpec("roles propose", "prince2", "Apply automatic PRINCE2 role assignment proposal.", "roles propose", aliases=("project start",), handler="roles"),
    CommandSpec("project start --ai", "prince2", "Run controlled project startup while forcing AI-assisted tree proposal review.", "project start --ai", handler="roles"),
    CommandSpec("project design", "prince2", "Show the design packet that future AI tree planning must receive.", "project design [--json]", json=True, handler="roles"),
    CommandSpec("roles domains", "prince2", "Show role domains and context visibility boundaries.", "roles domains [--json]", json=True, handler="roles"),
    CommandSpec("roles tree", "prince2", "Show hierarchical PRINCE2 organization tree and node context boundaries.", "roles tree [--json]", json=True, handler="roles"),
    CommandSpec("roles tree approve", "prince2", "Approve and persist the current PRINCE2 role-tree baseline.", "roles tree approve [--json]", json=True, handler="roles"),
    CommandSpec("roles baseline", "prince2", "Show the approved PRINCE2 role-tree baseline.", "roles baseline [--json]", json=True, handler="roles"),
    CommandSpec("roles baseline matrix", "prince2", "Show the approved role-tree baseline matrix including delegated nodes and route pools.", "roles baseline matrix [--json]", json=True, handler="roles"),
    CommandSpec("roles check", "prince2", "Validate PRINCE2 role tree readiness, rate-limit state, and independence warnings.", "roles check [--json]", json=True, handler="roles"),
    CommandSpec("roles flow", "prince2", "Show authorized PRINCE2 flow edges between role-tree nodes.", "roles flow [--json]", json=True, handler="roles"),
    CommandSpec("roles matrix", "prince2", "Show combined PRINCE2 role tree, flow, assignment, limit, and readiness matrix.", "roles matrix [--json]", json=True, handler="roles"),
    CommandSpec("role configure", "prince2", "Configure one PRINCE2 role assignment.", "role configure [role]", handler="roles"),
    CommandSpec("role clear", "prince2", "Clear one PRINCE2 role assignment.", "role clear <role>", handler="roles"),
    CommandSpec("role add-child", "prince2", "Add a delegated PRINCE2 child node to the approved role-tree baseline.", "role add-child [parent_node role_type [node_id]]", handler="roles"),
    CommandSpec("role assign", "prince2", "Assign provider/provider-model/params to one PRINCE2 role-tree node.", "role assign [node_id provider provider_model [reasoning_effort=<value>] [account=<name>] [pool=<primary|reviewer|fallback>]]", handler="roles"),
    CommandSpec("handoff", "handoff", "Show persisted PRINCE2 handoff context.", "handoff", json=True, handler="handoff"),
    CommandSpec("handoff actions", "handoff", "Show durable action/audit entries from handoff.", "handoff actions [limit] [--json]", json=True, handler="handoff"),
    CommandSpec("handoff export", "handoff", "Export runtime handoff to HANDOFF.md.", "handoff export", aliases=("handoff md",), handler="handoff"),
    CommandSpec("board", "handoff", "Show project board view.", "board", json=True, handler="handoff"),
    CommandSpec("stage review", "handoff", "Show stage boundary review.", "stage review", json=True, handler="handoff"),
    CommandSpec("resume", "handoff", "Show implicit resume summary.", "resume", aliases=("resume context", "resume --show"), json=True, handler="handoff"),
    CommandSpec("resume --clear", "handoff", "Clear resume context.", "resume --clear", handler="handoff"),
    CommandSpec("boundary", "handoff", "Show current boundary recommendation.", "boundary", json=True, handler="handoff"),
    CommandSpec("risks", "handoff", "Show risk register.", "risks", json=True, handler="handoff"),
    CommandSpec("issues", "handoff", "Show issue register.", "issues", json=True, handler="handoff"),
    CommandSpec("quality", "handoff", "Show quality register.", "quality", json=True, handler="handoff"),
    CommandSpec("exception", "handoff", "Show exception plan lane.", "exception", json=True, handler="handoff"),
    CommandSpec("lessons", "handoff", "Show lessons log.", "lessons", json=True, handler="handoff"),
    CommandSpec("transcript", "handoff", "Show recent tool transcript.", "transcript", aliases=("trace",), json=True, handler="handoff"),
    CommandSpec("todo", "handoff", "Show implementation backlog.", "todo", json=True, handler="handoff"),
    CommandSpec("permissions", "permissions", "Show permission settings.", "permissions", json=True, handler="permissions"),
    CommandSpec("permission mode", "permissions", "Set workspace permission mode.", "permission mode <default|accept_edits|plan|auto|dont_ask>", handler="permissions"),
    CommandSpec("permission allow", "permissions", "Add workspace allow rule.", "permission allow <rule>", handler="permissions"),
    CommandSpec("permission ask", "permissions", "Add workspace ask rule.", "permission ask <rule>", handler="permissions"),
    CommandSpec("permission deny", "permissions", "Add workspace deny rule.", "permission deny <rule>", handler="permissions"),
    CommandSpec("permission reset", "permissions", "Reset workspace permission settings.", "permission reset", handler="permissions"),
    CommandSpec("permission session mode", "permissions", "Set session-only permission mode.", "permission session mode <default|accept_edits|plan|auto|dont_ask>", handler="permissions"),
    CommandSpec("permission session allow", "permissions", "Add session-only allow rule.", "permission session allow <rule>", handler="permissions"),
    CommandSpec("permission session ask", "permissions", "Add session-only ask rule.", "permission session ask <rule>", handler="permissions"),
    CommandSpec("permission session deny", "permissions", "Add session-only deny rule.", "permission session deny <rule>", handler="permissions"),
    CommandSpec("permission session reset", "permissions", "Clear session-only permission overrides.", "permission session reset", handler="permissions"),
    CommandSpec("sessions", "shell", "List persistent shell sessions.", "sessions", aliases=("session list",), json=True, handler="sessions"),
    CommandSpec("session create", "shell", "Create persistent shell session.", "session create [cwd]", handler="sessions"),
    CommandSpec("session send last", "shell", "Run command in last persistent shell session.", "session send <id|last> <command>", handler="sessions"),
    CommandSpec("session close last", "shell", "Close persistent shell session.", "session close <id|last>", handler="sessions"),
    CommandSpec("patch preview", "files", "Preview a patch target path.", "patch preview <path>", handler="files"),
    CommandSpec("web search", "external_io", "Run governed web search with result evidence.", "web search <query>", json=True, handler="external_io"),
    CommandSpec("download", "external_io", "Download HTTP/HTTPS file inside workspace with checksum evidence.", "download <url> [path] [--max-bytes N]", json=True, handler="external_io"),
    CommandSpec("checksum", "external_io", "Compute SHA-256 for a workspace file.", "checksum <path>", json=True, handler="external_io"),
    CommandSpec("compress", "external_io", "Gzip-compress one workspace file.", "compress <path> [target.gz]", json=True, handler="external_io"),
    CommandSpec("archive verify", "external_io", "Verify a gzip archive and report checksum evidence.", "archive verify <path.gz>", json=True, handler="external_io"),
    CommandSpec("git status", "git", "Show git branch and working tree status.", "git status", json=True, handler="git"),
    CommandSpec("git log", "git", "Show recent commits.", "git log [limit]", json=True, handler="git"),
    CommandSpec("git history", "git", "Show commit history for a path.", "git history <path> [limit]", json=True, handler="git"),
    CommandSpec("git show", "git", "Show revision contents.", "git show [revision]", handler="git"),
    CommandSpec("git show --stat", "git", "Show revision stats.", "git show --stat [revision]", handler="git"),
    CommandSpec("sources", "sources", "Show local external source repositories.", "sources", aliases=("sources status",), json=True, handler="sources"),
    CommandSpec("sources status --strict", "sources", "Fail sources status when any source is missing or mismatched.", "sources status --strict", json=True, handler="sources"),
    CommandSpec("sources update", "sources", "Fast-forward local external source repositories and record evidence.", "sources update", json=True, handler="sources"),
    CommandSpec("update status", "update", "Show controlled self-update state for the current repository.", "update status", json=True, handler="update"),
    CommandSpec("update check", "update", "Fetch upstream metadata and report whether an update is available.", "update check [--json]", json=True, handler="update"),
    CommandSpec("update apply", "update", "Apply a fast-forward self-update after explicit confirmation.", "update apply --yes", json=True, handler="update"),
    CommandSpec("mode normal", "caveman", "Switch to normal mode.", "mode normal", handler="caveman"),
    CommandSpec("mode caveman", "caveman", "Switch to Caveman mode.", "mode caveman [level]", handler="caveman"),
    CommandSpec("mode plan", "caveman", "Switch to plan permission mode.", "mode plan", handler="caveman"),
    CommandSpec("mode auto", "caveman", "Switch to auto permission mode.", "mode auto", handler="caveman"),
    CommandSpec("mode accept-edits", "caveman", "Switch to accept-edits permission mode.", "mode accept-edits", handler="caveman"),
    CommandSpec("mode dont-ask", "caveman", "Switch to dont-ask permission mode.", "mode dont-ask", handler="caveman"),
    CommandSpec("mode default", "caveman", "Switch to default permission mode.", "mode default", handler="caveman"),
    CommandSpec("caveman help", "caveman", "Show Caveman command help.", "caveman help", handler="caveman"),
    CommandSpec("caveman on", "caveman", "Enable Caveman mode.", "caveman on [level]", handler="caveman"),
    CommandSpec("caveman off", "caveman", "Disable Caveman mode.", "caveman off", aliases=("stop caveman", "normal mode"), handler="caveman"),
)


def command_specs() -> tuple[CommandSpec, ...]:
    return COMMAND_SPECS


def command_catalog() -> list[dict[str, object]]:
    return [spec.to_dict() for spec in COMMAND_SPECS]


def command_usages_for_groups(*groups: str) -> list[str]:
    selected = set(groups)
    usages: list[str] = []
    for spec in COMMAND_SPECS:
        if spec.group not in selected:
            continue
        usage = spec.usage
        if spec.aliases:
            usage = " | ".join((usage, *spec.aliases))
        usages.append(usage)
    return usages


def command_phrases() -> tuple[str, ...]:
    seen: set[str] = set()
    phrases: list[str] = []
    for spec in COMMAND_SPECS:
        for phrase in spec.phrases():
            if phrase not in seen:
                seen.add(phrase)
                phrases.append(phrase)
    return tuple(phrases)


def command_specs_by_prefix(prefix: str) -> list[CommandSpec]:
    lowered = prefix.strip().lower()
    matches: list[CommandSpec] = []
    for spec in COMMAND_SPECS:
        phrases = tuple(phrase.lower() for phrase in spec.phrases())
        if not lowered or any(phrase.startswith(lowered) for phrase in phrases):
            matches.append(spec)
    return matches


def render_command_catalog() -> str:
    groups: dict[str, list[CommandSpec]] = {}
    for spec in COMMAND_SPECS:
        groups.setdefault(spec.group, []).append(spec)
    lines = ["Stagewarden command catalog:"]
    for group in sorted(groups):
        lines.extend(("", f"{group}:"))
        for spec in groups[group]:
            json_suffix = " json" if spec.json else ""
            lines.append(f"- {spec.usage}{json_suffix}")
            lines.append(f"  {spec.description}")
    return "\n".join(lines)
