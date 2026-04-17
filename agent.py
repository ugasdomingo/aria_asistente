import asyncio
import json
import os
from datetime import datetime

import pytz
from dotenv import load_dotenv
from openai import OpenAI

from google_apis import GoogleAPIs

load_dotenv()

MADRID_TZ = pytz.timezone("Europe/Madrid")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
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
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Obtiene los eventos del Google Calendar de Domingo. Úsalo siempre que pregunten por agenda, horario, reuniones o disponibilidad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "Días hacia adelante a consultar. Por defecto 7. Para 'hoy' usa 1.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": "Crea un evento en el Google Calendar de Domingo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título del evento"},
                    "fecha_inicio": {"type": "string", "description": "ISO 8601 con hora. Ejemplo: 2026-04-21T10:00:00"},
                    "fecha_fin": {"type": "string", "description": "ISO 8601 con hora. Ejemplo: 2026-04-21T11:00:00"},
                    "descripcion": {"type": "string", "description": "Descripción (opcional)"},
                    "ubicacion": {"type": "string", "description": "Lugar (opcional)"},
                },
                "required": ["titulo", "fecha_inicio", "fecha_fin"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_calendar_event",
            "description": "Elimina o cancela un evento del calendario de Domingo. Primero consulta get_calendar_events para obtener el ID del evento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_id": {
                        "type": "string",
                        "description": "ID del evento a eliminar (obtenido de get_calendar_events)",
                    }
                },
                "required": ["event_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_finances",
            "description": "Lee los datos financieros de Domingo: ingresos, gastos fijos, deudas. Úsalo para asesoría financiera o cuando pregunten por dinero disponible.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tasks",
            "description": "Lee las tareas y obligaciones pendientes de Domingo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "solo_pendientes": {
                        "type": "boolean",
                        "description": "Si es true, devuelve solo las tareas no completadas. Por defecto true.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Añade una nueva tarea, obligación o recordatorio.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre de la tarea"},
                    "fecha_limite": {"type": "string", "description": "Fecha límite en formato DD/MM/YYYY"},
                    "tipo": {"type": "string", "description": "tarea | deuda | obligacion | recordatorio"},
                    "monto": {"type": "string", "description": "Monto en euros si aplica (ej: '150€')"},
                    "prioridad": {"type": "string", "description": "alta | media | baja"},
                    "notas": {"type": "string", "description": "Notas adicionales (opcional)"},
                },
                "required": ["nombre", "prioridad"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task_status",
            "description": "Actualiza el estado de una tarea existente (Pendiente, En progreso, Completado).",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre": {"type": "string", "description": "Nombre exacto de la tarea"},
                    "estado": {"type": "string", "description": "Pendiente | En progreso | Completado"},
                },
                "required": ["nombre", "estado"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_google_doc",
            "description": "Crea un documento en Google Docs y devuelve el enlace. Útil para informes, actas, presupuestos, propuestas, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título del documento"},
                    "contenido": {"type": "string", "description": "Contenido completo del documento en texto plano."},
                },
                "required": ["titulo", "contenido"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Guarda o actualiza algo importante que has aprendido sobre Domingo: preferencias, datos personales, patrones de inversión, estilo de comunicación, contexto vital, etc. Úsalo cuando Domingo comparta información relevante que debas recordar en futuras conversaciones. Cada categoría es un bloque de memoria independiente.",
            "parameters": {
                "type": "object",
                "properties": {
                    "categoria": {
                        "type": "string",
                        "description": "Categoría corta de la memoria. Ejemplos: 'perfil_personal', 'preferencias_comunicacion', 'cartera_inversiones', 'situacion_financiera', 'familia', 'trabajo', 'objetivos'",
                    },
                    "contenido": {
                        "type": "string",
                        "description": "Contenido completo y detallado de lo que debes recordar sobre esta categoría. Escribe en tercera persona sobre Domingo.",
                    },
                },
                "required": ["categoria", "contenido"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stock_price",
            "description": "Obtiene el precio actual y datos clave de una acción o ETF. Úsalo SIEMPRE que el usuario mencione un ticker o pregunte por una empresa cotizada.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "Símbolo bursátil. Ejemplos: AAPL, MSFT, NVDA, SPY, AMZN"}
                },
                "required": ["ticker"],
            },
        },
    },
]


