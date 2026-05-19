from __future__ import annotations

from dataclasses import replace

from .agent import Agent
from .config import AgentConfig
from . import model_views as _model_views
from . import status_views as _status_views


def _configure_agent_for_workspace(config: AgentConfig) -> Agent:
    agent = Agent(config)
    _model_views._apply_model_preferences(agent, config)
    _status_views._provider_limit_status_report(agent, config)
    return agent


def _configure_readonly_agent_for_workspace(config: AgentConfig) -> Agent:
    readonly_config = replace(config, enforce_git=False, auto_git_commit=False)
    agent = Agent(readonly_config)
    _model_views._apply_model_preferences(agent, readonly_config)
    return agent


def _refresh_runtime_permissions(agent: Agent) -> None:
    agent.refresh_permissions()
