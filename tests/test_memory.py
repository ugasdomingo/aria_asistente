import unittest

from aria_core.memory import StructuredMemoryStore


class FakeBackend:
    def __init__(self):
        self.rows = []

    async def get_memoria(self):
        return list(self.rows)

    async def save_memoria(self, categoria, contenido):
        for row in self.rows:
            if row["Categoria"].lower() == categoria.lower():
                row["Contenido"] = contenido
                return "updated"
        self.rows.append({"Categoria": categoria, "Contenido": contenido})
        return "created"


class MemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_correction_is_versioned_and_searchable(self):
        store = StructuredMemoryStore(FakeBackend())

        first = await store.capture_user_correction("No vuelvas a responder con rodeos.", "reglas_comportamiento")
        second = await store.upsert("reglas_comportamiento", "Domingo quiere respuestas directas.", "test", 0.9)
        results = await store.search("respuestas directas")

        self.assertEqual(first.id, second.id)
        self.assertEqual(second.version, 2)
        self.assertEqual(results[0].content, "Domingo quiere respuestas directas.")

    async def test_delete_marks_memory_inactive(self):
        store = StructuredMemoryStore(FakeBackend())
        record = await store.upsert("preferencias_comunicacion", "Usar tono directo.", "test", 0.9)

        await store.delete(record.id, "test cleanup")

        self.assertEqual(await store.search("tono directo"), [])


if __name__ == "__main__":
    unittest.main()
