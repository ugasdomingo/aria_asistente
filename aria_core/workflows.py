from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class WorkflowSelection:
    name: str
    reasons: list[str]
    needs_memory_capture: bool = False


AGENDA_RE = re.compile(
    r"\b(agenda|calendario|reunion|reuniones|cita|hoy|manana|semana|disponible|disponibilidad|evento)\b",
    re.IGNORECASE,
)
TASK_RE = re.compile(r"\b(tarea|tareas|pendiente|pendientes|recordatorio|obligacion)\b", re.IGNORECASE)
MARKETING_RE = re.compile(r"\b(marketing|campana|campanas|contenido|ventas|leads|embudo|audiencia|redes)\b", re.IGNORECASE)
BUSINESS_RE = re.compile(r"\b(negocio|empresa|modelo de negocio|oferta|precio|pricing|cliente|clientes|estrategia)\b", re.IGNORECASE)
DECISION_RE = re.compile(r"\b(decidir|decision|elige|recomienda|opciones|pros|contras|tradeoff|conviene)\b", re.IGNORECASE)
FINANCE_RE = re.compile(r"\b(finanzas|dinero|gasto|gastos|ingreso|ingresos|deuda|deudas|ahorro|presupuesto)\b", re.IGNORECASE)
INVESTMENT_RE = re.compile(r"\b(accion|acciones|etf|ticker|dividendo|bolsa|invertir|inversion|revolut|nasdaq|nyse)\b", re.IGNORECASE)
DOCUMENT_RE = re.compile(r"\b(documento|doc|informe|acta|presupuesto|propuesta|google docs)\b", re.IGNORECASE)
MEMORY_RE = re.compile(
    r"\b(recuerda|memoriza|guarda|no vuelvas|nunca mas|a partir de ahora|corrige|correccion|para siempre|prefiero)\b",
    re.IGNORECASE,
)
TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")


def select_workflow(text: str) -> WorkflowSelection:
    reasons: list[str] = []
    checks = [
        ("memory", MEMORY_RE, "posible correccion o preferencia permanente"),
        ("agenda", AGENDA_RE, "agenda/calendario"),
        ("agenda", TASK_RE, "tareas u obligaciones"),
        ("marketing", MARKETING_RE, "marketing"),
        ("business", BUSINESS_RE, "negocio"),
        ("decision", DECISION_RE, "decision"),
        ("finance", FINANCE_RE, "finanzas personales"),
        ("investment", INVESTMENT_RE, "inversiones"),
        ("document", DOCUMENT_RE, "documento"),
    ]

    scores: dict[str, int] = {}
    for name, pattern, reason in checks:
        if pattern.search(text):
            scores[name] = scores.get(name, 0) + 1
            reasons.append(reason)

    if TICKER_RE.search(text) and INVESTMENT_RE.search(text):
        scores["investment"] = scores.get("investment", 0) + 1
        reasons.append("ticker o activo cotizado")

    if not scores:
        return WorkflowSelection("general", ["sin workflow especifico"])

    priority = ["memory", "agenda", "investment", "finance", "decision", "marketing", "business", "document"]
    selected = max(priority, key=lambda item: (scores.get(item, 0), -priority.index(item)))
    return WorkflowSelection(selected, reasons, needs_memory_capture=bool(MEMORY_RE.search(text)))


def memory_category_for_text(text: str) -> str:
    lowered = text.lower()
    if "no vuelvas" in lowered or "nunca mas" in lowered or "corrige" in lowered:
        return "reglas_comportamiento"
    if "prefiero" in lowered or "me gusta" in lowered or "estilo" in lowered:
        return "preferencias_comunicacion"
    if "marketing" in lowered or "negocio" in lowered or "empresa" in lowered:
        return "contexto_negocio"
    if "finanzas" in lowered or "dinero" in lowered or "deuda" in lowered:
        return "situacion_financiera"
    return "memoria_general"

