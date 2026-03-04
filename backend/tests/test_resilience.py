import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from app.engine.resilience import run_agent_with_retry, AgentError


@pytest.mark.asyncio
async def test_retry_succeeds_on_first_try():
    mock_run = AsyncMock(return_value="spec output")
    with patch("app.engine.resilience.run_agent", mock_run):
        from app.engine.claude_runtime import AgentRole
        result = await run_agent_with_retry(AgentRole.PM, "/tmp/sandbox", "context")
    assert result == "spec output"
    assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failure():
    mock_run = AsyncMock(side_effect=[TimeoutError("timeout"), "spec output"])
    with patch("app.engine.resilience.run_agent", mock_run):
        from app.engine.claude_runtime import AgentRole
        result = await run_agent_with_retry(
            AgentRole.PM, "/tmp/sandbox", "context", max_retries=2, base_delay=0.01
        )
    assert result == "spec output"
    assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_retry_exhausted_raises_agent_error():
    mock_run = AsyncMock(side_effect=TimeoutError("timeout"))
    with patch("app.engine.resilience.run_agent", mock_run):
        from app.engine.claude_runtime import AgentRole
        with pytest.raises(AgentError) as exc_info:
            await run_agent_with_retry(
                AgentRole.PM, "/tmp/sandbox", "context", max_retries=2, base_delay=0.01
            )
    assert "pm" in str(exc_info.value)
    assert mock_run.call_count == 2


@pytest.mark.asyncio
async def test_timeout_triggers_retry():
    async def slow_agent(*args, **kwargs):
        await asyncio.sleep(10)
        return "never"

    with patch("app.engine.resilience.run_agent", side_effect=slow_agent):
        from app.engine.claude_runtime import AgentRole
        with pytest.raises(AgentError):
            await run_agent_with_retry(
                AgentRole.PM, "/tmp/sandbox", "context",
                max_retries=1, timeout_seconds=0.1, base_delay=0.01,
            )
