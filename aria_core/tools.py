from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .drive_workspace import DriveWorkspace
from .memory import StructuredMemoryStore

MADRID_TZ = ZoneInfo("Europe/Madrid")


SENSITIVE_TOOLS = {
    "delete_calendar_event",
    "create_google_doc",
    "drive_create_document",
    "drive_trash_document",
    "memory_replace",
    "memory_delete",
}


def tool_schemas() -> list[dict]:
    return [
        _tool(
            "get_calendar_events",
            "Obtiene eventos del Google Calendar. Usalo para agenda, horario, reuniones o disponibilidad.",
            {"days": {"type": "integer", "description": "Dias hacia adelante. Para hoy usa 1."}},
        ),
        _tool(
            "create_calendar_event",
            "Crea un evento en Google Calendar.",
            {
                "titulo": {"type": "string"},
                "fecha_inicio": {"type": "string", "description": "ISO 8601, ejemplo 2026-04-21T10:00:00"},
                "fecha_fin": {"type": "string", "description": "ISO 8601, ejemplo 2026-04-21T11:00:00"},
                "descripcion": {"type": "string"},
                "ubicacion": {"type": "string"},
            },
            ["titulo", "fecha_inicio", "fecha_fin"],
        ),
        _tool(
            "delete_calendar_event",
            "Elimina un evento. Requiere confirmacion_usuario=true y un event_id consultado antes.",
            {"event_id": {"type": "string"}, "confirmacion_usuario": {"type": "boolean"}},
            ["event_id"],
        ),
        _tool("get_finances", "Lee ingresos, gastos fijos, deudas y datos financieros.", {}),
        _tool(
            "get_tasks",
            "Lee tareas y obligaciones.",
            {"solo_pendientes": {"type": "boolean", "description": "Por defecto true."}},
        ),
        _tool(
            "create_task",
            "Anade una tarea, obligacion o recordatorio.",
            {
                "nombre": {"type": "string"},
                "fecha_limite": {"type": "string", "description": "DD/MM/YYYY"},
                "tipo": {"type": "string", "description": "tarea | deuda | obligacion | recordatorio"},
                "monto": {"type": "string"},
                "prioridad": {"type": "string", "description": "alta | media | baja"},
                "notas": {"type": "string"},
            },
            ["nombre", "prioridad"],
        ),
        _tool(
            "update_task_status",
            "Actualiza el estado de una tarea existente.",
            {"nombre": {"type": "string"}, "estado": {"type": "string"}},
            ["nombre", "estado"],
        ),
        _tool(
            "create_google_doc",
            "Crea un Google Doc dentro de la carpeta Aria. Requiere confirmacion_usuario=true.",
            {"titulo": {"type": "string"}, "contenido": {"type": "string"}, "confirmacion_usuario": {"type": "boolean"}},
            ["titulo", "contenido"],
        ),
        _tool(
            "drive_list_documents",
            "Lista los Google Docs dentro de la carpeta Aria.",
            {},
        ),
        _tool(
            "drive_read_document",
            "Lee un Google Doc solo si esta dentro de la carpeta Aria.",
            {"document_id": {"type": "string"}},
            ["document_id"],
        ),
        _tool(
            "drive_create_document",
            "Crea un Google Doc dentro de la carpeta Aria. Requiere confirmacion_usuario=true.",
            {"title": {"type": "string"}, "content": {"type": "string"}, "confirmacion_usuario": {"type": "boolean"}},
            ["title", "content"],
        ),
        _tool(
            "drive_trash_document",
            "Envia a la papelera un Google Doc dentro de la carpeta Aria. Requiere confirmacion_usuario=true.",
            {"document_id": {"type": "string"}, "confirmacion_usuario": {"type": "boolean"}},
            ["document_id"],
        ),
        _tool(
            "get_stock_price",
            "Obtiene precio actual y datos clave de una accion o ETF. Usalo siempre ante tickers o empresas cotizadas.",
            {"ticker": {"type": "string"}},
            ["ticker"],
        ),
        _tool(
            "memory_search",
            "Busca memoria persistente relevante.",
            {
                "query": {"type": "string"},
                "categories": {"type": "array", "items": {"type": "string"}},
            },
            ["query"],
        ),
        _tool(
            "memory_upsert",
            "Crea o actualiza una memoria persistente por categoria.",
            {
                "category": {"type": "string"},
                "content": {"type": "string"},
                "source": {"type": "string"},
                "confidence": {"type": "number"},
            },
            ["category", "content"],
        ),
        _tool(
            "memory_replace",
            "Reemplaza una memoria por id o categoria. Requiere confirmacion_usuario=true.",
            {
                "memory_id": {"type": "string"},
                "new_content": {"type": "string"},
                "reason": {"type": "string"},
                "confirmacion_usuario": {"type": "boolean"},
            },
            ["memory_id", "new_content", "reason"],
        ),
        _tool(
            "memory_delete",
            "Marca una memoria como eliminada. Requiere confirmacion_usuario=true.",
            {"memory_id": {"type": "string"}, "reason": {"type": "string"}, "confirmacion_usuario": {"type": "boolean"}},
            ["memory_id", "reason"],
        ),
        _tool(
            "decision_log_create",
            "Registra una decision importante con opciones, recomendacion y razonamiento.",
            {
                "topic": {"type": "string"},
                "options": {"type": "array", "items": {"type": "string"}},
                "recommendation": {"type": "string"},
                "rationale": {"type": "string"},
            },
            ["topic", "options", "recommendation", "rationale"],
        ),
    ]


