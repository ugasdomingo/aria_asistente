import os
from contextlib import asynccontextmanager

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request

import agent

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID_FILE = ".chat_id"  # Persiste el chat_id en disco

scheduler = AsyncIOScheduler(timezone="Europe/Madrid")


# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_saved_chat_id() -> str:
    """Lee el chat_id guardado en disco o en la env."""
    env_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if env_id:
        return env_id
    if os.path.exists(CHAT_ID_FILE):
        with open(CHAT_ID_FILE) as f:
            return f.read().strip()
    return ""


def save_chat_id(chat_id: str):
    """Guarda el chat_id para los mensajes proactivos."""
    with open(CHAT_ID_FILE, "w") as f:
        f.write(chat_id)


async def send_message(chat_id: str, text: str):
    """Envía un mensaje a Telegram. Divide si supera 4096 caracteres."""
    max_len = 4096
    chunks = [text[i:i + max_len] for i in range(0, len(text), max_len)]
    async with httpx.AsyncClient() as http:
        for chunk in chunks:
            await http.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": chat_id, "text": chunk},
                timeout=30,
            )


async def daily_summary_job():
    """Tarea programada: genera y envía el resumen matutino."""
    chat_id = get_saved_chat_id()
    if not chat_id:
        print("⚠️  daily_summary: TELEGRAM_CHAT_ID no configurado. Escribe primero al bot.")
        return
    print(f"📅 Generando resumen diario para chat_id={chat_id}...")
    try:
        summary = await agent.generate_daily_summary()
        await send_message(chat_id, summary)
        print("✅ Resumen enviado.")
    except Exception as e:
        print(f"❌ Error en daily_summary: {e}")


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Registrar webhook en Telegram
    domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip().replace("\n", "").replace("\r", "")
    if domain:
        webhook_url = f"https://{domain}/webhook"
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook",
                json={"url": webhook_url},
                timeout=10,
            )
            data = resp.json()
            if data.get("ok"):
                print(f"✅ Webhook registrado: {webhook_url}")
            else:
                print(f"⚠️  Webhook error: {data}")
    else:
        print("⚠️  RAILWAY_PUBLIC_DOMAIN no configurado. Webhook no registrado automáticamente.")

    # Programar resumen diario
    # Lunes a viernes → 7:00 AM Madrid
    scheduler.add_job(daily_summary_job, "cron", day_of_week="mon-fri", hour=7, minute=0, id="summary_weekday")
    # Sábado y domingo → 10:00 AM Madrid
    scheduler.add_job(daily_summary_job, "cron", day_of_week="sat,sun", hour=10, minute=0, id="summary_weekend")
    scheduler.start()
    print("⏰ Scheduler activo — L-V 07:00 | S-D 10:00 (Madrid)")

    yield

    scheduler.shutdown()
    print("Scheduler detenido.")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="ARIA - Asistente Personal", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "ARIA"}


@app.get("/admin/drive")
async def drive_stats():
    """Muestra todos los archivos del Drive de la service account."""
    import asyncio
    from agent import google
    if not google.drive:
        return {"error": "Drive no configurado"}

    def _list():
        files = []
        page_token = None
        total_bytes = 0
        while True:
            resp = google.drive.files().list(
                pageSize=100,
                fields="nextPageToken, files(id, name, mimeType, size, createdTime)",
                pageToken=page_token,
            ).execute()
            for f in resp.get("files", []):
                size = int(f.get("size", 0))
                total_bytes += size
                files.append({
                    "id": f["id"],
                    "name": f["name"],
                    "type": f.get("mimeType", ""),
                    "size_kb": round(size / 1024, 1),
                    "created": f.get("createdTime", ""),
                })
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return {"total_files": len(files), "total_mb": round(total_bytes / 1024 / 1024, 2), "files": files}

    result = await asyncio.to_thread(_list)
    return result


@app.delete("/admin/drive/{file_id}")
async def delete_drive_file(file_id: str):
    """Elimina un archivo específico del Drive de la service account."""
    import asyncio
    from agent import google
    if not google.drive:
        return {"error": "Drive no configurado"}

    def _delete():
        google.drive.files().delete(fileId=file_id).execute()
        return {"status": "eliminado", "file_id": file_id}

    return await asyncio.to_thread(_delete)


@app.delete("/admin/drive")
async def delete_all_drive_files():
    """Elimina TODOS los archivos del Drive de la service account."""
    import asyncio
    from agent import google
    if not google.drive:
        return {"error": "Drive no configurado"}

    def _delete_all():
        deleted = []
        page_token = None
        while True:
            resp = google.drive.files().list(
                pageSize=100,
                fields="nextPageToken, files(id, name)",
                pageToken=page_token,
            ).execute()
            for f in resp.get("files", []):
                google.drive.files().delete(fileId=f["id"]).execute()
                deleted.append(f["name"])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return {"eliminados": len(deleted), "archivos": deleted}

    return await asyncio.to_thread(_delete_all)


@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
    except Exception:
        return {"ok": True}

    message = data.get("message") or data.get("edited_message")
    if not message:
        return {"ok": True}

    chat_id = str(message.get("chat", {}).get("id", ""))
    if not chat_id:
        return {"ok": True}

    # Guardar chat_id al primer contacto
    if not get_saved_chat_id():
        save_chat_id(chat_id)
        print(f"💾 chat_id guardado: {chat_id}")

    # Voz → mensaje de aviso
    if message.get("voice") or message.get("audio"):
        await send_message(
            chat_id,
            "🎤 Recibí tu nota de voz. Por ahora proceso mejor mensajes de texto. ¡Escríbeme!"
        )
        return {"ok": True}

    text = message.get("text", "").strip()
    if not text:
        return {"ok": True}

    # Comando /start
    if text == "/start":
        await send_message(
            chat_id,
            "👋 Hola Domingo, soy *ARIA* — tu asistente ejecutiva personal.\n\n"
            "Puedo ayudarte con:\n"
            "📅 Gestionar tu agenda y calendario\n"
            "✅ Tareas y obligaciones\n"
            "💰 Finanzas personales\n"
            "📈 Inversiones en acciones (Revolut)\n"
            "📄 Crear documentos\n\n"
            "¿En qué empezamos?"
        )
        return {"ok": True}

    # Procesar con el agente
    try:
        response = await agent.process_message(chat_id, text)
        await send_message(chat_id, response)
    except Exception as e:
        print(f"❌ Error procesando mensaje: {e}")
        await send_message(chat_id, "⚠️ Algo fue mal. Inténtalo en un momento.")

    return {"ok": True}
