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
    examples: tuple[str, ...] = ()

    def phrases(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["aliases"] = list(self.aliases)
        return payload


@dataclass(frozen=True)
class HelpTopic:
    key: str
    title: str
    summary: str = ""
    groups: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()
    extra_lines: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    def to_lines(self) -> list[str]:
        lines = [self.title, ""]
        if self.groups:
            lines.extend(f"- {usage}" for usage in command_usages_for_groups(*self.groups))
        if self.extra_lines:
            if lines and lines[-1] != "":
                lines.append("")
            lines.extend(self.extra_lines)
        if self.examples:
            if lines and lines[-1] != "":
                lines.append("")
            lines.append("Examples:")
            lines.extend(f"- stagewarden> {example}" for example in self.examples)
        return lines

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "summary": self.summary,
            "aliases": list(self.aliases),
            "groups": list(self.groups),
            "commands": command_usages_for_groups(*self.groups),
            "examples": list(self.examples),
            "extra_lines": list(self.extra_lines),
        }


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec("help", "core", "Show interactive help and help-topic metadata.", "help [topic] [--json]", aliases=("commands help", "help topics"), json=True, handler="help"),
    CommandSpec("slash", "core", "Show slash-command palette with workspace hints.", "slash [prefix]", json=True, handler="commands"),
    CommandSpec("slash choose", "core", "Open a guided slash-command chooser.", "slash choose [query]", handler="commands", examples=("choose command", "command picker")),
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
    CommandSpec("model choose", "models", "Open guided provider/model/parameter menu.", "model choose [local|cheap|chatgpt|openai|claude]", handler="models", examples=("model choose chatgpt", "choose model", "provider picker")),
    CommandSpec("model preset", "models", "Apply or choose a provider preset.", "model preset <provider> [preset]", handler="models"),
    CommandSpec("model add", "models", "Enable a provider.", "model add <local|cheap|chatgpt|openai|claude>", handler="models"),
    CommandSpec("model remove", "models", "Disable a provider.", "model remove <local|cheap|chatgpt|openai|claude>", handler="models"),
    CommandSpec("model inspect", "models", "Inspect dynamic provider-model peculiarities, with AI synthesis for discovered local models.", "model inspect <provider> [provider_model]", json=True, handler="models"),
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
    CommandSpec("roles context", "prince2", "Show the AI context packet for one PRINCE2 runtime node.", "roles context <node_id> [--json]", json=True, handler="roles"),
    CommandSpec("roles runtime", "prince2", "Show the materialized PRINCE2 node runtime derived from the approved baseline.", "roles runtime [--json]", json=True, handler="roles"),
    CommandSpec("roles active", "prince2", "Show only active PRINCE2 runtime nodes that are not yet completed.", "roles active [--json]", json=True, handler="roles"),
    CommandSpec("roles queues", "prince2", "Show compact queue/inbox/outbox supervision for the PRINCE2 runtime.", "roles queues [--json]", json=True, handler="roles"),
    CommandSpec("roles control", "prince2", "Show a board-facing PRINCE2 control view with blockers, queue pressure, and next gating action.", "roles control [--json]", json=True, handler="roles"),
    CommandSpec("roles tick", "prince2", "Advance the PRINCE2 runtime in batch across eligible nodes.", "roles tick [max_nodes] [--json]", json=True, handler="roles"),
    CommandSpec("roles messages", "prince2", "Show PRINCE2 node inbox/outbox messages, optionally for one node.", "roles messages [node_id] [--json]", json=True, handler="roles"),
    CommandSpec("roles check", "prince2", "Validate PRINCE2 role tree readiness, rate-limit state, and independence warnings.", "roles check [--json]", json=True, handler="roles"),
    CommandSpec("roles flow", "prince2", "Show authorized PRINCE2 flow edges between role-tree nodes.", "roles flow [--json]", json=True, handler="roles"),
    CommandSpec("roles matrix", "prince2", "Show combined PRINCE2 role tree, flow, assignment, limit, and readiness matrix.", "roles matrix [--json]", json=True, handler="roles"),
    CommandSpec("role configure", "prince2", "Configure one PRINCE2 role assignment.", "role configure [role]", handler="roles", examples=("role configure project_manager", "assign role model", "prince2 role model")),
    CommandSpec("role clear", "prince2", "Clear one PRINCE2 role assignment.", "role clear <role>", handler="roles"),
    CommandSpec("role add-child", "prince2", "Add a delegated PRINCE2 child node to the approved role-tree baseline.", "role add-child [parent_node role_type [node_id]]", handler="roles"),
    CommandSpec("role assign", "prince2", "Assign provider/provider-model/params to one PRINCE2 role-tree node.", "role assign [node_id provider provider_model [reasoning_effort=<value>] [account=<name>] [pool=<primary|reviewer|fallback>]]", handler="roles"),
    CommandSpec("role message", "prince2", "Send a governed PRINCE2 node-to-node message through an approved flow edge.", "role message <source_node> <target_node> <edge_id> payload=<scope1,scope2> [evidence=<ref1,ref2>] [summary=<text_with_underscores>]", json=True, handler="roles"),
    CommandSpec("role wait", "prince2", "Put one PRINCE2 runtime node into waiting state with explicit wake triggers.", "role wait <node_id> reason=<text_with_underscores> [wake=<trigger1,trigger2>]", json=True, handler="roles"),
    CommandSpec("role wake", "prince2", "Wake one waiting PRINCE2 runtime node with an authorized trigger.", "role wake <node_id> trigger=<name>", json=True, handler="roles"),
    CommandSpec("role tick", "prince2", "Advance one PRINCE2 runtime node lifecycle by one orchestrated step.", "role tick <node_id>", json=True, handler="roles"),
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
    CommandSpec("file inspect", "files", "Inspect file text encoding and newline metadata.", "file inspect <path> [--json]", json=True, handler="files"),
    CommandSpec("file stat", "files", "Inspect file or directory metadata and permissions.", "file stat <path> [--json]", json=True, handler="files"),
    CommandSpec("file copy", "files", "Copy a file or directory inside the workspace.", "file copy <source> <destination> [--overwrite] [--dry-run] [--json]", json=True, handler="files"),
    CommandSpec("file move", "files", "Move or rename a file or directory inside the workspace.", "file move <source> <destination> [--overwrite] [--dry-run] [--json]", json=True, handler="files"),
    CommandSpec("file delete", "files", "Delete a file or directory inside the workspace.", "file delete <path> [--recursive] [--dry-run] [--json]", json=True, handler="files"),
    CommandSpec("file chmod", "files", "Update octal mode for a file or directory.", "file chmod <path> <mode> [--recursive] [--dry-run] [--json]", json=True, handler="files"),
    CommandSpec("file chown", "files", "Update owner/group for a file or directory when supported.", "file chown <path> <user> [group] [--recursive] [--dry-run] [--json]", json=True, handler="files"),
    CommandSpec("patch preview", "files", "Preview a patch target path.", "patch preview <path>", handler="files"),
    CommandSpec("web search", "external_io", "Run governed web search with result evidence.", "web search <query>", json=True, handler="external_io", examples=("search web", "research online", "rete ricerca")),
    CommandSpec("download", "external_io", "Download HTTP/HTTPS file inside workspace with checksum evidence.", "download <url> [path] [--max-bytes N]", json=True, handler="external_io", examples=("download file", "scarica file", "fetch artifact")),
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
    CommandSpec("update status", "update", "Show controlled self-update state for the current repository.", "update status", json=True, handler="update", examples=("self update status", "version status")),
    CommandSpec("update check", "update", "Fetch upstream metadata and report whether an update is available.", "update check [--json]", json=True, handler="update", examples=("check for updates", "new version")),
    CommandSpec("update apply", "update", "Apply a fast-forward self-update after explicit confirmation.", "update apply --yes", json=True, handler="update", examples=("apply update", "upgrade stagewarden")),
    CommandSpec("extensions", "extensions", "Discover local Stagewarden extensions without executing them.", "extensions", json=True, handler="extensions", examples=("list extensions", "plugin list")),
    CommandSpec("extension scaffold", "extensions", "Create a safe local extension scaffold.", "extension scaffold <name>", json=True, handler="extensions", examples=("create extension", "new plugin")),
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


