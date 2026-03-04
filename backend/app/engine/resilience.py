"""Agent execution with retry, timeout, and error handling."""

import asyncio
import logging

from app.engine.claude_runtime import run_agent, AgentRole

logger = logging.getLogger(__name__)

TRANSIENT_EXCEPTIONS = (TimeoutError, asyncio.TimeoutError, ConnectionError, OSError)


class AgentError(Exception):
    """Raised when an agent fails after all retries."""

    def __init__(self, agent_name: str, original_error: Exception):
        self.agent_name = agent_name
        self.original_error = original_error
        super().__init__(f"Agent '{agent_name}' failed: {original_error}")


async def run_agent_with_retry(
    role: AgentRole,
    sandbox_path: str,
    context: str,
    max_retries: int = 3,
    timeout_seconds: float = 300.0,
    base_delay: float = 1.0,
) -> str:
    """Run an agent with retry on transient failures and per-call timeout."""
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            result = await asyncio.wait_for(
                run_agent(role, sandbox_path, context),
                timeout=timeout_seconds,
            )
            return result
        except TRANSIENT_EXCEPTIONS as e:
            last_error = e
            logger.warning(
                "Agent %s attempt %d/%d failed: %s",
                role.value, attempt, max_retries, e,
            )
            if attempt < max_retries:
                delay = base_delay * (4 ** (attempt - 1))  # 1s, 4s, 16s
                await asyncio.sleep(delay)
        except Exception as e:
            # Non-transient error — fail immediately
            raise AgentError(role.value, e) from e

    raise AgentError(role.value, last_error)
