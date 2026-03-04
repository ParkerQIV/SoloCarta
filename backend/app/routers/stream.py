import asyncio
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

router = APIRouter(prefix="/api/stream", tags=["stream"])

# In-memory event bus (simple dict of run_id -> asyncio.Queue)
_event_queues: dict[str, list[asyncio.Queue]] = {}


def publish_event(run_id: str, event_type: str, data: dict):
    """Publish an event to all listeners for a run."""
    if run_id in _event_queues:
        for queue in _event_queues[run_id]:
            queue.put_nowait({"event": event_type, "data": json.dumps(data)})


@router.get("/{run_id}")
async def stream_run(run_id: str):
    queue: asyncio.Queue = asyncio.Queue()
    _event_queues.setdefault(run_id, []).append(queue)

    async def event_generator():
        try:
            while True:
                event = await queue.get()
                yield event
                if event.get("event") == "pipeline_complete":
                    break
        finally:
            _event_queues[run_id].remove(queue)
            if not _event_queues[run_id]:
                del _event_queues[run_id]

    return EventSourceResponse(event_generator())
