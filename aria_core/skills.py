from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Protocol

from .campaigns import BRANDS, CampaignBrief, CampaignBundle, CampaignGenerator, normalize_brand
from .memory import StructuredMemoryStore


class DriveCreator(Protocol):
    async def create_document(self, title: str, content: str) -> dict:
        ...


class CampaignStore(Protocol):
    async def save_campaign_bundle(self, bundle: CampaignBundle) -> dict:
        ...

    async def list_campaigns(self, brand: str | None = None, limit: int = 10) -> list[dict]:
        ...

    async def get_campaign_status(self, brand: str | None = None) -> list[dict]:
        ...

    async def get_campaign_today(self, brand: str | None = None, today: str | None = None) -> list[dict]:
        ...


@dataclass(frozen=True)
class InterviewField:
    key: str
    label: str
    question: str


@dataclass(frozen=True)
class SkillDefinition:
    id: str
    names: list[str]
    commands: list[str]
    triggers: list[str]
    fields: list[InterviewField]


MARKETING_PLAN = SkillDefinition(
    id="marketing_plan",
    names=["marketing", "plan de marketing"],
    commands=["/skill marketing", "/habilidad marketing", "/marketing"],
    triggers=["plan de marketing", "campana de marketing", "estrategia de marketing", "captar leads"],
    fields=[
        InterviewField("objetivo", "Objetivo", "Que objetivo concreto quieres conseguir con el plan?"),
        InterviewField("oferta", "Negocio/oferta", "Que vendes exactamente y cual es la oferta principal?"),
        InterviewField("audiencia", "Audiencia", "A que tipo de cliente o audiencia quieres llegar?"),
        InterviewField("mercado", "Mercado", "En que mercado, zona o nicho competiras?"),
        InterviewField("presupuesto", "Presupuesto", "Que presupuesto aproximado tienes para esta campana?"),
        InterviewField("plazo", "Plazo", "En que plazo quieres ver resultados?"),
        InterviewField("canales", "Canales", "Que canales tienes disponibles ahora mismo?"),
        InterviewField("activos", "Activos existentes", "Que activos tienes ya: web, redes, base de datos, contenido, equipo o marca?"),
        InterviewField("restricciones", "Restricciones", "Que restricciones debo respetar: tiempo, legal, tono, recursos, paises o herramientas?"),
        InterviewField("metrica", "Metrica principal", "Cual sera la metrica principal de exito?"),
    ],
)


WEEKLY_CAMPAIGN = SkillDefinition(
    id="weekly_campaign",
    names=["campaign", "campana semanal", "campana de 7 dias"],
    commands=["/campaign", "/campana"],
    triggers=["campana de 7 dias", "campana para diginode", "campana para silicity", "haz campana", "creame una campana"],
    fields=[
        InterviewField("marca", "Marca", "Para que marca sera la campana: Diginode o Silicity?"),
        InterviewField("objetivo", "Objetivo", "Que objetivo concreto debe conseguir esta campana de 7 dias?"),
        InterviewField("producto_oferta", "Producto/oferta", "Que producto, servicio u oferta quieres empujar?"),
        InterviewField("audiencia", "Audiencia", "A que audiencia especifica le hablaremos?"),
        InterviewField("dolor_principal", "Dolor principal", "Cual es el dolor o problema principal que debe activar la campana?"),
        InterviewField("cta", "CTA", "Cual sera la llamada a la accion principal?"),
        InterviewField("tono", "Tono", "Que tono debe usar Aria para esta campana?"),
        InterviewField("fecha_inicio", "Fecha inicio", "Que fecha de inicio quieres? Puedes responder hoy, manana o YYYY-MM-DD."),
        InterviewField("promocion", "Promocion", "Hay promocion, oferta temporal o incentivo que debamos mencionar?"),
        InterviewField("restricciones", "Restricciones", "Que restricciones debo respetar: claims, palabras prohibidas, legal, marca o recursos?"),
        InterviewField("assets", "Assets", "Que assets existentes tienes: logos, fotos, casos, testimonios, web, videos o posts anteriores?"),
    ],
)


