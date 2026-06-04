from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass


FOLDER_MIME = "application/vnd.google-apps.folder"
DOC_MIME = "application/vnd.google-apps.document"


@dataclass
class DriveDocument:
    id: str
    name: str
    link: str = ""
    modified_time: str = ""


class DriveWorkspace:
    def __init__(self, google, folder_name: str = "Aria"):
        self.google = google
        self.folder_name = folder_name
        self._folder_id: str | None = None

    async def list_documents(self) -> list[dict]:
        return await asyncio.to_thread(self._list_documents)

    async def create_document(self, title: str, content: str) -> dict:
        return await asyncio.to_thread(self._create_document, title, content)

    async def read_document(self, document_id: str) -> dict:
        return await asyncio.to_thread(self._read_document, document_id)

    async def trash_document(self, document_id: str) -> dict:
        return await asyncio.to_thread(self._trash_document, document_id)

    def _clients(self):
        user_drive, user_docs = (None, None)
        if hasattr(self.google, "_get_user_drive_docs"):
            user_drive, user_docs = self.google._get_user_drive_docs()
        drive_client = user_drive or getattr(self.google, "drive", None)
        docs_client = user_docs or getattr(self.google, "docs", None)
        if not drive_client:
            raise RuntimeError("Drive no configurado")
        if not docs_client:
            raise RuntimeError("Docs no configurado")
        return drive_client, docs_client

    def _ensure_folder_id(self) -> str:
        if self._folder_id:
            return self._folder_id

        drive_client, _ = self._clients()
        env_folder_id = os.getenv("ARIA_DRIVE_FOLDER_ID", "").strip() or os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()
        if env_folder_id:
            folder = drive_client.files().get(fileId=env_folder_id, fields="id,name,mimeType,trashed").execute()
            if folder.get("trashed"):
                raise RuntimeError("La carpeta Aria configurada esta en la papelera")
            if folder.get("mimeType") != FOLDER_MIME:
                raise RuntimeError("ARIA_DRIVE_FOLDER_ID no apunta a una carpeta")
            self._folder_id = env_folder_id
            return self._folder_id

        query = (
            f"name='{_escape_query(self.folder_name)}' "
            f"and mimeType='{FOLDER_MIME}' and trashed=false"
        )
        result = drive_client.files().list(q=query, fields="files(id,name)", pageSize=10).execute()
        files = result.get("files", [])
        if files:
            self._folder_id = files[0]["id"]
            return self._folder_id

        folder = drive_client.files().create(
            body={"name": self.folder_name, "mimeType": FOLDER_MIME},
            fields="id",
        ).execute()
        self._folder_id = folder["id"]
        return self._folder_id

    def _list_documents(self) -> list[dict]:
        drive_client, _ = self._clients()
        folder_id = self._ensure_folder_id()
        query = f"'{folder_id}' in parents and mimeType='{DOC_MIME}' and trashed=false"
        result = drive_client.files().list(
            q=query,
            fields="files(id,name,webViewLink,modifiedTime)",
            orderBy="modifiedTime desc",
            pageSize=50,
        ).execute()
        return [
            {
                "id": item.get("id", ""),
                "name": item.get("name", ""),
                "link": item.get("webViewLink", ""),
                "modified_time": item.get("modifiedTime", ""),
            }
            for item in result.get("files", [])
        ]

    def _create_document(self, title: str, content: str) -> dict:
        drive_client, docs_client = self._clients()
        folder_id = self._ensure_folder_id()
        doc = drive_client.files().create(
            body={"name": title, "mimeType": DOC_MIME, "parents": [folder_id]},
            fields="id,webViewLink",
        ).execute()
        doc_id = doc["id"]
        if content:
            docs_client.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
            ).execute()
        return {
            "status": "creado",
            "titulo": title,
            "documentId": doc_id,
            "link": doc.get("webViewLink", f"https://docs.google.com/document/d/{doc_id}/edit"),
            "folder": self.folder_name,
        }

    def _read_document(self, document_id: str) -> dict:
        _, docs_client = self._clients()
        file_info = self._assert_document_in_folder(document_id)
        document = docs_client.documents().get(documentId=document_id).execute()
        return {
            "status": "ok",
            "documentId": document_id,
            "title": file_info.get("name", document.get("title", "")),
            "content": _extract_doc_text(document),
            "link": file_info.get("webViewLink", ""),
        }

    def _trash_document(self, document_id: str) -> dict:
        drive_client, _ = self._clients()
        file_info = self._assert_document_in_folder(document_id)
        drive_client.files().update(fileId=document_id, body={"trashed": True}, fields="id,trashed").execute()
        return {
            "status": "trashed",
            "documentId": document_id,
            "title": file_info.get("name", ""),
            "message": "Documento enviado a la papelera.",
        }

    def _assert_document_in_folder(self, document_id: str) -> dict:
        drive_client, _ = self._clients()
        folder_id = self._ensure_folder_id()
        file_info = drive_client.files().get(
            fileId=document_id,
            fields="id,name,mimeType,parents,trashed,webViewLink",
        ).execute()
        if file_info.get("trashed"):
            raise RuntimeError("El documento esta en la papelera")
        if file_info.get("mimeType") != DOC_MIME:
            raise RuntimeError("El archivo no es un Google Doc")
        if folder_id not in file_info.get("parents", []):
            raise RuntimeError("Operacion rechazada: el documento no esta dentro de la carpeta Aria")
        return file_info


def _extract_doc_text(document: dict) -> str:
    parts: list[str] = []
    for item in document.get("body", {}).get("content", []):
        paragraph = item.get("paragraph")
        if not paragraph:
            continue
        for element in paragraph.get("elements", []):
            text_run = element.get("textRun")
            if text_run and text_run.get("content"):
                parts.append(text_run["content"])
    return "".join(parts).strip()


def _escape_query(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")

