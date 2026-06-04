from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


MADRID_TZ = ZoneInfo("Europe/Madrid")


@dataclass(frozen=True)
class Brand:
    name: str
    description: str
    audience: str
    tone: str
    offer: str
    cta: str
    restrictions: str

    def airtable_fields(self) -> dict:
        return {
            "Marca": self.name,
            "Descripcion": self.description,
            "Audiencia": self.audience,
            "Tono": self.tone,
            "Oferta": self.offer,
            "CTA Principal": self.cta,
            "Restricciones": self.restrictions,
        }


BRANDS: dict[str, Brand] = {
    "diginode": Brand(
        name="Diginode",
        description="Soluciones de IA, automatizacion y sistemas digitales para empresas.",
        audience="Fundadores, directores y equipos operativos que quieren escalar procesos sin perder control.",
        tone="Consultivo, directo, experto y orientado a resultados.",
        offer="Automatizacion, agentes de IA, integraciones y optimizacion de operaciones.",
        cta="Agenda una llamada de diagnostico.",
        restrictions="No prometer resultados garantizados; priorizar claridad, evidencia y casos de uso.",
    ),
    "silicity": Brand(
        name="Silicity",
        description="Marca de tecnologia e innovacion aplicada a negocios y experiencias digitales.",
        audience="Empresas y equipos que buscan modernizar su presencia, sistemas y crecimiento digital.",
        tone="Sofisticado, claro, aspiracional y practico.",
        offer="Estrategia, contenido y soluciones digitales para crecer con una marca mas fuerte.",
        cta="Pide una propuesta inicial.",
        restrictions="Evitar claims vagos; conectar siempre creatividad con impacto de negocio.",
    ),
}


@dataclass(frozen=True)
class CampaignBrief:
    brand_key: str
    objective: str
    product_offer: str
    audience: str
    main_pain: str
    cta: str
    tone: str
    start_date: date
    promotion: str
    restrictions: str
    existing_assets: str

    @property
    def brand(self) -> Brand:
        return BRANDS[self.brand_key]

    @property
    def end_date(self) -> date:
        return self.start_date + timedelta(days=6)

    @property
    def theme(self) -> str:
        return f"{self.product_offer} para resolver {self.main_pain}"

    @classmethod
    def from_answers(cls, answers: dict, today: date | None = None) -> "CampaignBrief":
        today = today or datetime.now(MADRID_TZ).date()
        brand_key = normalize_brand(str(answers.get("marca", ""))) or "diginode"
        brand = BRANDS[brand_key]
        return cls(
            brand_key=brand_key,
            objective=_clean(answers.get("objetivo")) or "generar oportunidades comerciales cualificadas",
            product_offer=_clean(answers.get("producto_oferta")) or brand.offer,
            audience=_clean(answers.get("audiencia")) or brand.audience,
            main_pain=_clean(answers.get("dolor_principal")) or "falta de claridad para pasar de interes a accion",
            cta=_clean(answers.get("cta")) or brand.cta,
            tone=_clean(answers.get("tono")) or brand.tone,
            start_date=parse_campaign_date(_clean(answers.get("fecha_inicio")), today=today),
            promotion=_clean(answers.get("promocion")) or "sin promocion especifica",
            restrictions=_clean(answers.get("restricciones")) or brand.restrictions,
            existing_assets=_clean(answers.get("assets")) or "sin activos existentes indicados",
        )


@dataclass(frozen=True)
class Campaign:
    campaign_id: str
    brand: Brand
    objective: str
    theme: str
    start_date: date
    end_date: date
    status: str
    notes: str

    def airtable_fields(self) -> dict:
        return {
            "CampaignID": self.campaign_id,
            "Marca": self.brand.name,
            "Objetivo": self.objective,
            "Tema": self.theme,
            "Fecha Inicio": self.start_date.isoformat(),
            "Fecha Fin": self.end_date.isoformat(),
            "Estado": self.status,
            "Notas": self.notes,
        }


@dataclass(frozen=True)
class DailyContentPlan:
    day: int
    date: date
    angle: str
    central_message: str
    cta: str


