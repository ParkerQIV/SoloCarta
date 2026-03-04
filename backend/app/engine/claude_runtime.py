"""Claude Agent SDK runtime wrapper with role-based tool configuration."""

from enum import Enum
from pathlib import Path

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions


class AgentRole(str, Enum):
    PM = "pm"
    ARCHITECT = "architect"
    PLANNER = "planner"
    DEV = "dev"
    QA = "qa"
    REVIEWER = "reviewer"
    GATEKEEPER = "gatekeeper"


# Tools available per agent role
AGENT_TOOLS: dict[AgentRole, list[str]] = {
    AgentRole.PM: ["Read", "Glob", "Grep"],
    AgentRole.ARCHITECT: ["Read", "Glob", "Grep"],
    AgentRole.PLANNER: ["Read", "Glob", "Grep"],
    AgentRole.DEV: ["Read", "Write", "Edit", "Bash", "Glob", "Grep"],
    AgentRole.QA: ["Read", "Bash", "Glob", "Grep"],
    AgentRole.REVIEWER: ["Read", "Glob", "Grep"],
    AgentRole.GATEKEEPER: ["Read", "Glob", "Grep"],
}


def _load_prompt(role: AgentRole) -> str:
    """Load agent prompt template from prompts/ directory."""
    prompt_path = Path(__file__).parent.parent / "prompts" / f"{role.value}.md"
    if prompt_path.exists():
        return prompt_path.read_text()
    return f"You are a {role.value} agent. Complete your assigned task."


def build_agent_options(
    role: AgentRole,
    sandbox_path: str,
) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions for a specific agent role."""
    prompt = _load_prompt(role)
    tools = AGENT_TOOLS[role]

    return ClaudeAgentOptions(
        agents={
            role.value: AgentDefinition(
                description=f"SoloCarta {role.value} agent",
                prompt=prompt,
                tools=tools,
                model="sonnet",
            )
        },
        cwd=sandbox_path,
        permission_mode="bypassPermissions",
        max_turns=50,
        max_budget_usd=1.0,
    )


async def run_agent(
    role: AgentRole,
    sandbox_path: str,
    context: str,
) -> str:
    """Run an agent with the given context and return its output."""
    from claude_agent_sdk import AssistantMessage, TextBlock, query

    options = build_agent_options(role=role, sandbox_path=sandbox_path)

    output_parts: list[str] = []
    async for message in query(prompt=context, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    output_parts.append(block.text)

    return "\n".join(output_parts)
