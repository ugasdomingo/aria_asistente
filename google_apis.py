import asyncio
import json
import os
from datetime import datetime, timedelta

import pytz
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

MADRID_TZ = pytz.timezone("Europe/Madrid")


class GoogleAPIs:
    def __init__(self):
        self.sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        self.calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
        self.calendar = None
        self.sheets = None
        self.docs = None
        self.drive = None

        creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
        if not creds_json:
            print("⚠️  GOOGLE_CREDENTIALS_JSON vacío — Google APIs desactivadas.")
            return

        try:
            creds_dict = json.loads(creds_json)
            credentials = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=SCOPES
            )
            self.calendar = build("calendar", "v3", credentials=credentials)
            self.sheets = build("sheets", "v4", credentials=credentials)
            self.docs = build("docs", "v1", credentials=credentials)
            self.drive = build("drive", "v3", credentials=credentials)
            print("✅ Google APIs conectadas correctamente.")
        except json.JSONDecodeError as e:
            print(f"❌ GOOGLE_CREDENTIALS_JSON no es JSON válido: {e}")
            print("   Verifica que pegaste el contenido completo del archivo JSON en Railway.")
        except Exception as e:
            print(f"❌ Error conectando Google APIs: {e}")

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

    # ─── Sheets ──────────────────────────────────────────────────────────────

    def _get_sheet_values(self, range_name: str) -> list:
        if not self.sheets:
            return []
        result = self.sheets.spreadsheets().values().get(
            spreadsheetId=self.sheet_id, range=range_name
        ).execute()
        return result.get("values", [])

    async def get_sheet_values(self, range_name: str) -> list:
        return await asyncio.to_thread(self._get_sheet_values, range_name)

    def _append_sheet_row(self, sheet_name: str, values: list):
        if not self.sheets:
            return
        self.sheets.spreadsheets().values().append(
            spreadsheetId=self.sheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [values]},
        ).execute()

    async def append_sheet_row(self, sheet_name: str, values: list):
        await asyncio.to_thread(self._append_sheet_row, sheet_name, values)

    def _update_task_status(self, task_name: str, new_status: str) -> str:
        if not self.sheets:
            return "Sheets no configurado"
        data = self._get_sheet_values("Tareas!A:H")
        if not data or len(data) < 2:
            return "No se encontraron tareas"
        headers = data[0]
        status_col = headers.index("Estado") if "Estado" in headers else 6
        for i, row in enumerate(data[1:], start=2):
            if row and row[0].strip().lower() == task_name.strip().lower():
                cell = f"Tareas!{chr(65 + status_col)}{i}"
                self.sheets.spreadsheets().values().update(
                    spreadsheetId=self.sheet_id,
                    range=cell,
                    valueInputOption="USER_ENTERED",
                    body={"values": [[new_status]]},
                ).execute()
                return f"Tarea '{task_name}' actualizada a '{new_status}'"
        return f"No se encontró la tarea '{task_name}'"

    async def update_task_status(self, task_name: str, new_status: str) -> str:
        return await asyncio.to_thread(self._update_task_status, task_name, new_status)

    def _save_to_history(self, chat_id: str, rol: str, mensaje: str):
        fecha = datetime.now(MADRID_TZ).strftime("%d/%m/%Y %H:%M")
        self._append_sheet_row("Historial", [fecha, chat_id, rol, mensaje])

    async def save_to_history(self, chat_id: str, rol: str, mensaje: str):
        await asyncio.to_thread(self._save_to_history, chat_id, rol, mensaje)

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
        # Make it readable by anyone with the link
        self.drive.permissions().create(
            fileId=doc_id,
            body={"type": "anyone", "role": "reader"},
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
