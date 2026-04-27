import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.events import event_broker
from app.agent.runtime import AgentRuntime


class AgentRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_interrupt_cancels_running_task(self) -> None:
        runtime = AgentRuntime()
        session_id = "runtime-interrupt-test"
        await event_broker.clear(session_id)

        task = asyncio.create_task(asyncio.sleep(60))
        runtime._tasks[session_id] = task  # noqa: SLF001

        await runtime.interrupt(session_id)

        with self.assertRaises(asyncio.CancelledError):
            await task
        history = await event_broker.history(session_id)
        self.assertEqual(history[-1]["type"], "task_status")
        self.assertEqual(history[-1]["state"], "interrupted")


if __name__ == "__main__":
    unittest.main()