HELP_TOPICS: tuple[HelpTopic, ...] = (
    HelpTopic(
        key="core",
        title="Core commands",
        summary="exit, reset, overview, health, report, status, preflight, stream, sessions, transcript",
        extra_lines=(
            "- help [topic]",
            "- exit | quit",
            "- reset",
            "- overview",
            "- health",
            "- report",
            "- status",
            "- status full",
            "- statusline",
            "- preflight",
            "- shell backend",
            "- shell backend use <auto|bash|zsh|powershell|cmd>",
            "- auth status <chatgpt|claude>",
            "- stream on | stream off | stream status",
            "- transcript | trace",
            "- doctor",
            "- sessions | session list",
            "- session create [cwd]",
            "- session send <id|last> <command>",
            "- session close <id|last>",
            "- patch preview <diff-file>",
        ),
        examples=(
            "overview",
            "health",
            "report",
            "status",
            "status full",
            "statusline",
            "preflight",
            "shell backend",
            "shell backend use zsh",
            "auth status chatgpt",
            "stream off",
            "doctor",
            "session create",
            "session send last pwd",
            "patch preview changes.diff",
            "transcript",
        ),
        aliases=("sessions", "session"),
    ),
    HelpTopic(
        key="models",
        title="Model commands",
        summary="provider routing, provider models, blocks",
        groups=("models",),
        examples=(
            "models usage",
            "model limits",
            "model choose chatgpt",
            "model list claude",
            "model params chatgpt",
            "model variant openai gpt-5.4-mini",
            "model preset chatgpt",
            "model param set chatgpt reasoning_effort high",
            "model limit-record chatgpt You've hit your usage limit. Try again at 8:05 PM.",
        ),
        aliases=("model",),
    ),
    HelpTopic(
        key="accounts",
        title="Account commands",
        summary="provider profiles, login, env vars, usage limits",
        groups=("accounts",),
        examples=(
            "account login chatgpt personale",
            "account choose openai",
            "account login-device openai lavoro",
            "account add openai lavoro OPENAI_API_KEY_WORK",
            "account import claude lavoro ~/.claude/.credentials.json",
        ),
        aliases=("account",),
    ),
    HelpTopic(
        key="permissions",
        title="Permission commands",
        summary="plan/auto modes, allow/ask/deny rules",
        groups=("permissions",),
        examples=(
            "permission mode plan",
            "permission ask shell:python3 -m unittest",
            "permission session allow shell:git status",
        ),
        aliases=("permission", "perm"),
    ),
    HelpTopic(
        key="handoff",
        title="Handoff and PRINCE2 commands",
        summary="overview, PRINCE2 handoff, board review, registers, backlog",
        groups=("handoff", "prince2"),
        examples=(
            "overview",
            "handoff",
            "board",
            "roles",
            "roles domains",
            "resume --show",
            "boundary",
            "handoff export",
        ),
        aliases=("prince2",),
    ),
    HelpTopic(
        key="git",
        title="Git commands",
        summary="status, log, file history, show",
        groups=("git",),
        examples=(
            "git status",
            "git log 5",
            "git history stagewarden/main.py 10",
        ),
        aliases=("history",),
    ),
    HelpTopic(
        key="update",
        title="Update commands",
        summary="source sync, self-update status, checks, fast-forward apply",
        groups=("update", "sources"),
        examples=(
            "sources status --strict",
            "sources update",
            "update status",
            "update check --json",
            "update apply --yes",
        ),
    ),
    HelpTopic(
        key="files",
        title="File commands",
        summary="inspect, stat, copy, move, delete, chmod, chown, patch preview",
        groups=("files",),
        examples=(
            "file inspect README.md",
            "file stat stagewarden",
            "file copy README.md docs/README.copy.md --dry-run",
            "file move docs/old.md docs/new.md",
            "file delete build --recursive --dry-run",
            "file chmod scripts/run.sh 0755",
            "file chown cache 501 20 --recursive",
            "patch preview changes.diff",
        ),
        aliases=("file", "fs"),
    ),
    HelpTopic(
        key="external_io",
        title="External IO commands",
        summary="web search, download, checksum, compression, archive verify",
        groups=("external_io",),
        examples=(
            "web search Stagewarden coding agent",
            "download https://example.com/file.txt artifacts/file.txt --max-bytes 1048576",
            "checksum artifacts/file.txt",
            "compress artifacts/file.txt",
            "archive verify artifacts/file.txt.gz",
        ),
        aliases=("io", "network", "download"),
    ),
    HelpTopic(
        key="extensions",
        title="Extension commands",
        summary="extension discovery and scaffold",
        groups=("extensions",),
        examples=(
            "extensions",
            "extension scaffold local-tools",
        ),
        aliases=("extension",),
    ),
    HelpTopic(
        key="caveman",
        title="Caveman commands",
        summary="Caveman aliases and modes",
        extra_lines=(
            "- /caveman help",
            "- /caveman <lite|full|ultra|wenyan-lite|wenyan|wenyan-ultra> <task>",
            "- /caveman commit",
            "- /caveman review",
            "- /caveman compress <file>",
            "- caveman help | caveman on [level] | caveman off",
            "- mode caveman <level>",
            "- mode normal",
        ),
        examples=(
            "caveman on ultra",
            "/caveman review",
            "mode normal",
        ),
    ),
    HelpTopic(
        key="ljson",
        title="LJSON commands",
        summary="encode, decode, benchmark",
        extra_lines=(
            "- stagewarden --ljson-encode records.json [--ljson-output out.ljson]",
            "- stagewarden --ljson-decode records.ljson [--ljson-output records.json]",
            "- stagewarden --ljson-encode records.json --ljson-numeric --ljson-gzip",
            "- stagewarden --ljson-benchmark records.json",
        ),
        examples=(
            "python3 -m stagewarden.main --ljson-encode data.json",
            "python3 -m stagewarden.main --ljson-benchmark data.json",
        ),
    ),
)


