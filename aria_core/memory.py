from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

MADRID_TZ = ZoneInfo("Europe/Madrid")


class MemoryBackend(Protocol):
    async def get_memoria(self) -> list[dict]:
        ...

    async def save_memoria(self, categoria: str, contenido: str) -> str:
        ...


@dataclass
class MemoryRecord:
    id: str
    category: str
    content: str
    version: int = 1
    source: str = "unknown"
    confidence: float = 0.75
    status: str = "active"
    updated_at: str = ""
    history: list[dict] = field(default_factory=list)

    @classmethod
    def from_airtable_fields(cls, fields: dict) -> "MemoryRecord":
        category = str(fields.get("Categoria") or fields.get("category") or "memoria_general")
        raw_content = str(fields.get("Contenido") or fields.get("content") or "")
        updated_at = str(fields.get("Actualizado") or fields.get("updated_at") or "")

        try:
            payload = json.loads(raw_content)
        except (TypeError, json.JSONDecodeError):
            payload = {}

        if isinstance(payload, dict) and payload.get("_aria_memory_v") == 2:
            return cls(
                id=str(payload.get("id") or f"mem_{uuid.uuid4().hex}"),
                category=str(payload.get("category") or category),
                content=str(payload.get("content") or ""),
                version=int(payload.get("version") or 1),
                source=str(payload.get("source") or "unknown"),
                confidence=float(payload.get("confidence") or 0.75),
                status=str(payload.get("status") or "active"),
                updated_at=str(payload.get("updated_at") or updated_at),
                history=list(payload.get("history") or []),
            )

        return cls(
            id=f"legacy_{category.lower().replace(' ', '_')}",
            category=category,
            content=raw_content,
            source="legacy",
            updated_at=updated_at,
        )

    def to_storage_content(self) -> str:
        return json.dumps(
            {
                "_aria_memory_v": 2,
                "id": self.id,
                "category": self.category,
                "content": self.content,
                "version": self.version,
                "source": self.source,
                "confidence": self.confidence,
                "status": self.status,
                "updated_at": self.updated_at,
                "history": self.history[-20:],
            },
            ensure_ascii=False,
        )

    def to_model_text(self) -> str:
        return f"[{self.category} | v{self.version} | {self.id}]\n{self.content}"


class StructuredMemoryStore:
    def __init__(self, backend: MemoryBackend):
        self.backend = backend

    async def list_records(self, include_deleted: bool = False) -> list[MemoryRecord]:
        records = [MemoryRecord.from_airtable_fields(item) for item in await self.backend.get_memoria()]
        if include_deleted:
            return records
        return [record for record in records if record.status == "active" and record.content.strip()]

    async def search(self, query: str, categories: list[str] | None = None, limit: int = 8) -> list[MemoryRecord]:
        query_terms = _terms(query)
        category_set = {item.lower() for item in categories or []}
        scored: list[tuple[int, MemoryRecord]] = []

        for record in await self.list_records():
            if category_set and record.category.lower() not in category_set:
                continue
            haystack = f"{record.category} {record.content}".lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score or not query_terms:
                scored.append((score, record))

        scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
        return [record for _, record in scored[:limit]]

    async def upsert(self, category: str, content: str, source: str = "user", confidence: float = 0.85) -> MemoryRecord:
        now = _now()
        records = await self.list_records(include_deleted=True)
        match = next((record for record in records if record.category.lower() == category.lower()), None)

        if match:
            previous = {
                "version": match.version,
                "content": match.content,
                "updated_at": match.updated_at,
                "operation": "upsert",
            }
            match.version += 1
            match.content = content
            match.source = source
            match.confidence = confidence
            match.status = "active"
            match.updated_at = now
            match.history.append(previous)
            record = match
        else:
            record = MemoryRecord(
                id=f"mem_{uuid.uuid4().hex}",
                category=category,
                content=content,
                source=source,
                confidence=confidence,
                updated_at=now,
            )

        await self.backend.save_memoria(record.category, record.to_storage_content())
        return record

    async def replace(self, memory_id: str, new_content: str, reason: str) -> MemoryRecord:
        record = await self._find(memory_id)
        now = _now()
        record.history.append(
            {
                "version": record.version,
                "content": record.content,
                "updated_at": record.updated_at,
                "operation": "replace",
                "reason": reason,
            }
        )
        record.version += 1
        record.content = new_content
        record.updated_at = now
        record.status = "active"
        await self.backend.save_memoria(record.category, record.to_storage_content())
        return record

    async def delete(self, memory_id: str, reason: str) -> MemoryRecord:
        record = await self._find(memory_id)
        record.history.append(
            {
                "version": record.version,
                "content": record.content,
                "updated_at": record.updated_at,
                "operation": "delete",
                "reason": reason,
            }
        )
        record.version += 1
        record.status = "deleted"
        record.updated_at = _now()
        await self.backend.save_memoria(record.category, record.to_storage_content())
        return record

    async def capture_user_correction(self, text: str, category: str) -> MemoryRecord:
        content = (
            "Correccion o preferencia indicada por Domingo. "
            f"Aplicar en futuras conversaciones: {text.strip()}"
        )
        return await self.upsert(category=category, content=content, source="user_correction", confidence=0.95)

    async def _find(self, memory_id: str) -> MemoryRecord:
        normalized = memory_id.strip().lower()
        records = await self.list_records(include_deleted=True)
        for record in records:
            if record.id.lower() == normalized or record.category.lower() == normalized:
                return record
        raise ValueError(f"No se encontro memoria con id '{memory_id}'")


def _terms(text: str) -> list[str]:
    return [term for term in text.lower().replace(",", " ").replace(".", " ").split() if len(term) > 2]


def _now() -> str:
    return datetime.now(MADRID_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
