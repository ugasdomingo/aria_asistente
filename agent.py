import json
import os
from datetime import datetime

import pytz
from anthropic import Anthropic
from dotenv import load_dotenv

from google_apis import GoogleAPIs

load_dotenv()

MADRID_TZ = pytz.timezone("Europe/Madrid")
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
google = GoogleAPIs()

SYSTEM_PROMPT = """Eres ARIA, asistente personal ejecutiva, asesora de finanzas personales y asesora de inversión en acciones de Domingo. Hablas siempre en español. Tienes carácter de profesional senior: directa, empática, organizada y sin rodeos.

━━━ TRIPLE ROL ━━━

1. ASISTENTE EJECUTIVA PERSONAL (máxima prioridad)
• La agenda de Domingo es sagrada — la organizas, proteges y optimizas.
• Gestionas tareas, recordatorios y obligaciones con seguimiento real.
• Creas documentos cuando hace falta: informes, actas, presupuestos, propuestas.
• Eres proactiva: alertas de conflictos en la agenda, tareas vencidas, reuniones próximas.
• Cuando te piden "¿qué tengo hoy/esta semana?", siempre consultas calendario Y tareas pendientes.

2. ASESORA DE FINANZAS PERSONALES
• Conoces los ingresos, gastos fijos, deudas y ahorros de Domingo.
• Alertas ANTES de que venzan pagos o deudas importantes.
• Analizas balance ingresos/gastos y detectas patrones de gasto.
• Recomiendas ajustes de presupuesto de forma práctica y realista.
• Hablas claro: sin jerga financiera innecesaria.

3. ASESORA DE INVERSIÓN EN ACCIONES (vía Revolut)
• Asesoras sobre acciones, ETFs, dividendos y estrategias de inversión.
• Siempre consultas el precio real antes de opinar sobre una acción.
• Usas criterios concretos: horizonte temporal, diversificación, precio de entrada/salida, stop loss.
• Recuerdas posiciones e historial que Domingo te comparte.
• SIEMPRE aclaras que tu consejo es orientativo, no asesoramiento financiero regulado.

━━━ NORMAS DE OPERACIÓN ━━━
• Usa herramientas cuando necesites datos reales. Nunca inventes información.
• Si el usuario menciona una acción o ticker, consulta el precio antes de responder.
• Respuestas concisas para Telegram: claras, bien estructuradas, sin florituras.
• Usa emojis con moderación para mejorar la legibilidad.
• Si detectas algo urgente (deuda próxima, conflicto de agenda), menciónalo aunque no te lo pidan.
"""

TOOLS = [
    {
        "name": "get_calendar_events",
        "description": "Obtiene los eventos del Google Calendar de Domingo. Úsalo siempre que pregunten por agenda, horario, reuniones o disponibilidad.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Días hacia adelante a consultar. Por defecto 7. Para 'hoy' usa 1.",
                }
            },
        },
    },
    {
        "name": "create_calendar_event",
        "description": "Crea un evento en el Google Calendar de Domingo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título del evento"},
                "fecha_inicio": {
                    "type": "string",
                    "description": "ISO 8601 con hora. Ejemplo: 2026-04-21T10:00:00",
                },
                "fecha_fin": {
                    "type": "string",
                    "description": "ISO 8601 con hora. Ejemplo: 2026-04-21T11:00:00",
                },
                "descripcion": {"type": "string", "description": "Descripción (opcional)"},
                "ubicacion": {"type": "string", "description": "Lugar (opcional)"},
            },
            "required": ["titulo", "fecha_inicio", "fecha_fin"],
        },
    },
    {
        "name": "get_finances",
        "description": "Lee los datos financieros de Domingo: ingresos, gastos fijos, deudas. Úsalo para asesoría financiera o cuando pregunten por dinero disponible.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_tasks",
        "description": "Lee las tareas y obligaciones pendientes de Domingo.",
        "input_schema": {
            "type": "object",
            "properties": {
                "solo_pendientes": {
                    "type": "boolean",
                    "description": "Si es true, devuelve solo las tareas no completadas. Por defecto true.",
                }
            },
        },
    },
    {
        "name": "create_task",
        "description": "Añade una nueva tarea, obligación o recordatorio.",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre de la tarea"},
                "fecha_limite": {
                    "type": "string",
                    "description": "Fecha límite en formato DD/MM/YYYY",
                },
                "tipo": {
                    "type": "string",
                    "description": "tarea | deuda | obligacion | recordatorio",
                },
                "monto": {
                    "type": "string",
                    "description": "Monto en euros si aplica (ej: '150€')",
                },
                "prioridad": {
                    "type": "string",
                    "description": "alta | media | baja",
                },
                "notas": {"type": "string", "description": "Notas adicionales (opcional)"},
            },
            "required": ["nombre", "prioridad"],
        },
    },
    {
        "name": "update_task_status",
        "description": "Actualiza el estado de una tarea existente (Pendiente, En progreso, Completado).",
        "input_schema": {
            "type": "object",
            "properties": {
                "nombre": {"type": "string", "description": "Nombre exacto de la tarea"},
                "estado": {
                    "type": "string",
                    "description": "Pendiente | En progreso | Completado",
                },
            },
            "required": ["nombre", "estado"],
        },
    },
    {
        "name": "create_google_doc",
        "description": "Crea un documento en Google Docs y devuelve el enlace. Útil para informes, actas, presupuestos, propuestas, etc.",
        "input_schema": {
            "type": "object",
            "properties": {
                "titulo": {"type": "string", "description": "Título del documento"},
                "contenido": {
                    "type": "string",
                    "description": "Contenido completo del documento en texto plano. Usa saltos de línea para estructurar.",
                },
            },
            "required": ["titulo", "contenido"],
        },
    },
    {
        "name": "get_stock_price",
        "description": "Obtiene el precio actual y datos clave de una acción o ETF. Úsalo SIEMPRE que el usuario mencione un ticker o pregunte por una empresa cotizada.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Símbolo bursátil. Ejemplos: AAPL, MSFT, NVDA, SPY, AMZN",
                }
            },
            "required": ["ticker"],
        },
    },
]