@dataclass(frozen=True)
class ContentPiece:
    campaign_id: str
    day: int
    date: date
    channel: str
    format: str
    title: str
    copy: str
    hashtags: list[str]
    image_prompts: list[str]
    video_prompt: str
    video_script: str
    cta: str
    notes: str
    status: str = "Pendiente"

    def airtable_fields(self) -> dict:
        return {
            "CampaignID": self.campaign_id,
            "Dia": self.day,
            "Fecha": self.date.isoformat(),
            "Canal": self.channel,
            "Formato": self.format,
            "Titulo": self.title,
            "Copy": self.copy,
            "Hashtags": " ".join(self.hashtags),
            "Prompt Imagen": "\n".join(f"{idx + 1}. {prompt}" for idx, prompt in enumerate(self.image_prompts)),
            "Prompt Video": self.video_prompt,
            "Guion Video": self.video_script,
            "CTA": self.cta,
            "Estado": self.status,
        }


@dataclass(frozen=True)
class CampaignBundle:
    brand: Brand
    campaign: Campaign
    daily_plans: list[DailyContentPlan]
    pieces: list[ContentPiece]

    def airtable_payload(self) -> dict:
        return {
            "brand": self.brand.airtable_fields(),
            "campaign": self.campaign.airtable_fields(),
            "content": [piece.airtable_fields() for piece in self.pieces],
        }


class CampaignGenerator:
    def generate(self, brief: CampaignBrief) -> CampaignBundle:
        campaign_id = _campaign_id(brief.brand.name, brief.start_date)
        campaign = Campaign(
            campaign_id=campaign_id,
            brand=brief.brand,
            objective=brief.objective,
            theme=brief.theme,
            start_date=brief.start_date,
            end_date=brief.end_date,
            status="Planificada",
            notes=(
                f"Promocion: {brief.promotion}. Activos existentes: {brief.existing_assets}. "
                f"Restricciones: {brief.restrictions}."
            ),
        )
        daily_plans = [_daily_plan(brief, day) for day in range(1, 8)]
        pieces: list[ContentPiece] = []
        for plan in daily_plans:
            pieces.extend(_pieces_for_day(campaign_id, brief, plan))
        return CampaignBundle(brand=brief.brand, campaign=campaign, daily_plans=daily_plans, pieces=pieces)


def normalize_brand(value: str) -> str | None:
    normalized = value.strip().lower()
    for key, brand in BRANDS.items():
        if key in normalized or brand.name.lower() in normalized:
            return key
    return None


def parse_campaign_date(value: str, today: date | None = None) -> date:
    today = today or datetime.now(MADRID_TZ).date()
    raw = (value or "").strip().lower()
    if not raw or raw in {"hoy", "lo antes posible", "cuanto antes"}:
        return today
    if raw in {"manana", "mañana"}:
        return today + timedelta(days=1)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return today


def _daily_plan(brief: CampaignBrief, day: int) -> DailyContentPlan:
    angles = [
        "problema urgente",
        "coste de no actuar",
        "nuevo enfoque",
        "prueba y autoridad",
        "objeciones frecuentes",
        "caso de uso concreto",
        "decision y siguiente paso",
    ]
    angle = angles[day - 1]
    central_message = (
        f"{brief.brand.name} ayuda a {brief.audience} a avanzar hacia '{brief.objective}' "
        f"resolviendo {brief.main_pain} con {brief.product_offer}."
    )
    return DailyContentPlan(
        day=day,
        date=brief.start_date + timedelta(days=day - 1),
        angle=angle,
        central_message=central_message,
        cta=brief.cta,
    )


