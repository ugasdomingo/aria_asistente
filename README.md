# ARIA — Asistente Personal IA

Asistente ejecutiva personal, asesora financiera y de inversiones para Domingo.
Stack: Python · FastAPI · Claude (Anthropic) · Google APIs · Telegram · Railway

---

## Arquitectura

```
Telegram (móvil)
    ↓
Railway (este servidor)
    ↓ bucle agente real
Claude API con herramientas:
    ├── get_calendar_events / create_calendar_event  → Google Calendar
    ├── get_finances / get_tasks / create_task        → Google Sheets
    ├── create_google_doc                             → Google Docs
    └── get_stock_price                               → Yahoo Finance
    ↓
Respuesta → Telegram
```

---

## Setup

### 1. Variables de entorno (Railway Dashboard → Variables)

| Variable | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram |
| `ANTHROPIC_API_KEY` | API Key de console.anthropic.com |
| `GOOGLE_CREDENTIALS_JSON` | JSON completo de la Service Account (una sola línea) |
| `GOOGLE_SHEET_ID` | ID de la hoja de Google Sheets |
| `GOOGLE_CALENDAR_ID` | `primary` o el ID del calendario específico |
| `RAILWAY_PUBLIC_DOMAIN` | Se inyecta automáticamente en Railway |

### 2. Google Service Account

1. [Google Cloud Console](https://console.cloud.google.com) → Proyecto nuevo "ARIA Assistant"
2. Activa: **Calendar API**, **Sheets API**, **Docs API**, **Drive API**
3. IAM → Service Accounts → Crear → descarga la clave JSON
4. Pega el JSON completo (en una línea) en `GOOGLE_CREDENTIALS_JSON`
5. **Comparte** el Google Sheet y el Calendario con el email de la service account como **Editor**

### 3. Estructura del Google Sheet

**Pestaña Finanzas** — fila 1:
`Concepto | Tipo | Monto | Fecha Vencimiento | Frecuencia | Estado | Notas | Actualizado`

**Pestaña Tareas** — fila 1:
`Tarea | Fecha Limite | Tipo | Monto | Prioridad | Notas | Estado | Creado`

**Pestaña Historial** — fila 1:
`Fecha | ChatID | Rol | Mensaje`

---

## Resumen diario automático

- **Lunes a Viernes** → 07:00 AM (hora Madrid)
- **Sábado y Domingo** → 10:00 AM (hora Madrid)

---

## Herramientas de ARIA

| Herramienta | Qué hace |
|---|---|
| `get_calendar_events` | Lee el Google Calendar |
| `create_calendar_event` | Crea eventos |
| `get_finances` | Lee datos financieros |
| `get_tasks` | Lee tareas pendientes |
| `create_task` | Añade tarea a Sheets |
| `update_task_status` | Marca tarea como completada |
| `create_google_doc` | Crea documento en Google Docs |
| `get_stock_price` | Precio y datos de acciones/ETFs |
