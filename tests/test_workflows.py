import unittest

from aria_core.workflows import memory_category_for_text, select_workflow


class WorkflowTests(unittest.TestCase):
    def test_agenda_is_selected_for_today_query(self):
        selection = select_workflow("Que tengo hoy y que tareas estan pendientes?")
        self.assertEqual(selection.name, "agenda")


    def test_marketing_is_selected_for_campaign_plan(self):
        selection = select_workflow("Necesito una campana de marketing para conseguir leads")
        self.assertEqual(selection.name, "marketing")


    def test_decision_is_selected_for_decision_support(self):
        selection = select_workflow("Ayudame a decidir si contrato a alguien o automatizo")
        self.assertEqual(selection.name, "decision")


    def test_memory_capture_detects_corrections(self):
        selection = select_workflow("No vuelvas a usar respuestas largas, corrigelo para siempre")
        self.assertEqual(selection.name, "memory")
        self.assertTrue(selection.needs_memory_capture)
        self.assertEqual(memory_category_for_text("No vuelvas a usar respuestas largas"), "reglas_comportamiento")


if __name__ == "__main__":
    unittest.main()
