import unittest
from datetime import date

from aria_core.campaigns import CampaignBrief, CampaignGenerator


class CampaignGeneratorTests(unittest.TestCase):
    def test_diginode_campaign_generates_seven_complete_days(self):
        brief = CampaignBrief.from_answers(
            {
                "marca": "Diginode",
                "objetivo": "generar demos",
                "producto_oferta": "agentes de IA para operaciones",
                "audiencia": "fundadores de pymes",
                "dolor_principal": "procesos manuales",
                "cta": "agenda una llamada",
                "tono": "directo y experto",
                "fecha_inicio": "2026-06-10",
                "promocion": "diagnostico gratis",
                "restricciones": "sin prometer resultados",
                "assets": "logo y web",
            },
            today=date(2026, 6, 4),
        )
        bundle = CampaignGenerator().generate(brief)

        self.assertEqual(len(bundle.daily_plans), 7)
        self.assertEqual(bundle.campaign.brand.name, "Diginode")
        self.assertTrue(bundle.campaign.campaign_id.startswith("CMP-DIGINODE-20260610-"))
        self.assertEqual(len(bundle.pieces), 35)

        for day in range(1, 8):
            pieces = [piece for piece in bundle.pieces if piece.day == day]
            formats = [piece.format for piece in pieces]
            channels = {piece.channel for piece in pieces}
            self.assertIn("instagram_carousel", formats)
            self.assertIn("linkedin_post", formats)
            self.assertEqual(formats.count("vertical_video"), 3)
            self.assertTrue({"Instagram Stories", "YouTube Shorts", "WhatsApp Stories"}.issubset(channels))

            carousel = next(piece for piece in pieces if piece.format == "instagram_carousel")
            self.assertGreaterEqual(len(carousel.image_prompts), 3)

            for video in [piece for piece in pieces if piece.format == "vertical_video"]:
                self.assertIn("8-10", video.video_script)
                self.assertIn("8-10", video.video_prompt)

    def test_silicity_campaign_applies_brand_defaults_when_answers_are_sparse(self):
        brief = CampaignBrief.from_answers(
            {
                "marca": "Silicity",
                "objetivo": "aumentar awareness",
                "fecha_inicio": "2026-06-10",
            },
            today=date(2026, 6, 4),
        )
        bundle = CampaignGenerator().generate(brief)

        self.assertEqual(bundle.campaign.brand.name, "Silicity")
        self.assertIn("Silicity", bundle.pieces[0].title)
        self.assertIn("MarcaDigital", " ".join(bundle.pieces[0].hashtags))
        self.assertIn("Empresas", bundle.daily_plans[0].central_message)


if __name__ == "__main__":
    unittest.main()
