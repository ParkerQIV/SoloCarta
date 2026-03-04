import pytest
from app.engine.claude_runtime import build_agent_options, AgentRole


def test_build_agent_options_pm():
    options = build_agent_options(
        role=AgentRole.PM,
        sandbox_path="/tmp/sandbox",
    )
    assert options is not None
    assert "pm" in str(options.agents)


def test_build_agent_options_dev():
    options = build_agent_options(
        role=AgentRole.DEV,
        sandbox_path="/tmp/sandbox",
    )
    assert options is not None
    # Dev agent should have write/bash tools
    dev_agent = options.agents["dev"]
    assert "Bash" in dev_agent.tools
    assert "Write" in dev_agent.tools
