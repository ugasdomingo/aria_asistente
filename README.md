# ARIA 2 - Asistente personal fiable

ARIA es una asistente ejecutiva personal para Domingo. Funciona por Telegram y
usa OpenAI, Google Calendar/Docs/Drive, Airtable y Yahoo Finance.

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
  -> Telegram media analysis
  -> Safe Drive workspace: Aria folder
  -> Airtable history, tasks, finances, memory
  -> Telegram response
```

## Modulos principales

- `aria_core/orchestrator.py`: capa interna `process_message(chat_id, text)`.
- `aria_core/memory.py`: memoria persistente estructurada, versionada y compatible con la tabla actual de Airtable.
- `aria_core/tools.py`: herramientas normalizadas y proteccion para acciones sensibles.
- `aria_core/workflows.py`: enrutado hacia agenda, marketing, negocio, decisiones, finanzas, inversiones, documentos o memoria.
- `aria_core/telegram_media.py`: descarga temporal y clasificacion de adjuntos de Telegram.
- `aria_core/media.py`: vision, transcripcion y analisis basico de video con OpenAI.
- `aria_core/drive_workspace.py`: operaciones limitadas a la carpeta `Aria` de Google Drive.
- `aria_core/skills.py`: registro de habilidades guiadas, empezando por marketing.
- `aria_core/campaigns.py`: generador de campanas semanales para Diginode y Silicity.
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
- `drive_create_document`
- `drive_trash_document`
- `memory_replace`
- `memory_delete`

El modelo debe pedir confirmacion explicita a Domingo antes de ejecutarlas.

## Multimedia en Telegram

ARIA procesa adjuntos de forma temporal:

- Imagenes y documentos de imagen: se analizan con vision.
- Voz y audio: se transcriben.
- Videos y video notes: se intenta transcribir el audio y analizar algunos fotogramas.

Los archivos originales se borran localmente tras procesarlos. Solo se conserva
el texto util que entra al contexto de la conversacion.

## Drive seguro

ARIA opera dentro de una carpeta llamada `Aria`.

- Si `ARIA_DRIVE_FOLDER_ID` existe, usa esa carpeta.
- Si no existe, busca una carpeta llamada `Aria`.
- Si no la encuentra, la crea.

Herramientas disponibles:

- `drive_list_documents`
- `drive_read_document`
- `drive_create_document`
- `drive_trash_document`

Leer y enviar a papelera valida que el documento este dentro de la carpeta
`Aria`. El borrado permanente no esta habilitado.

## Habilidades

La primera habilidad guiada es `marketing_plan`.

Activacion:

- `/skill marketing`
- `/habilidad marketing`
- `/marketing`
- "Aria, hazme un plan de marketing"

ARIA entrevista al usuario, genera el plan y al final ofrece guardarlo como
Google Doc dentro de la carpeta `Aria`.

La habilidad `weekly_campaign` genera campanas de 7 dias para `Diginode` o
`Silicity`. No publica automaticamente: crea el calendario, copies, hashtags,
prompts de imagen, prompts de video y guiones para que Domingo produzca los
assets y publique manualmente.

Activacion:

- `/campaign diginode`
- `/campaign silicity`
- `/campana diginode`
- "Aria, creame una campana de 7 dias para Diginode"
- "Aria, haz campana para Silicity"

Consultas:

- `/campanas`
- `/campaign status`
- `/campaign today`
- `/campaign diginode semana actual`

Cada campana guarda en Airtable:

- `Marcas`: `Marca`, `Descripcion`, `Audiencia`, `Tono`, `Oferta`, `CTA Principal`, `Restricciones`
- `Campañas`: `CampaignID`, `Marca`, `Objetivo`, `Tema`, `Fecha Inicio`, `Fecha Fin`, `Estado`, `Notas`
- `Contenido Campaña`: `CampaignID`, `Dia`, `Fecha`, `Canal`, `Formato`, `Titulo`, `Copy`, `Hashtags`, `Prompt Imagen`, `Prompt Video`, `Guion Video`, `CTA`, `Estado`

Por campana se generan 35 piezas: 7 carruseles de Instagram, 21 videos
verticales adaptados a Instagram Stories, YouTube Shorts y WhatsApp Stories,
y 7 posts de LinkedIn.

## Variables de entorno

- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` opcional, por defecto `gpt-4o-mini`
- `AIRTABLE_API_KEY`
- `AIRTABLE_BASE_ID`
- `AIRTABLE_TABLE_MARCAS` opcional, por defecto `Marcas`
- `AIRTABLE_TABLE_CAMPANAS` opcional, por defecto `Campañas`
- `AIRTABLE_TABLE_CONTENIDO_CAMPANA` opcional, por defecto `Contenido Campaña`
- `GOOGLE_CREDENTIALS_JSON`
- `GOOGLE_CALENDAR_ID`
- `GOOGLE_USER_REFRESH_TOKEN` opcional para crear Docs como usuario
- `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET` para OAuth de Docs
- `ARIA_DRIVE_FOLDER_ID` opcional para fijar la carpeta Aria
- `GOOGLE_DRIVE_FOLDER_ID` fallback opcional
- `OPENAI_VISION_MODEL` opcional, por defecto `gpt-4.1-mini`
- `OPENAI_TRANSCRIBE_MODEL` opcional, por defecto `gpt-4o-mini-transcribe`
- `ARIA_MEDIA_MAX_MB` opcional, por defecto `20`
- `ARIA_VIDEO_MAX_FRAMES` opcional, por defecto `4`
- `ARIA_TRACE_FILE` opcional, por defecto `.aria_traces.jsonl`
- `ARIA_DISABLE_AGENTS_SDK=1` opcional para forzar el fallback manual

## Verificacion local

En este entorno se verifico con el Python incluido en Codex:

```powershell
C:\Users\Usuario\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest discover -s tests -v
C:\Users\Usuario\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile agent.py main.py google_apis.py aria_core\message_context.py aria_core\media.py aria_core\telegram_media.py aria_core\drive_workspace.py aria_core\skills.py aria_core\campaigns.py aria_core\memory.py aria_core\tools.py aria_core\workflows.py aria_core\orchestrator.py aria_core\tracing.py aria_core\evals.py aria_core\prompts.py
```

## Despliegue

Railway sigue arrancando la app FastAPI de `main.py`. El endpoint `/webhook` y
`/health` se mantienen.
