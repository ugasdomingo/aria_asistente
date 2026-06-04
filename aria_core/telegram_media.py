from __future__ import annotations

import os
import tempfile
from pathlib import Path

from .media import OpenAIMediaAnalyzer
from .message_context import AttachmentContext, MessageContext


class TelegramMediaAdapter:
    def __init__(self, bot_token: str, analyzer: OpenAIMediaAnalyzer | None = None):
        self.bot_token = bot_token
        self.analyzer = analyzer or OpenAIMediaAnalyzer()
        self.max_bytes = int(float(os.getenv("ARIA_MEDIA_MAX_MB", "20")) * 1024 * 1024)

    async def build_context(self, message: dict) -> MessageContext:
        caption = (message.get("caption") or "").strip()
        attachment = _select_attachment(message)
        if not attachment:
            return MessageContext(caption=caption)

        kind, payload = attachment
        metadata = _metadata_for(kind, payload)
        file_id = payload.get("file_id")
        file_size = int(payload.get("file_size") or 0)

        if file_size and file_size > self.max_bytes:
            return MessageContext(
                caption=caption,
                attachments=[
                    AttachmentContext(
                        kind=kind,
                        warning=f"Archivo demasiado grande ({round(file_size / 1024 / 1024, 1)} MB). Limite: {round(self.max_bytes / 1024 / 1024, 1)} MB.",
                        metadata=metadata,
                    )
                ],
            )

        if not file_id:
            return MessageContext(
                caption=caption,
                attachments=[AttachmentContext(kind=kind, warning="Telegram no envio file_id para este adjunto.", metadata=metadata)],
            )

        suffix = _suffix_for(kind, payload)
        tmp_path = ""
        try:
            tmp_path = await self._download_file(file_id, suffix)
            attachment_context = await self._process_file(kind, tmp_path, caption, metadata)
            return MessageContext(caption=caption, attachments=[attachment_context])
        finally:
            if tmp_path:
                try:
                    Path(tmp_path).unlink(missing_ok=True)
                except OSError:
                    pass

    async def _download_file(self, file_id: str, suffix: str) -> str:
        import httpx

        async with httpx.AsyncClient(timeout=60) as http:
            file_resp = await http.get(f"https://api.telegram.org/bot{self.bot_token}/getFile", params={"file_id": file_id})
            file_resp.raise_for_status()
            file_data = file_resp.json()
            if not file_data.get("ok"):
                raise RuntimeError(f"Telegram getFile fallo: {file_data}")

            file_path = file_data.get("result", {}).get("file_path")
            file_size = int(file_data.get("result", {}).get("file_size") or 0)
            if file_size and file_size > self.max_bytes:
                raise RuntimeError("El archivo supera el limite configurado.")
            if not file_path:
                raise RuntimeError("Telegram no devolvio file_path.")

            download_url = f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            download_resp = await http.get(download_url)
            download_resp.raise_for_status()
            if len(download_resp.content) > self.max_bytes:
                raise RuntimeError("El archivo descargado supera el limite configurado.")

        handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            handle.write(download_resp.content)
            return handle.name
        finally:
            handle.close()

    async def _process_file(self, kind: str, path: str, caption: str, metadata: dict) -> AttachmentContext:
        try:
            if kind == "image":
                summary = self.analyzer.analyze_image(path, _caption_prompt(caption))
                return AttachmentContext(kind=kind, summary=summary, metadata=metadata)

            if kind in {"voice", "audio"}:
                transcript = self.analyzer.transcribe_audio(path)
                return AttachmentContext(kind=kind, transcript=transcript, metadata=metadata)

            if kind in {"video", "video_note"}:
                transcript, summary, warning = self.analyzer.analyze_video(path)
                return AttachmentContext(kind=kind, transcript=transcript, summary=summary, warning=warning, metadata=metadata)

            return AttachmentContext(kind=kind, warning="Tipo de adjunto no soportado todavia.", metadata=metadata)
        except Exception as exc:
            return AttachmentContext(kind=kind, warning=f"No pude procesar el adjunto: {exc}", metadata=metadata)


def _select_attachment(message: dict) -> tuple[str, dict] | None:
    if message.get("photo"):
        return "image", sorted(message["photo"], key=lambda item: item.get("file_size", 0))[-1]
    if message.get("voice"):
        return "voice", message["voice"]
    if message.get("audio"):
        return "audio", message["audio"]
    if message.get("video"):
        return "video", message["video"]
    if message.get("video_note"):
        return "video_note", message["video_note"]
    document = message.get("document")
    if document:
        mime_type = document.get("mime_type", "")
        if mime_type.startswith("image/"):
            return "image", document
        if mime_type.startswith("audio/"):
            return "audio", document
        if mime_type.startswith("video/"):
            return "video", document
        return "document", document
    return None


def _metadata_for(kind: str, payload: dict) -> dict:
    keys = ["file_name", "mime_type", "file_size", "duration", "width", "height"]
    metadata = {"telegram_kind": kind}
    for key in keys:
        if payload.get(key) is not None:
            metadata[key] = payload[key]
    return metadata


def _suffix_for(kind: str, payload: dict) -> str:
    file_name = payload.get("file_name") or ""
    if "." in file_name:
        return "." + file_name.rsplit(".", 1)[-1]
    mime_type = payload.get("mime_type", "")
    if mime_type == "image/png":
        return ".png"
    if mime_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if mime_type == "audio/mpeg":
        return ".mp3"
    if mime_type == "audio/ogg" or kind == "voice":
        return ".ogg"
    if mime_type == "video/mp4" or kind in {"video", "video_note"}:
        return ".mp4"
    return ".bin"


def _caption_prompt(caption: str) -> str:
    base = "Analiza esta imagen para que ARIA pueda responder al usuario con precision."
    if caption:
        return f"{base}\nCaption del usuario: {caption}"
    return base
