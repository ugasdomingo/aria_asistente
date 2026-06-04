import asyncio
import json
import os
from datetime import datetime, timedelta
from urllib.parse import quote

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
        self.tbl_memoria = "tbl78K08qNSAUKanC"
        self.tbl_marcas = os.getenv("AIRTABLE_TABLE_MARCAS", "Marcas").strip()
        self.tbl_campanas = os.getenv("AIRTABLE_TABLE_CAMPANAS", "Campañas").strip()
        self.tbl_contenido_campana = os.getenv("AIRTABLE_TABLE_CONTENIDO_CAMPANA", "Contenido Campaña").strip()

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
        table_part = quote(str(table_id), safe="")
        url = f"{AIRTABLE_BASE_URL}/{self.airtable_base_id}/{table_part}"
        if record_id:
            url += f"/{quote(str(record_id), safe='')}"
        return url

    def _at_post_record(self, table_id: str, fields: dict) -> dict:
        resp = httpx.post(
            self._at_url(table_id),
            headers=self._at_headers(),
            json={"fields": fields},
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            return {"error": f"Airtable {table_id} error {resp.status_code}: {resp.text[:300]}"}
        return resp.json()

    def _at_patch_record(self, table_id: str, record_id: str, fields: dict) -> dict:
        resp = httpx.patch(
            self._at_url(table_id, record_id),
            headers=self._at_headers(),
            json={"fields": fields},
            timeout=20,
        )
        if resp.status_code not in (200, 201):
            return {"error": f"Airtable {table_id} error {resp.status_code}: {resp.text[:300]}"}
        return resp.json()

    def _at_get_records(self, table_id: str, max_records: int = 100, params: dict | None = None) -> list:
        if not self.airtable_key:
            return []
        query = {"maxRecords": max_records}
        if params:
            query.update(params)
        resp = httpx.get(
            self._at_url(table_id),
            headers=self._at_headers(),
            params=query,
            timeout=20,
        )
        if resp.status_code != 200:
            print(f"Airtable {table_id} read error {resp.status_code}: {resp.text[:300]}")
            return []
        return resp.json().get("records", [])

    def _at_batch_create(self, table_id: str, records: list[dict]) -> dict:
        created = 0
        errors: list[str] = []
        for start in range(0, len(records), 10):
            chunk = records[start:start + 10]
            resp = httpx.post(
                self._at_url(table_id),
                headers=self._at_headers(),
                json={"records": [{"fields": fields} for fields in chunk]},
                timeout=30,
            )
            if resp.status_code not in (200, 201):
                errors.append(f"{resp.status_code}: {resp.text[:300]}")
                continue
            created += len(resp.json().get("records", []))
        return {"created": created, "errors": errors}

    def _save_campaign_bundle(self, bundle) -> dict:
        if not self.airtable_key:
            return {"error": "Airtable no configurado", "created_content": 0}
        payload = bundle.airtable_payload()
        brand_fields = payload["brand"]
        existing_brand = next(
            (
                record
                for record in self._at_get_records(self.tbl_marcas, max_records=100)
                if record.get("fields", {}).get("Marca", "").strip().lower()
                == brand_fields.get("Marca", "").strip().lower()
            ),
            None,
        )
        if existing_brand:
            brand_result = self._at_patch_record(self.tbl_marcas, existing_brand["id"], brand_fields)
        else:
            brand_result = self._at_post_record(self.tbl_marcas, brand_fields)

        campaign_result = self._at_post_record(self.tbl_campanas, payload["campaign"])
        content_result = self._at_batch_create(self.tbl_contenido_campana, payload["content"])
        errors = list(content_result["errors"])
        for result in (brand_result, campaign_result):
            if isinstance(result, dict) and result.get("error"):
                errors.append(result["error"])
        return {
            "brand": brand_result,
            "campaign": campaign_result,
            "created_content": content_result["created"],
            "errors": errors,
        }

    async def save_campaign_bundle(self, bundle) -> dict:
        return await asyncio.to_thread(self._save_campaign_bundle, bundle)

    def _list_campaigns(self, brand: str | None = None, limit: int = 10) -> list[dict]:
        records = self._at_get_records(
            self.tbl_campanas,
            max_records=100,
            params={
                "sort[0][field]": "Fecha Inicio",
                "sort[0][direction]": "desc",
            },
        )
        rows = [record.get("fields", {}) for record in records]
        if brand:
            rows = [row for row in rows if row.get("Marca", "").strip().lower() == brand.strip().lower()]
        return rows[:limit]

    async def list_campaigns(self, brand: str | None = None, limit: int = 10) -> list[dict]:
        return await asyncio.to_thread(self._list_campaigns, brand, limit)

    def _get_campaign_status(self, brand: str | None = None) -> list[dict]:
        return self._list_campaigns(brand=brand, limit=5)

    async def get_campaign_status(self, brand: str | None = None) -> list[dict]:
        return await asyncio.to_thread(self._get_campaign_status, brand)

    def _get_campaign_today(self, brand: str | None = None, today: str | None = None) -> list[dict]:
        target_date = today or datetime.now(MADRID_TZ).date().isoformat()
        campaign_ids: set[str] | None = None
        if brand:
            campaigns = self._list_campaigns(brand=brand, limit=50)
            campaign_ids = {row.get("CampaignID", "") for row in campaigns if row.get("CampaignID")}
        records = self._at_get_records(self.tbl_contenido_campana, max_records=100)
        rows = [record.get("fields", {}) for record in records]
        rows = [row for row in rows if row.get("Fecha") == target_date]
        if campaign_ids is not None:
            rows = [row for row in rows if row.get("CampaignID") in campaign_ids]
        return sorted(rows, key=lambda row: (str(row.get("CampaignID", "")), int(row.get("Dia", 0)), str(row.get("Canal", ""))))

    async def get_campaign_today(self, brand: str | None = None, today: str | None = None) -> list[dict]:
        return await asyncio.to_thread(self._get_campaign_today, brand, today)

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

    # ─── Memoria permanente ──────────────────────────────────────────────────

    def _get_memoria(self) -> list:
        if not self.airtable_key:
            return []
        resp = httpx.get(
            self._at_url(self.tbl_memoria),
            headers=self._at_headers(),
            params={"maxRecords": 100},
            timeout=10,
        )
        return [r["fields"] for r in resp.json().get("records", [])]

    async def get_memoria(self) -> list:
        return await asyncio.to_thread(self._get_memoria)

    def _save_memoria(self, categoria: str, contenido: str) -> str:
        if not self.airtable_key:
            return "Airtable no configurado"
        fecha = datetime.now(MADRID_TZ).strftime("%d/%m/%Y %H:%M")
        # Buscar si ya existe un registro con esa categoría
        resp = httpx.get(
            self._at_url(self.tbl_memoria),
            headers=self._at_headers(),
            params={"maxRecords": 100},
            timeout=10,
        )
        records = resp.json().get("records", [])
        match = next(
            (r for r in records if r["fields"].get("Categoria", "").strip().lower() == categoria.strip().lower()),
            None,
        )
        if match:
            # Actualizar registro existente
            httpx.patch(
                self._at_url(self.tbl_memoria, match["id"]),
                headers=self._at_headers(),
                json={"fields": {"Contenido": contenido, "Actualizado": fecha}},
                timeout=10,
            )
            return f"Memoria '{categoria}' actualizada."
        else:
            # Crear nuevo registro
            httpx.post(
                self._at_url(self.tbl_memoria),
                headers=self._at_headers(),
                json={"fields": {"Categoria": categoria, "Contenido": contenido, "Actualizado": fecha}},
                timeout=10,
            )
            return f"Memoria '{categoria}' guardada."

    async def save_memoria(self, categoria: str, contenido: str) -> str:
        return await asyncio.to_thread(self._save_memoria, categoria, contenido)

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
                "id": e.get("id", ""),
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

    def _delete_calendar_event(self, event_id: str) -> dict:
        if not self.calendar:
            return {"error": "Calendar no configurado"}
        try:
            self.calendar.events().delete(
                calendarId=self.calendar_id, eventId=event_id
            ).execute()
            return {"status": "eliminado", "event_id": event_id}
        except Exception as e:
            return {"error": str(e)}

    async def delete_calendar_event(self, event_id: str) -> dict:
        return await asyncio.to_thread(self._delete_calendar_event, event_id)

    # ─── Docs ────────────────────────────────────────────────────────────────

    def _get_user_drive_docs(self):
        """Crea clientes Drive y Docs autenticados como el usuario (OAuth)."""
        refresh_token = os.getenv("GOOGLE_USER_REFRESH_TOKEN", "").strip()
        client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
        if not all([refresh_token, client_id, client_secret]):
            return None, None

        # Refrescar manualmente el access token
        resp = httpx.post(
            "https://oauth2.googleapis.com/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            timeout=10,
        )
        token_data = resp.json()
        print(f"📄 OAuth refresh status={resp.status_code}: {token_data.get('error')} — {token_data.get('error_description')}")

        if "error" in token_data:
            return None, None

        access_token = token_data["access_token"]
        from google.oauth2.credentials import Credentials
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=[
                "https://www.googleapis.com/auth/drive",
                "https://www.googleapis.com/auth/documents",
            ],
        )
        user_drive = build("drive", "v3", credentials=creds)
        user_docs = build("docs", "v1", credentials=creds)
        return user_drive, user_docs

    def _create_doc(self, titulo: str, contenido: str) -> dict:
        if not self.drive:
            return {"error": "Drive no configurado"}
        try:
            owner_email = os.getenv("GOOGLE_OWNER_EMAIL", "").strip()
            owner_email = owner_email  # usado más abajo si no hay OAuth
            print(f"📄 Docs: creando documento '{titulo}' vía Drive API...")

            # Usar OAuth del usuario si está disponible; si no, service account
            user_drive, user_docs = self._get_user_drive_docs()
            drive_client = user_drive if user_drive else self.drive
            docs_client = user_docs if user_docs else self.docs
            auth_mode = "OAuth usuario" if user_drive else "service account"
            print(f"📄 Docs: usando {auth_mode}")

            folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
            file_metadata = {
                "name": titulo,
                "mimeType": "application/vnd.google-apps.document",
            }
            if folder_id:
                file_metadata["parents"] = [folder_id]

            doc = drive_client.files().create(
                body=file_metadata, fields="id"
            ).execute()
            doc_id = doc.get("id")
            print(f"📄 Docs: documento creado con ID {doc_id}, insertando contenido...")

            # Insertar contenido vía Docs API
            requests = [{"insertText": {"location": {"index": 1}, "text": contenido}}]
            docs_client.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()

            # Compartir con el propietario solo si se usó service account
            if not user_drive and owner_email:
                drive_client.permissions().create(
                    fileId=doc_id,
                    body={"type": "user", "role": "writer", "emailAddress": owner_email},
                    sendNotificationEmail=False,
                ).execute()
                print(f"✅ Docs: documento compartido con {owner_email}")
            else:
                print("✅ Docs: documento creado en Drive del usuario")

            return {
                "status": "creado",
                "titulo": titulo,
                "documentId": doc_id,
                "link": f"https://docs.google.com/document/d/{doc_id}/edit",
            }
        except Exception as e:
            print(f"❌ Docs error: {type(e).__name__}: {e}")
            return {"error": str(e)}

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
