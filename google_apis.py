import asyncio
import json
import os
from datetime import datetime, timedelta

import httpx
import pytz
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

MADRID_TZ = pytz.timezone("Europe/Madrid")
AIRTABLE_BASE_URL = "https://api.airtable.com/v0"


class GoogleAPIs:
    def __init__(self):
        self.calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        self.calendar = None
        self.docs = None
        self.drive = None

        # Airtable
        self.airtable_key = os.getenv("AIRTABLE_API_KEY", "").strip()
        self.airtable_base_id = os.getenv("AIRTABLE_BASE_ID", "appg3sqgom3NIQuYy").strip()
        self.tbl_historial = "tblWQvasKiFr7OQAz"
        self.tbl_finanzas = "tblBaDPD27Lid39NN"
        self.tbl_tareas = "tblCuQNQ1whoWscNt"

        if self.airtable_key:
            print("✅ Airtable configurado correctamente.")
        else:
            print("⚠️  AIRTABLE_API_KEY vacío — Airtable desactivado.")

        # Google credentials (Calendar + Docs solamente)
        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
        if not creds_json:
            print("⚠️  GOOGLE_CREDENTIALS_JSON vacío — Google Calendar/Docs desactivados.")
            return

        try:
            creds_dict = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
            self.calendar = build("calendar", "v3", credentials=credentials)
            self.docs = build("docs", "v1", credentials=credentials)
            self.drive = build("drive", "v3", credentials=credentials)
            print("✅ Google Calendar/Docs conectados correctamente.")
        except json.JSONDecodeError as e:
            print(f"❌ GOOGLE_CREDENTIALS_JSON no es JSON válido: {e}")
        except Exception as e:
            print(f"❌ Error conectando Google APIs: {e}")

    # ─── Airtable helpers ────────────────────────────────────────────────────

    def _at_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.airtable_key}",
            "Content-Type": "application/json",
        }

    def _at_url(self, table_id: str, record_id: str = "") -> str:
        url = f"{AIRTABLE_BASE_URL}/{self.airtable_base_id}/{table_id}"
        if record_id:
            url += f"/{record_id}"
        return url

    # ─── Historial ───────────────────────────────────────────────────────────

    def _save_to_history(self, chat_id: str, rol: str, mensaje: str):
        if not self.airtable_key:
            print("⚠️  Airtable: AIRTABLE_API_KEY no configurado, no se guarda historial.")
            return
        fecha = datetime.now(MADRID_TZ).strftime("%d/%m/%Y %H:%M")
        resp = httpx.post(
            self._at_url(self.tbl_historial),
            headers=self._at_headers(),
            json={"fields": {"Fecha": fecha, "ChatID": chat_id, "Rol": rol, "Mensaje": mensaje}},
            timeout=10,
        )
        if resp.status_code not in (200, 201):
            print(f"❌ Airtable historial error {resp.status_code}: {resp.text[:300]}")

    async def save_to_history(self, chat_id: str, rol: str, mensaje: str):
        await asyncio.to_thread(self._save_to_history, chat_id, rol, mensaje)

    def _get_historial(self, chat_id: str, limit: int = 20) -> list:
        if not self.airtable_key:
            return []
        resp = httpx.get(
            self._at_url(self.tbl_historial),
            headers=self._at_headers(),
            params={
                "maxRecords": limit,
                "filterByFormula": f"{{ChatID}}='{chat_id}'",
                "sort[0][field]": "Fecha",
                "sort[0][direction]": "asc",
            },
            timeout=10,
        )
        records = resp.json().get("records", [])
        return [
            {"rol": r["fields"].get("Rol", ""), "mensaje": r["fields"].get("Mensaje", "")}
            for r in records
        ]

    async def get_historial(self, chat_id: str, limit: int = 20) -> list:
        return await asyncio.to_thread(self._get_historial, chat_id, limit)

    # ─── Finanzas ────────────────────────────────────────────────────────────

    def _get_finanzas(self) -> list:
        if not self.airtable_key:
            return []
        resp = httpx.get(
            self._at_url(self.tbl_finanzas),
            headers=self._at_headers(),
            params={"maxRecords": 100},
            timeout=10,
        )
        return [r["fields"] for r in resp.json().get("records", [])]

    async def get_finanzas(self) -> list:
        return await asyncio.to_thread(self._get_finanzas)

    # ─── Tareas ──────────────────────────────────────────────────────────────

    def _get_tareas(self, solo_pendientes: bool = True) -> list:
        if not self.airtable_key:
            return []
        params: dict = {"maxRecords": 200}
        if solo_pendientes:
            params["filterByFormula"] = "NOT({Estado}='Completado')"
        resp = httpx.get(
            self._at_url(self.tbl_tareas),
            headers=self._at_headers(),
            params=params,
            timeout=10,
        )
        return [r["fields"] for r in resp.json().get("records", [])]

    async def get_tareas(self, solo_pendientes: bool = True) -> list:
        return await asyncio.to_thread(self._get_tareas, solo_pendientes)

    def _create_tarea(self, fields: dict):
        if not self.airtable_key:
            return
        httpx.post(
            self._at_url(self.tbl_tareas),
            headers=self._at_headers(),
            json={"fields": fields},
            timeout=10,
        )

    async def create_tarea(self, fields: dict):
        await asyncio.to_thread(self._create_tarea, fields)

    def _update_tarea_estado(self, task_name: str, new_status: str) -> str:
        if not self.airtable_key:
            return "Airtable no configurado"
        # Buscar la tarea (lista completa y filtra en Python para evitar problemas con comillas)
        resp = httpx.get(
            self._at_url(self.tbl_tareas),
            headers=self._at_headers(),
            params={"maxRecords": 200},
            timeout=10,
        )
        records = resp.json().get("records", [])
        match = next(
            (r for r in records if r["fields"].get("Tarea", "").strip().lower() == task_name.strip().lower()),
            None,
        )
        if not match:
            return f"No se encontró la tarea '{task_name}'"
        httpx.patch(
            self._at_url(self.tbl_tareas, match["id"]),
            headers=self._at_headers(),
            json={"fields": {"Estado": new_status}},
            timeout=10,
        )
        return f"Tarea '{task_name}' actualizada a '{new_status}'"

    async def update_tarea_estado(self, task_name: str, new_status: str) -> str:
        return await asyncio.to_thread(self._update_tarea_estado, task_name, new_status)

    # ─── Calendar ────────────────────────────────────────────────────────────

    def _get_calendar_events(self, days: int = 7) -> list:
        if not self.calendar:
            return []
        now = datetime.utcnow()
        end = now + timedelta(days=days)
        result = self.calendar.events().list(
            calendarId=self.calendar_id,
            timeMin=now.isoformat() + "Z",
            timeMax=end.isoformat() + "Z",
            maxResults=25,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = []
        for e in result.get("items", []):
            start = e.get("start", {})
            events.append({
                "titulo": e.get("summary", "Sin título"),
                "inicio": start.get("dateTime", start.get("date", "")),
                "descripcion": e.get("description", ""),
                "ubicacion": e.get("location", ""),
            })
        return events

    async def get_calendar_events(self, days: int = 7) -> list:
        return await asyncio.to_thread(self._get_calendar_events, days)

    def _create_calendar_event(
        self, titulo: str, fecha_inicio: str, fecha_fin: str,
        descripcion: str = "", ubicacion: str = ""
    ) -> dict:
        if not self.calendar:
            return {"error": "Calendar no configurado"}
        event = {
            "summary": titulo,
            "description": descripcion,
            "location": ubicacion,
            "start": {"dateTime": fecha_inicio, "timeZone": "Europe/Madrid"},
            "end": {"dateTime": fecha_fin, "timeZone": "Europe/Madrid"},
        }
        result = self.calendar.events().insert(
            calendarId=self.calendar_id, body=event
        ).execute()
        return {
            "status": "creado",
            "titulo": titulo,
            "link": result.get("htmlLink", ""),
            "id": result.get("id", ""),
        }

    async def create_calendar_event(self, **kwargs) -> dict:
        return await asyncio.to_thread(self._create_calendar_event, **kwargs)

    # ─── Docs ────────────────────────────────────────────────────────────────

    def _create_doc(self, titulo: str, contenido: str) -> dict:
        if not self.docs:
            return {"error": "Docs no configurado"}
        doc = self.docs.documents().create(body={"title": titulo}).execute()
        doc_id = doc.get("documentId")
        requests = [{"insertText": {"location": {"index": 1}, "text": contenido}}]
        self.docs.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()
        owner_email = os.getenv("GOOGLE_OWNER_EMAIL", "").strip()
        if owner_email:
            self.drive.permissions().create(
                fileId=doc_id,
                body={"type": "user", "role": "writer", "emailAddress": owner_email},
                sendNotificationEmail=False,
            ).execute()
        return {
            "status": "creado",
            "titulo": titulo,
            "documentId": doc_id,
            "link": f"https://docs.google.com/document/d/{doc_id}/edit",
        }

    async def create_doc(self, titulo: str, contenido: str) -> dict:
        return await asyncio.to_thread(self._create_doc, titulo, contenido)

    # ─── Stocks ──────────────────────────────────────────────────────────────

    def _get_stock_price(self, ticker: str) -> dict:
        try:
            import yfinance as yf
            stock = yf.Ticker(ticker.upper())
            info = stock.info
            hist = stock.history(period="2d")
            if hist.empty:
                return {"error": f"No se encontraron datos para {ticker}"}
            current = round(float(hist["Close"].iloc[-1]), 2)
            prev = round(float(hist["Close"].iloc[-2]), 2) if len(hist) > 1 else current
            change_pct = round(((current - prev) / prev) * 100, 2)
            return {
                "ticker": ticker.upper(),
                "nombre": info.get("longName", ticker),
                "precio": current,
                "moneda": info.get("currency", "USD"),
                "cambio_hoy_%": change_pct,
                "52w_min": info.get("fiftyTwoWeekLow", "N/A"),
                "52w_max": info.get("fiftyTwoWeekHigh", "N/A"),
                "per": info.get("trailingPE", "N/A"),
                "sector": info.get("sector", "N/A"),
                "descripcion": info.get("longBusinessSummary", "")[:200],
            }
        except Exception as e:
            return {"error": f"Error obteniendo {ticker}: {str(e)}"}

    async def get_stock_price(self, ticker: str) -> dict:
        return await asyncio.to_thread(self._get_stock_price, ticker)
