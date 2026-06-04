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

    async def test_drive_sensitive_tools_require_confirmation(self):
        executor = ToolExecutor(FakeGoogle(), StructuredMemoryStore(FakeGoogle()))

        create_result = await executor.execute("drive_create_document", {"title": "Plan", "content": "Contenido"})
        trash_result = await executor.execute("drive_trash_document", {"document_id": "doc_1"})

        self.assertIn("approval_required", create_result)
        self.assertIn("approval_required", trash_result)

    def test_drive_tools_are_registered(self):
        from aria_core.tools import tool_schemas

        names = {item["function"]["name"] for item in tool_schemas()}

        self.assertIn("drive_list_documents", names)
        self.assertIn("drive_read_document", names)
        self.assertIn("drive_create_document", names)
        self.assertIn("drive_trash_document", names)


if __name__ == "__main__":
    unittest.main()