async def _execute_tool(tool_name: str, tool_input: dict) -> str:
    """Ejecuta la herramienta solicitada por Claude y devuelve el resultado como string."""
    try:
        if tool_name == "get_calendar_events":
            days = tool_input.get("days", 7)
            events = await google.get_calendar_events(days)
            if not events:
                return "No hay eventos en los próximos días."
            return json.dumps(events, ensure_ascii=False, indent=2)

        elif tool_name == "create_calendar_event":
            result = await google.create_calendar_event(
                titulo=tool_input["titulo"],
                fecha_inicio=tool_input["fecha_inicio"],
                fecha_fin=tool_input["fecha_fin"],
                descripcion=tool_input.get("descripcion", ""),
                ubicacion=tool_input.get("ubicacion", ""),
            )
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "get_finances":
            data = await google.get_finanzas()
            if not data:
                return "No hay datos financieros registrados aún."
            return json.dumps(data, ensure_ascii=False, indent=2)

        elif tool_name == "get_tasks":
            solo_pendientes = tool_input.get("solo_pendientes", True)
            data = await google.get_tareas(solo_pendientes)
            if not data:
                return "No hay tareas registradas." if not solo_pendientes else "No hay tareas pendientes."
            return json.dumps(data, ensure_ascii=False, indent=2)

        elif tool_name == "create_task":
            fecha = datetime.now(MADRID_TZ).strftime("%d/%m/%Y")
            fields = {
                "Tarea": tool_input.get("nombre", ""),
                "Fecha Limite": tool_input.get("fecha_limite", ""),
                "Tipo": tool_input.get("tipo", "tarea"),
                "Monto": tool_input.get("monto", ""),
                "Prioridad": tool_input.get("prioridad", "media"),
                "Notas": tool_input.get("notas", ""),
                "Estado": "Pendiente",
                "Creado": fecha,
            }
            await google.create_tarea(fields)
            return f"Tarea '{tool_input['nombre']}' añadida correctamente."

        elif tool_name == "update_task_status":
            result = await google.update_tarea_estado(
                tool_input["nombre"], tool_input["estado"]
            )
            return result

        elif tool_name == "create_google_doc":
            result = await google.create_doc(
                titulo=tool_input["titulo"],
                contenido=tool_input["contenido"],
            )
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "get_stock_price":
            result = await google.get_stock_price(tool_input["ticker"])
            return json.dumps(result, ensure_ascii=False)

        else:
            return f"Herramienta desconocida: {tool_name}"

    except Exception as e:
        return f"Error en {tool_name}: {str(e)}"


async def process_message(chat_id: str, user_message: str) -> str:
    """Bucle agente: Claude razona y llama herramientas hasta dar respuesta final."""

    # Guardar mensaje del usuario en el historial
    await google.save_to_history(chat_id, "usuario", user_message)

    # Cargar historial reciente como contexto
    history_items = await google.get_historial(chat_id, limit=20)
    history_context = ""
    if history_items:
        lines = [f"{item['rol']}: {item['mensaje']}" for item in history_items]
        history_context = "\nHISTORIAL RECIENTE:\n" + "\n".join(lines)

    now_madrid = datetime.now(MADRID_TZ).strftime("%A %d/%m/%Y %H:%M")
    system = SYSTEM_PROMPT + f"\nFECHA Y HORA ACTUAL (Madrid): {now_madrid}" + history_context

    messages = [{"role": "user", "content": user_message}]

    # Bucle agente con máximo 10 iteraciones
    for _ in range(10):
        response = client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-opus-4-5"),
            max_tokens=4096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            final_text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            await google.save_to_history(chat_id, "aria", final_text)
            return final_text

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = await _execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": tool_results})

        else:
            break

    return "Algo fue mal procesando tu mensaje. Inténtalo de nuevo."


async def generate_daily_summary() -> str:
    """Genera el resumen matutino consultando agenda, tareas y finanzas."""
    now = datetime.now(MADRID_TZ)
    dias = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
    day_name = dias[now.weekday()]
    date_str = now.strftime("%d/%m/%Y")

    prompt = (
        f"Hoy es {day_name} {date_str}. Genera el resumen matutino de Domingo. "
        "Revisa: 1) agenda de hoy y los próximos 3 días, 2) tareas pendientes urgentes o próximas a vencer, "
        "3) pagos o deudas que vencen pronto. "
        "Sé directa y práctica. Termina con una frase motivadora breve. "
        "Formato: secciones claras con emojis de título."
    )
    return await process_message("daily_summary", prompt)
