import unittest

from aria_core.memory import StructuredMemoryStore
from aria_core.skills import SkillRegistry


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


class FakeDrive:
    def __init__(self):
        self.created = []

    async def create_document(self, title, content):
        self.created.append({"title": title, "content": content})
        return {"link": "https://docs.example/plan"}


class FakeCampaignStore:
    def __init__(self):
        self.saved = []

    async def save_campaign_bundle(self, bundle):
        self.saved.append(bundle)
        return {"created_content": len(bundle.pieces), "errors": []}

    async def list_campaigns(self, brand=None, limit=10):
        rows = [bundle.campaign.airtable_fields() for bundle in self.saved]
        if brand:
            rows = [row for row in rows if row["Marca"].lower() == brand.lower()]
        return rows[:limit]

    async def get_campaign_status(self, brand=None):
        return await self.list_campaigns(brand=brand, limit=5)

    async def get_campaign_today(self, brand=None, today=None):
        rows = []
        for bundle in self.saved:
            if brand and bundle.campaign.brand.name.lower() != brand.lower():
                continue
            rows.extend(piece.airtable_fields() for piece in bundle.pieces[:5])
        return rows


class SkillTests(unittest.IsolatedAsyncioTestCase):
    async def test_marketing_skill_interviews_and_offers_drive_save(self):
        backend = FakeBackend()
        registry = SkillRegistry(StructuredMemoryStore(backend), FakeDrive())

        first = await registry.handle("chat1", "/skill marketing")
        self.assertIn("habilidad de plan de marketing", first)

        answers = [
            "Conseguir 100 leads cualificados",
            "Consultoria de automatizacion para pymes",
            "Fundadores de pymes de servicios",
            "Espana",
            "1000 euros",
            "30 dias",
            "LinkedIn, email y web",
            "Web, algunos casos y perfil de LinkedIn",
            "Poco tiempo y tono profesional",
            "Coste por lead",
        ]
        response = ""
        for answer in answers:
            response = await registry.handle("chat1", answer)

        self.assertIn("# Plan de marketing", response)
        self.assertIn("Quieres que lo guarde", response)

    async def test_marketing_skill_saves_after_confirmation(self):
        backend = FakeBackend()
        drive = FakeDrive()
        registry = SkillRegistry(StructuredMemoryStore(backend), drive)

        await registry.handle("chat1", "/marketing")
        for answer in [
            "Leads",
            "Servicio",
            "Clientes",
            "Madrid",
            "500",
            "2 semanas",
            "LinkedIn",
            "Web",
            "Sin ads caros",
            "Leads",
        ]:
            await registry.handle("chat1", answer)

        saved = await registry.handle("chat1", "si, guardalo")

        self.assertIn("guardado", saved)
        self.assertEqual(len(drive.created), 1)

    async def test_campaign_skill_interviews_generates_and_saves_bundle(self):
        backend = FakeBackend()
        campaign_store = FakeCampaignStore()
        registry = SkillRegistry(StructuredMemoryStore(backend), FakeDrive(), campaign_store=campaign_store)

        first = await registry.handle("chat2", "/campaign diginode")
        self.assertIn("Marca detectada: Diginode", first)
        self.assertIn("Objetivo", first)

        answers = [
            "Generar 20 llamadas de diagnostico",
            "Agentes de IA para operaciones",
            "Fundadores de pymes B2B",
            "Mucho trabajo manual",
            "Agenda una llamada",
            "Experto, claro y accionable",
            "2026-06-10",
            "Diagnostico gratis",
            "No prometer ROI garantizado",
            "Logo, web y casos",
        ]
        response = ""
        for answer in answers:
            response = await registry.handle("chat2", answer)

        self.assertIn("Campana semanal creada para Diginode", response)
        self.assertIn("35 piezas", response)
        self.assertEqual(len(campaign_store.saved), 1)
        bundle = campaign_store.saved[0]
        self.assertEqual(bundle.campaign.brand.name, "Diginode")
        self.assertEqual(len(bundle.daily_plans), 7)
        self.assertEqual(len(bundle.pieces), 35)
        self.assertTrue(all(piece.campaign_id == bundle.campaign.campaign_id for piece in bundle.pieces))

    async def test_campaign_lookup_commands_return_saved_campaigns(self):
        backend = FakeBackend()
        campaign_store = FakeCampaignStore()
        registry = SkillRegistry(StructuredMemoryStore(backend), FakeDrive(), campaign_store=campaign_store)

        await registry.handle("chat3", "/campaign silicity")
        for answer in [
            "Awareness",
            "Contenido premium",
            "Equipos de marketing",
            "Baja diferenciacion",
            "Pide una propuesta",
            "Sofisticado y practico",
            "2026-06-10",
            "Sin promocion",
            "Mantener tono premium",
            "Logo y guia visual",
        ]:
            await registry.handle("chat3", answer)

        status = await registry.handle("chat3", "/campaign silicity semana actual")
        today = await registry.handle("chat3", "/campaign today")
        listing = await registry.handle("chat3", "/campanas")

        self.assertIn("Silicity", status)
        self.assertIn("Contenido de campana para hoy", today)
        self.assertIn("Campanas", listing)


if __name__ == "__main__":
    unittest.main()
