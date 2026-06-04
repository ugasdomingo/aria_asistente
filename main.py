import os
from contextlib import asynccontextmanager

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import agent
from aria_core.telegram_media import TelegramMediaAdapter

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID_FILE = ".chat_id"

scheduler = AsyncIOScheduler(timezone="Europe/Madrid")
media_adapter: TelegramMediaAdapter | None = None


def get_saved_chat_id() -> str:
    env_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if env_id:
        return env_id
    if os.path.exists(CHAT_ID_FILE):
        with open(CHAT_ID_FILE) as handle:
            return handle.read().strip()
    return ""


def save_chat_id(chat_id: str):
    with open(CHAT_ID_FILE, "w") as handle:
        handle.write(chat_id)


def get_media_adapter() -> TelegramMediaAdapter:
    global media_adapter
    if media_adapter is None:
        media_adapter = TelegramMediaAdapter(BOT_TOKEN)
    return media_adapter


async def send_message(chat_id: str, text: str):
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
    chat_id = get_saved_chat_id()
    if not chat_id:
        print("daily_summary: TELEGRAM_CHAT_ID no configurado. Escribe primero al bot.")
        return
    print(f"Generando resumen diario para chat_id={chat_id}...")
    try:
        summary = await agent.generate_daily_summary()
        await send_message(chat_id, summary)
        print("Resumen enviado.")
    except Exception as exc:
        print(f"Error en daily_summary: {exc}")


@asynccontextmanager
async def lifespan(app: FastAPI):
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
                print(f"Webhook registrado: {webhook_url}")
            else:
                print(f"Webhook error: {data}")
    else:
        print("RAILWAY_PUBLIC_DOMAIN no configurado. Webhook no registrado automaticamente.")

    scheduler.add_job(daily_summary_job, "cron", day_of_week="mon-fri", hour=7, minute=0, id="summary_weekday")
    scheduler.add_job(daily_summary_job, "cron", day_of_week="sat,sun", hour=10, minute=0, id="summary_weekend")
    scheduler.start()
    print("Scheduler activo: L-V 07:00 | S-D 10:00 Madrid")

    yield

    scheduler.shutdown()
    print("Scheduler detenido.")


app = FastAPI(title="ARIA - Asistente Personal", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "ARIA"}


@app.get("/auth/google")
async def auth_google():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    redirect_uri = "https://ariaasistente-production.up.railway.app/auth/callback"
    scope = "https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/documents"
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return RedirectResponse(url)


@app.get("/auth/callback")
async def auth_callback(code: str = "", error: str = ""):
    if error:
        return HTMLResponse(f"<h2>Error: {error}</h2>")
    if not code:
        return HTMLResponse("<h2>No se recibio codigo de autorizacion.</h2>")

    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    redirect_uri = "https://ariaasistente-production.up.railway.app/auth/callback"

    async with httpx.AsyncClient() as http:
        resp = await http.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
    tokens = resp.json()
    refresh_token = tokens.get("refresh_token", "")

    if not refresh_token:
        return HTMLResponse(
            "<h2>No se obtuvo refresh_token.</h2>"
            "<p>Asegurate de haber anadido access_type=offline y prompt=consent.</p>"
            f"<pre>{tokens}</pre>"
        )

    return HTMLResponse(
        f"""
        <h1>Autorizacion completada</h1>
        <p>Copia el token completo y anadelo en Railway como <code>GOOGLE_USER_REFRESH_TOKEN</code>:</p>
        <textarea id="token" rows="4" style="width:100%;font-size:13px;padding:12px;word-break:break-all"
            onclick="this.select()">{refresh_token}</textarea>
        <br><br>
        <button onclick="navigator.clipboard.writeText(document.getElementById('token').value);this.innerText='Copiado!'"
            style="padding:12px 24px;font-size:16px;cursor:pointer">
            Copiar token
        </button>
        <p>Token length: <strong>{len(refresh_token)} caracteres</strong></p>
        <p>Despues de anadirlo en Railway, ARIA usara tu Drive para la carpeta Aria.</p>
        """
    )


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

    if not get_saved_chat_id():
        save_chat_id(chat_id)
        print(f"chat_id guardado: {chat_id}")

    text = message.get("text", "").strip()
    caption = message.get("caption", "").strip()
    media_context = None

    if any(message.get(key) for key in ("photo", "voice", "audio", "video", "video_note", "document")):
        media_context = await get_media_adapter().build_context(message)

    if not text and caption:
        text = caption

    if not text and media_context and media_context.has_content:
        text = "Analiza el adjunto que te he enviado y dime que puedes hacer con el."

    if not text:
        return {"ok": True}

    if text == "/start":
        await send_message(
            chat_id,
            "Hola Domingo, soy ARIA, tu asistente ejecutiva personal.\n\n"
            "Puedo ayudarte con:\n"
            "- Gestionar tu agenda y calendario\n"
            "- Tareas y obligaciones\n"
            "- Finanzas personales\n"
            "- Inversiones en acciones\n"
            "- Crear, leer y organizar documentos\n"
            "- Analizar imagenes, audios y videos\n"
            "- Activar habilidades como /skill marketing\n\n"
            "En que empezamos?",
        )
        return {"ok": True}

    try:
        response = await agent.process_message(chat_id, text, media_context=media_context)
        await send_message(chat_id, response)
    except Exception as exc:
        print(f"Error procesando mensaje: {exc}")
        await send_message(chat_id, "Algo fue mal. Intentalo en un momento.")

    return {"ok": True}