def _pieces_for_day(campaign_id: str, brief: CampaignBrief, plan: DailyContentPlan) -> list[ContentPiece]:
    base_title = f"Dia {plan.day}: {plan.angle.title()} - {brief.brand.name}"
    hashtags = _hashtags(brief)
    carousel = ContentPiece(
        campaign_id=campaign_id,
        day=plan.day,
        date=plan.date,
        channel="Instagram",
        format="instagram_carousel",
        title=f"{base_title} | Carrusel",
        copy=(
            f"{plan.central_message}\n\n"
            f"En este carrusel: sintoma, impacto y paso practico para actuar hoy.\n\n"
            f"{brief.cta}"
        ),
        hashtags=hashtags,
        image_prompts=[
            f"Portada vertical 4:5 para {brief.brand.name}, tema '{plan.angle}', texto grande y limpio, tono {brief.tone}.",
            f"Diapositiva educativa 4:5 mostrando el problema '{brief.main_pain}' con iconografia sobria y espacio para bullets.",
            f"Diapositiva final 4:5 con CTA '{brief.cta}', marca {brief.brand.name}, composicion clara y profesional.",
        ],
        video_prompt="",
        video_script="",
        cta=brief.cta,
        notes="Carrusel minimo de 3 imagenes. Publicacion manual.",
    )
    video_prompt = (
        f"Video vertical 9:16 de 8-10 segundos para {brief.brand.name}. "
        f"Visual dinamico sobre '{plan.angle}', ritmo rapido, texto en pantalla, cierre con CTA."
    )
    video_script = (
        "Duracion objetivo: 8-10 segundos.\n"
        f"0-2s: Hook visual sobre {brief.main_pain}.\n"
        f"2-6s: Mostrar como {brief.product_offer} cambia la situacion.\n"
        f"6-9s: Rematar con beneficio ligado a {brief.objective}.\n"
        f"9-10s: CTA: {brief.cta}."
    )
    video_pieces = [
        _video_piece(campaign_id, brief, plan, "Instagram Stories", video_prompt, video_script, hashtags),
        _video_piece(campaign_id, brief, plan, "YouTube Shorts", video_prompt, video_script, hashtags),
        _video_piece(campaign_id, brief, plan, "WhatsApp Stories", video_prompt, video_script, hashtags),
    ]
    linkedin = ContentPiece(
        campaign_id=campaign_id,
        day=plan.day,
        date=plan.date,
        channel="LinkedIn",
        format="linkedin_post",
        title=f"{base_title} | LinkedIn",
        copy=(
            f"{brief.audience} no necesita mas ruido: necesita una forma concreta de resolver {brief.main_pain}.\n\n"
            f"La idea de hoy: {plan.central_message}\n\n"
            f"Si el objetivo es {brief.objective}, el siguiente paso debe ser pequeno, medible y accionable.\n\n"
            f"{brief.cta}"
        ),
        hashtags=hashtags[:4],
        image_prompts=[
            f"Imagen profesional para LinkedIn sobre '{plan.angle}', marca {brief.brand.name}, estilo {brief.tone}, sin exceso de texto.",
        ],
        video_prompt="",
        video_script="",
        cta=brief.cta,
        notes="Post de LinkedIn con imagen. Publicacion manual.",
    )
    return [carousel, *video_pieces, linkedin]


def _video_piece(
    campaign_id: str,
    brief: CampaignBrief,
    plan: DailyContentPlan,
    channel: str,
    video_prompt: str,
    video_script: str,
    hashtags: list[str],
) -> ContentPiece:
    platform_note = {
        "Instagram Stories": "Texto corto en pantalla y sticker/CTA manual.",
        "YouTube Shorts": "Titulo claro, hook fuerte en el primer segundo.",
        "WhatsApp Stories": "Copy mas directo y cercano para contactos existentes.",
    }[channel]
    return ContentPiece(
        campaign_id=campaign_id,
        day=plan.day,
        date=plan.date,
        channel=channel,
        format="vertical_video",
        title=f"Dia {plan.day}: {brief.brand.name} en 8-10s | {channel}",
        copy=f"{plan.angle.title()}: {brief.objective}. {brief.cta}",
        hashtags=hashtags,
        image_prompts=[],
        video_prompt=video_prompt,
        video_script=video_script,
        cta=brief.cta,
        notes=f"Reutiliza el mismo video vertical. {platform_note}",
    )


def _hashtags(brief: CampaignBrief) -> list[str]:
    brand_tag = f"#{brief.brand.name.replace(' ', '')}"
    if brief.brand_key == "diginode":
        base = [brand_tag, "#IA", "#Automatizacion", "#Negocios", "#Productividad", "#TransformacionDigital"]
    else:
        base = [brand_tag, "#Innovacion", "#MarcaDigital", "#Crecimiento", "#Contenido", "#Estrategia"]
    return base


def _campaign_id(brand_name: str, start_date: date) -> str:
    token = uuid.uuid4().hex[:6].upper()
    brand_slug = "".join(ch for ch in brand_name.upper() if ch.isalnum())
    return f"CMP-{brand_slug}-{start_date.strftime('%Y%m%d')}-{token}"


def _clean(value) -> str:
    return str(value or "").strip()