class SkillRegistry:
    def __init__(
        self,
        memory: StructuredMemoryStore,
        drive: DriveCreator,
        campaign_store: CampaignStore | None = None,
    ):
        self.memory = memory
        self.drive = drive
        self.campaign_store = campaign_store
        self.campaign_generator = CampaignGenerator()
        self.skills = {
            MARKETING_PLAN.id: MARKETING_PLAN,
            WEEKLY_CAMPAIGN.id: WEEKLY_CAMPAIGN,
        }

    async def handle(self, chat_id: str, text: str) -> str | None:
        active = await self._load_session(chat_id)
        normalized = _normalize_text(text)

        if active and normalized in {"cancelar", "cancela", "salir", "terminar habilidad"}:
            active["status"] = "cancelled"
            await self._save_session(chat_id, active)
            return "He cancelado la habilidad activa."

        if active and active.get("status") == "awaiting_save":
            if _is_affirmative(normalized):
                plan = active.get("plan", "")
                title = "Plan de marketing - Aria"
                result = await self.drive.create_document(title, plan)
                active["status"] = "saved"
                active["document"] = result
                await self._save_session(chat_id, active)
                return f"Listo. He guardado el plan en la carpeta Aria de Drive: {result.get('link', '')}"
            if _is_negative(normalized):
                active["status"] = "completed"
                await self._save_session(chat_id, active)
                return "Perfecto, no lo guardo en Drive. El plan queda en esta conversacion."

        if active and active.get("status") == "collecting":
            return await self._continue_interview(chat_id, active, text)

        campaign_lookup = self._match_campaign_lookup(text)
        if campaign_lookup:
            action, brand = campaign_lookup
            return await self._handle_campaign_lookup(action, brand)

        campaign_brand = self._match_campaign_start(text)
        if campaign_brand is not None:
            return await self._start_campaign(chat_id, campaign_brand)

        skill = self._match_skill(text)
        if not skill:
            return None

        session = {
            "skill_id": skill.id,
            "status": "collecting",
            "answers": {},
            "current_field": skill.fields[0].key,
        }
        await self._save_session(chat_id, session)
        return (
            "Activamos la habilidad de plan de marketing. Te voy a entrevistar rapido para no inventar datos.\n\n"
            f"1/{len(skill.fields)}. {skill.fields[0].question}"
        )

    async def _start_campaign(self, chat_id: str, brand_key: str | None) -> str:
        answers: dict = {}
        if brand_key:
            answers["marca"] = BRANDS[brand_key].name
        next_key = _next_missing(WEEKLY_CAMPAIGN, answers)
        session = {
            "skill_id": WEEKLY_CAMPAIGN.id,
            "status": "collecting",
            "answers": answers,
            "current_field": next_key,
        }
        await self._save_session(chat_id, session)
        field = _field_by_key(WEEKLY_CAMPAIGN, next_key)
        position = _field_position(WEEKLY_CAMPAIGN, next_key)
        brand_note = f"Marca detectada: {BRANDS[brand_key].name}.\n\n" if brand_key else ""
        return (
            f"{brand_note}Activamos la habilidad de campana semanal. "
            "Aria generara 7 dias de carrusel, video vertical y LinkedIn para publicar manualmente.\n\n"
            f"{position}/{len(WEEKLY_CAMPAIGN.fields)}. {field.label}: {field.question}"
        )

    async def _continue_interview(self, chat_id: str, session: dict, text: str) -> str:
        if session["skill_id"] == WEEKLY_CAMPAIGN.id:
            return await self._continue_campaign_interview(chat_id, session, text)
        return await self._continue_marketing_interview(chat_id, session, text)

    async def _continue_marketing_interview(self, chat_id: str, session: dict, text: str) -> str:
        skill = self.skills[session["skill_id"]]
        answers = dict(session.get("answers") or {})
        current_key = session.get("current_field") or _next_missing(skill, answers)
        if current_key:
            answers[current_key] = text.strip()

        next_key = _next_missing(skill, answers)
        if next_key:
            session["answers"] = answers
            session["current_field"] = next_key
            await self._save_session(chat_id, session)
            field = _field_by_key(skill, next_key)
            answered_count = len(answers)
            return f"{answered_count + 1}/{len(skill.fields)}. {field.question}"

        plan = _render_marketing_plan(answers)
        session["answers"] = answers
        session["status"] = "awaiting_save"
        session["plan"] = plan
        await self._save_session(chat_id, session)
        return (
            f"{plan}\n\n"
            "Quieres que lo guarde como Google Doc en la carpeta Aria de Drive? Responde si o no."
        )

    async def _continue_campaign_interview(self, chat_id: str, session: dict, text: str) -> str:
        answers = dict(session.get("answers") or {})
        current_key = session.get("current_field") or _next_missing(WEEKLY_CAMPAIGN, answers)
        if current_key == "marca":
            brand_key = normalize_brand(text)
            if not brand_key:
                return "Necesito elegir una de las dos marcas iniciales: Diginode o Silicity."
            answers[current_key] = BRANDS[brand_key].name
        elif current_key:
            answers[current_key] = text.strip()

        next_key = _next_missing(WEEKLY_CAMPAIGN, answers)
        if next_key:
            session["answers"] = answers
            session["current_field"] = next_key
            await self._save_session(chat_id, session)
            field = _field_by_key(WEEKLY_CAMPAIGN, next_key)
            return f"{_field_position(WEEKLY_CAMPAIGN, next_key)}/{len(WEEKLY_CAMPAIGN.fields)}. {field.label}: {field.question}"

        brief = CampaignBrief.from_answers(answers)
        bundle = self.campaign_generator.generate(brief)
        if self.campaign_store:
            save_result = await self.campaign_store.save_campaign_bundle(bundle)
        else:
            save_result = {"error": "Airtable no configurado en SkillRegistry", "created_content": 0}
        session["answers"] = answers
        session["status"] = "completed"
        session["campaign_id"] = bundle.campaign.campaign_id
        await self._save_session(chat_id, session)
        return _render_campaign_created(bundle, save_result)

    def _match_skill(self, text: str) -> SkillDefinition | None:
        normalized = _normalize_text(text)
        for skill in [MARKETING_PLAN]:
            commands = {_normalize_text(command) for command in skill.commands}
            if normalized in commands:
                return skill
            if normalized.startswith("/skill ") and any(name in normalized for name in skill.names):
                return skill
            if any(_normalize_text(trigger) in normalized for trigger in skill.triggers):
                return skill
        return None

    def _match_campaign_start(self, text: str) -> str | None | bool:
        normalized = _normalize_text(text)
        if normalized.startswith("/campaign") or normalized.startswith("/campana"):
            if any(word in normalized for word in ["status", "estado", "today", "hoy", "semana actual"]):
                return None
            return normalize_brand(normalized) or False
        if "campana" in normalized and any(word in normalized for word in ["crea", "creame", "haz", "hacer", "7 dias"]):
            return normalize_brand(normalized) or False
        return None

    def _match_campaign_lookup(self, text: str) -> tuple[str, str | None] | None:
        normalized = _normalize_text(text)
        brand_key = normalize_brand(normalized)
        brand = BRANDS[brand_key].name if brand_key else None
        if normalized in {"/campanas", "/campaigns"}:
            return ("list", None)
        if not (normalized.startswith("/campaign") or normalized.startswith("/campana")):
            return None
        if "today" in normalized or "hoy" in normalized:
            return ("today", brand)
        if "status" in normalized or "estado" in normalized or "semana actual" in normalized:
            return ("status", brand)
        return None

    async def _handle_campaign_lookup(self, action: str, brand: str | None) -> str:
        if not self.campaign_store:
            return "Airtable no esta configurado para consultar campanas todavia."
        if action == "list":
            rows = await self.campaign_store.list_campaigns(limit=8)
            return _render_campaign_list(rows)
        if action == "today":
            rows = await self.campaign_store.get_campaign_today(brand=brand)
            return _render_campaign_today(rows, brand)
        rows = await self.campaign_store.get_campaign_status(brand=brand)
        return _render_campaign_list(rows, title="Estado de campanas")

    async def _load_session(self, chat_id: str) -> dict | None:
        category = _session_category(chat_id)
        records = await self.memory.list_records()
        match = next((record for record in records if record.category == category), None)
        if not match:
            return None
        try:
            payload = json.loads(match.content)
        except json.JSONDecodeError:
            return None
        if payload.get("status") in {"cancelled", "completed", "saved"}:
            return None
        return payload

    async def _save_session(self, chat_id: str, session: dict) -> None:
        await self.memory.upsert(
            category=_session_category(chat_id),
            content=json.dumps(session, ensure_ascii=False),
            source="skill_registry",
            confidence=1.0,
        )


