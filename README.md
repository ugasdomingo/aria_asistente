# ARIA 2 - Asistente personal fiable

ARIA es una asistente ejecutiva personal para Domingo. Funciona por Telegram y
usa OpenAI, Google Calendar/Docs, Airtable y Yahoo Finance.

La version 2 separa el cerebro en modulos para que la memoria y las decisiones
no dependan solo del prompt.

## Arquitectura

```text
Telegram
  -> FastAPI webhook
  -> agent.py compatible wrapper
  -> aria_core.orchestrator.AriaOrchestrator
      -> workflow routing
      -> structured memory retrieval
      -> tool execution with approval gates
      -> OpenAI Agents SDK runtime when installed
      -> compatible Chat Completions tool loop fallback
  -> Google Calendar / Docs
  -> Airtable history, tasks, finances, memory
  -> Telegram response
```

## Modulos principales

- `aria_core/orchestrator.py`: capa interna `process_message(chat_id, text)`.
- `aria_core/memory.py`: memoria persistente estructurada, versionada y compatible con la tabla actual de Airtable.
- `aria_core/tools.py`: herramientas normalizadas y proteccion para acciones sensibles.
- `aria_core/workflows.py`: enrutado hacia agenda, marketing, negocio, decisiones, finanzas, inversiones, documentos o memoria.
- `aria_core/tracing.py`: trazas JSONL locales en `.aria_traces.jsonl`.
- `aria_core/evals.py`: evaluaciones estaticas basicas.
- `agent.py`: wrapper estable usado por `main.py`.

Por defecto, si `openai-agents` esta instalado, ARIA usa `Agent`, `Runner` y
`FunctionTool` del Agents SDK. Si necesitas desactivar ese runtime durante una
incidencia, define `ARIA_DISABLE_AGENTS_SDK=1` y usara el loop compatible de
Chat Completions.

## Memoria persistente

ARIA guarda las memorias nuevas como JSON versionado dentro del campo
`Contenido` de Airtable, manteniendo compatibilidad con los campos actuales:

- `Categoria`
- `Contenido`
- `Actualizado`

Cada correccion del usuario del tipo "no vuelvas", "recuerda", "corrige" o
"a partir de ahora" se captura antes de responder y se actualiza como memoria
persistente. Las operaciones disponibles son:

- `memory_search(query, categories)`
- `memory_upsert(category, content, source, confidence)`
- `memory_replace(memory_id, new_content, reason)`
- `memory_delete(memory_id, reason)`
- `decision_log_create(topic, options, recommendation, rationale)`

`memory_replace` y `memory_delete` requieren confirmacion explicita.

## Acciones sensibles

Estas herramientas devuelven `approval_required` si no reciben
`confirmacion_usuario=true`:

- `delete_calendar_event`
- `create_google_doc`
- `memory_replace`
- `memory_delete`

El modelo debe pedir confirmacion explicita a Domingo antes de ejecutarlas.

## Variables de entorno

- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` opcional, por defecto `gpt-4o-mini`
- `AIRTABLE_API_KEY`
- `AIRTABLE_BASE_ID`
- `GOOGLE_CREDENTIALS_JSON`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_USER_REFRESH_TOKEN` opcional para crear Docs como usuario
- `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` para OAuth de Docs
- `GOOGLE_DRIVE_FOLDER_ID` opcional
- `ARIA_TRACE_FILE` opcional, por defecto `.aria_traces.jsonl`
- `ARIA_DISABLE_AGENTS_SDK=1` opcional para forzar el fallback manual

## Verificacion local

En este entorno se verifico con el Python incluido en Codex:

```powershell
C:\Users\Usuario\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
C:\Users\Usuario\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile agent.py main.py google_apis.py aria_core\memory.py aria_core\tools.py aria_core\workflows.py aria_core\orchestrator.py aria_core\tracing.py aria_core\evals.py
```

## Despliegue

Railway sigue arrancando la app FastAPI de `main.py`. El endpoint `/webhook` y
`/health` se mantienen.
