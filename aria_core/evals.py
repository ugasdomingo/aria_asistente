from __future__ import annotations

from .tools import SENSITIVE_TOOLS, tool_schemas
from .workflows import select_workflow


def run_static_evals() -> list[dict]:
    tool_names = {item["function"]["name"] for item in tool_schemas()}
    cases = [
        {
            "name": "agenda_consulta_hoy",
            "passed": select_workflow("Que tengo hoy en la agenda?").name == "agenda",
        },
        {
            "name": "marketing_plan",
            "passed": select_workflow("Necesito un plan de marketing para captar leads").name == "marketing",
        },
        {
            "name": "decision_support",
            "passed": select_workflow("Ayudame a decidir entre dos opciones").name == "decision",
        },
        {
            "name": "memory_tools_present",
            "passed": {"memory_search", "memory_upsert", "memory_replace", "memory_delete"}.issubset(tool_names),
        },
        {
            "name": "sensitive_tools_guarded",
            "passed": {"delete_calendar_event", "create_google_doc", "memory_replace", "memory_delete"}.issubset(SENSITIVE_TOOLS),
        },
    ]
    return cases