def _session_category(chat_id: str) -> str:
    return f"skill_session:{chat_id}"


def _next_missing(skill: SkillDefinition, answers: dict) -> str | None:
    for field in skill.fields:
        if not str(answers.get(field.key, "")).strip():
            return field.key
    return None


def _field_by_key(skill: SkillDefinition, key: str | None) -> InterviewField:
    if not key:
        raise ValueError("Missing field key")
    return next(field for field in skill.fields if field.key == key)


def _field_position(skill: SkillDefinition, key: str | None) -> int:
    if not key:
        return len(skill.fields)
    for idx, field in enumerate(skill.fields, start=1):
        if field.key == key:
            return idx
    return 1


def _normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.strip().lower())
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _is_affirmative(text: str) -> bool:
    return bool(re.search(r"\b(si|vale|ok|guarda|guardalo|adelante)\b", text, re.IGNORECASE))


def _is_negative(text: str) -> bool:
    return bool(re.search(r"\b(no|ahora no|no lo guardes)\b", text, re.IGNORECASE))


def _render_campaign_created(bundle: CampaignBundle, save_result: dict) -> str:
    campaign = bundle.campaign
    content_count = len(bundle.pieces)
    saved_count = save_result.get("created_content", 0)
    if save_result.get("error"):
        save_line = f"No pude guardarla en Airtable: {save_result['error']}"
    elif save_result.get("errors"):
        save_line = f"Guardada parcialmente en Airtable: {saved_count}/{content_count} piezas. Avisos: {' | '.join(save_result['errors'][:3])}"
    else:
        save_line = f"Guardada en Airtable: 1 campana y {saved_count} piezas de contenido."
    return (
        f"Campana semanal creada para {campaign.brand.name}.\n\n"
        f"CampaignID: {campaign.campaign_id}\n"
        f"Fechas: {campaign.start_date.isoformat()} a {campaign.end_date.isoformat()}\n"
        f"Contenido generado: 7 carruseles, 21 videos verticales adaptados y 7 posts de LinkedIn.\n"
        f"{save_line}\n\n"
        "Publicacion manual por ahora. Puedes consultar con /campaign status, /campaign today o /campanas."
    )