class ToolExecutor:
    def __init__(self, google, memory: StructuredMemoryStore):
        self.google = google
        self.memory = memory
        self.drive = DriveWorkspace(google)

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> str:
        try:
            if tool_name in SENSITIVE_TOOLS and not tool_input.get("confirmacion_usuario"):
                return json.dumps(
                    {
                        "status": "approval_required",
                        "tool": tool_name,
                        "message": "Pide confirmacion explicita a Domingo antes de ejecutar esta accion.",
                    },
                    ensure_ascii=False,
                )

            result = await self._execute(tool_name, tool_input)
            return _json(result)
        except Exception as exc:
            return _json({"status": "error", "tool": tool_name, "error": str(exc)})

    async def _execute(self, tool_name: str, tool_input: dict[str, Any]) -> Any:
        if tool_name == "get_calendar_events":
            events = await self.google.get_calendar_events(tool_input.get("days", 7))
            return {"status": "ok", "events": events}

        if tool_name == "create_calendar_event":
            return await self.google.create_calendar_event(
                titulo=tool_input["titulo"],
                fecha_inicio=tool_input["fecha_inicio"],
                fecha_fin=tool_input["fecha_fin"],
                descripcion=tool_input.get("descripcion", ""),
                ubicacion=tool_input.get("ubicacion", ""),
            )

        if tool_name == "delete_calendar_event":
            return await self.google.delete_calendar_event(tool_input["event_id"])

        if tool_name == "get_finances":
            return {"status": "ok", "finances": await self.google.get_finanzas()}

        if tool_name == "get_tasks":
            return {"status": "ok", "tasks": await self.google.get_tareas(tool_input.get("solo_pendientes", True))}

        if tool_name == "create_task":
            fecha = datetime.now(MADRID_TZ).strftime("%d/%m/%Y")
            await self.google.create_tarea(
                {
                    "Tarea": tool_input.get("nombre", ""),
                    "Fecha Limite": tool_input.get("fecha_limite", ""),
                    "Tipo": tool_input.get("tipo", "tarea"),
                    "Monto": tool_input.get("monto", ""),
                    "Prioridad": tool_input.get("prioridad", "media"),
                    "Notas": tool_input.get("notas", ""),
                    "Estado": "Pendiente",
                    "Creado": fecha,
                }
            )
            return {"status": "ok", "message": f"Tarea '{tool_input['nombre']}' anadida correctamente."}

        if tool_name == "update_task_status":
            return {"status": "ok", "message": await self.google.update_tarea_estado(tool_input["nombre"], tool_input["estado"])}

        if tool_name == "create_google_doc":
            return await self.drive.create_document(title=tool_input["titulo"], content=tool_input["contenido"])

        if tool_name == "drive_list_documents":
            return {"status": "ok", "documents": await self.drive.list_documents()}

        if tool_name == "drive_read_document":
            return await self.drive.read_document(tool_input["document_id"])

        if tool_name == "drive_create_document":
            return await self.drive.create_document(title=tool_input["title"], content=tool_input["content"])

        if tool_name == "drive_trash_document":
            return await self.drive.trash_document(tool_input["document_id"])

        if tool_name == "get_stock_price":
            return await self.google.get_stock_price(tool_input["ticker"])

        if tool_name == "memory_search":
            records = await self.memory.search(
                query=tool_input["query"],
                categories=tool_input.get("categories") or None,
            )
            return {"status": "ok", "memories": [record.__dict__ for record in records]}

        if tool_name == "memory_upsert":
            record = await self.memory.upsert(
                category=tool_input["category"],
                content=tool_input["content"],
                source=tool_input.get("source", "assistant_tool"),
                confidence=float(tool_input.get("confidence", 0.85)),
            )
            return {"status": "ok", "memory": record.__dict__}

        if tool_name == "memory_replace":
            record = await self.memory.replace(tool_input["memory_id"], tool_input["new_content"], tool_input["reason"])
            return {"status": "ok", "memory": record.__dict__}

        if tool_name == "memory_delete":
            record = await self.memory.delete(tool_input["memory_id"], tool_input["reason"])
            return {"status": "ok", "memory": record.__dict__}

        if tool_name == "decision_log_create":
            payload = {
                "topic": tool_input["topic"],
                "options": tool_input["options"],
                "recommendation": tool_input["recommendation"],
                "rationale": tool_input["rationale"],
            }
            record = await self.memory.upsert(
                category=f"decision_log:{tool_input['topic'][:40]}",
                content=json.dumps(payload, ensure_ascii=False),
                source="decision_workflow",
                confidence=0.9,
            )
            return {"status": "ok", "decision_log": record.__dict__}

        return {"status": "error", "error": f"Herramienta desconocida: {tool_name}"}


def _tool(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


def _json(data: Any) -> str:
    if isinstance(data, str):
        return data
    return json.dumps(data, ensure_ascii=False, indent=2)