async def _execute_tool(tool_name: str, tool_input: dict) -> str:
    try:
        if tool_name == "get_calendar_events":
            events = await google.get_calendar_events(tool_input.get("days", 7))
            return json.dumps(events, ensure_ascii=False, indent=2) if events else "No hay eventos en los próximos días."

        elif tool_name == "delete_calendar_event":
            result = await google.delete_calendar_event(tool_input["event_id"])
            return json.dumps(result, ensure_ascii=False)

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
            return json.dumps(data, ensure_ascii=False, indent=2) if data else "No hay datos financieros registrados aún."

        elif tool_name == "get_tasks":
            data = await google.get_tareas(tool_input.get("solo_pendientes", True))
            if not data:
                return "No hay tareas pendientes." if tool_input.get("solo_pendientes", True) else "No hay tareas registradas."
            return json.dumps(data, ensure_ascii=False, indent=2)

        elif tool_name == "create_task":
            fecha = datetime.now(MADRID_TZ).strftime("%d/%m/%Y")
            await google.create_tarea({
                "Tarea": tool_input.get("nombre", ""),
                "Fecha Limite": tool_input.get("fecha_limite", ""),
                "Tipo": tool_input.get("tipo", "tarea"),
                "Monto": tool_input.get("monto", ""),
                "Prioridad": tool_input.get("prioridad", "media"),
                "Notas": tool_input.get("notas", ""),
                "Estado": "Pendiente",
                "Creado": fecha,
            })
            return f"Tarea '{tool_input['nombre']}' añadida correctamente."

        elif tool_name == "update_task_status":
            return await google.update_tarea_estado(tool_input["nombre"], tool_input["estado"])

        elif tool_name == "save_memory":
            return await google.save_memoria(tool_input["categoria"], tool_input["contenido"])

        elif tool_name == "create_google_doc":
            result = await google.create_doc(titulo=tool_input["titulo"], contenido=tool_input["contenido"])
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "get_stock_price":
            result = await google.get_stock_price(tool_input["ticker"])
            return json.dumps(result, ensure_ascii=False)

        else:
            return f"Herramienta desconocida: {tool_name}"

    except Exception as e:
        return f"Error en {tool_name}: {str(e)}"


async def process_message(chat_id: str, user_message: str) -> str:
    """Bucle agente: GPT-4o-mini razona y llama herramientas hasta dar respuesta final."""

    await google.save_to_history(chat_id, "usuario", user_message)

    # Cargar memoria permanente y historial reciente en paralelo
    historia_items, memoria_items = await asyncio.gather(
        google.get_historial(chat_id, limit=20),
        google.get_memoria(),
    )
    now_madrid = datetime.now(MADRID_TZ).strftime("%A %d/%m/%Y %H:%M")

    system_content = SYSTEM_PROMPT + f"\nFECHA Y HORA ACTUAL (Madrid): {now_madrid}"

    if memoria_items:
        memoria_text = "\n\n━━━ LO QUE SÉ SOBRE DOMINGO (memoria permanente) ━━━\n"
        for m in memoria_items:
            memoria_text += f"\n[{m.get('Categoria', '').upper()}]\n{m.get('Contenido', '')}\n"
        system_content += memoria_text

    messages = [{"role": "system", "content": system_content}]

    # Añadir historial previo como mensajes reales
    for item in historia_items:
        role = "assistant" if item["rol"] == "aria" else "user"
        messages.append({"role": role, "content": item["mensaje"]})

    messages.append({"role": "user", "content": user_message})

    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Bucle agente con máximo 10 iteraciones
    for _ in range(10):
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=4096,
        )

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "stop":
            final_text = msg.content or ""
            await google.save_to_history(chat_id, "aria", final_text)
            return final_text

        if finish_reason == "tool_calls" and msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]})
            for tc in msg.tool_calls:
                tool_input = json.loads(tc.function.arguments)
                result = await _execute_tool(tc.function.name, tool_input)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
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