def command_specs() -> tuple[CommandSpec, ...]:
    return COMMAND_SPECS


def help_topics() -> tuple[HelpTopic, ...]:
    return HELP_TOPICS


def help_topic_entry(topic: str) -> HelpTopic | None:
    lowered = topic.strip().lower()
    for item in HELP_TOPICS:
        if lowered == item.key or lowered in item.aliases:
            return item
    return None


def help_topic_lines(topic: str) -> list[str] | None:
    item = help_topic_entry(topic)
    return None if item is None else item.to_lines()


def help_topic_catalog() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in HELP_TOPICS:
        items.append(
            {
                "key": item.key,
                "title": item.title,
                "summary": item.summary,
                "aliases": list(item.aliases),
                "examples": list(item.examples),
            }
        )
    return items


def help_topic_report(topic: str | None = None) -> dict[str, object]:
    if topic is None:
        return {"command": "help", "topics": help_topic_catalog()}
    item = help_topic_entry(topic)
    if item is None:
        return {
            "command": "help",
            "ok": False,
            "topic": topic,
            "message": f"Unknown help topic: {topic}",
            "topics": help_topic_catalog(),
        }
    payload = item.to_dict()
    payload["command"] = "help"
    payload["ok"] = True
    payload["topic"] = item.key
    return payload


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


def _fuzzy_score(query: str, candidate: str) -> int | None:
    lowered_query = query.strip().lower()
    lowered_candidate = candidate.strip().lower()
    if not lowered_query:
        return 0
    if lowered_candidate.startswith(lowered_query):
        return 0
    if lowered_query in lowered_candidate:
        return 10 + lowered_candidate.index(lowered_query)
    position = 0
    gaps = 0
    for char in lowered_query:
        found = lowered_candidate.find(char, position)
        if found < 0:
            return None
        gaps += max(0, found - position)
        position = found + 1
    return 100 + gaps + len(lowered_candidate)


def command_specs_by_query(query: str) -> list[CommandSpec]:
    lowered = query.strip().lower()
    if not lowered:
        return list(COMMAND_SPECS)
    scored: list[tuple[int, int, CommandSpec]] = []
    for index, spec in enumerate(COMMAND_SPECS):
        scores = [
            score
            for phrase in (spec.name, spec.usage, spec.description, *spec.aliases, *spec.examples)
            if (score := _fuzzy_score(lowered, phrase)) is not None
        ]
        if scores:
            scored.append((min(scores), index, spec))
    scored.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in scored]


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