def _render_campaign_list(rows: list[dict], title: str = "Campanas") -> str:
    if not rows:
        return f"No encontre campanas guardadas en Airtable para esa consulta."
    lines = [title + ":"]
    for row in rows[:8]:
        lines.append(
            f"- {row.get('CampaignID', 'sin ID')} | {row.get('Marca', '')} | "
            f"{row.get('Fecha Inicio', '')} a {row.get('Fecha Fin', '')} | {row.get('Estado', '')} | "
            f"{row.get('Objetivo', '')}"
        )
    return "\n".join(lines)


def _render_campaign_today(rows: list[dict], brand: str | None) -> str:
    if not rows:
        target = f" para {brand}" if brand else ""
        return f"No encontre contenido de campana para hoy{target}."
    lines = ["Contenido de campana para hoy:"]
    for row in rows:
        lines.append(
            f"- Dia {row.get('Dia', '')} | {row.get('Canal', '')} | "
            f"{row.get('Formato', '')} | {row.get('Titulo', '')}"
        )
    return "\n".join(lines)


def _render_marketing_plan(answers: dict) -> str:
    return f"""# Plan de marketing

## Diagnostico
Objetivo: {answers['objetivo']}
Oferta: {answers['oferta']}
Audiencia: {answers['audiencia']}
Mercado: {answers['mercado']}
Presupuesto: {answers['presupuesto']}
Plazo: {answers['plazo']}

## Posicionamiento
Enfocar la comunicacion en el resultado que busca la audiencia y en la diferencia concreta de la oferta. El mensaje debe unir problema, promesa y prueba en una frase sencilla.

## Funnel recomendado
1. Atraccion: contenido y anuncios orientados al problema principal de la audiencia.
2. Captura: landing o formulario con una propuesta clara y una unica llamada a la accion.
3. Nutricion: secuencia corta de seguimiento con prueba, objeciones y caso de uso.
4. Conversion: oferta directa con urgencia realista y siguiente paso facil.
5. Retencion: seguimiento post-compra, testimonios y oferta secundaria.

## Canales
Canales disponibles: {answers['canales']}
Prioridad: empezar con los canales donde ya exista activo, audiencia o velocidad de ejecucion. Evitar abrir demasiados frentes a la vez.

## Activos y recursos
Activos actuales: {answers['activos']}
Usarlos como base antes de crear piezas nuevas: web, contenido, base de datos, redes, marca, casos o contactos.

## Calendario operativo
Semana 1: definir mensaje, oferta, landing/formulario y primera pieza de contenido.
Semana 2: lanzar primeras publicaciones o campanas, medir respuesta inicial y ajustar.
Semana 3: reforzar lo que convierta mejor, crear prueba social y seguimiento.
Semana 4: optimizar conversion, documentar aprendizajes y decidir escalado.

## KPIs
Metrica principal: {answers['metrica']}
Metricas de apoyo: alcance cualificado, coste por lead, tasa de conversion, respuesta comercial y ventas atribuidas.

## Restricciones y riesgos
Restricciones: {answers['restricciones']}
Riesgos: mensaje demasiado generico, audiencia poco definida, presupuesto disperso, falta de seguimiento comercial o medir demasiadas cosas.

## Proximas acciones
1. Escribir una propuesta de valor en una frase.
2. Elegir un canal principal y uno secundario.
3. Crear una pieza de captacion y una llamada a la accion.
4. Lanzar una prueba pequena durante 7 dias.
5. Revisar resultados y decidir si iterar, pausar o escalar.
"""
