import unittest

from aria_core.memory import StructuredMemoryStore
from aria_core.tools import ToolExecutor


class FakeGoogle:
    async def get_memoria(self):
        return []

    async def save_memoria(self, categoria, contenido):
        return "ok"


class ToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_sensitive_tools_require_confirmation(self):
        executor = ToolExecutor(FakeGoogle(), StructuredMemoryStore(FakeGoogle()))

        result = await executor.execute("delete_calendar_event", {"event_id": "abc"})

        self.assertIn("approval_required", result)


if __name__ == "__main__":
    unittest.main()
