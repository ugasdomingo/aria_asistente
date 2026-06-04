from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AttachmentContext:
    kind: str
    summary: str = ""
    transcript: str = ""
    metadata: dict = field(default_factory=dict)
    warning: str = ""

    def to_prompt_text(self) -> str:
        parts = [f"Adjunto recibido: {self.kind}."]
        if self.transcript:
            parts.append(f"Transcripcion:\n{self.transcript}")
        if self.summary:
            parts.append(f"Resumen visual/contextual:\n{self.summary}")
        if self.warning:
            parts.append(f"Aviso tecnico: {self.warning}")
        if self.metadata:
            parts.append(f"Metadatos: {self.metadata}")
        return "\n\n".join(parts)


@dataclass
class MessageContext:
    caption: str = ""
    attachments: list[AttachmentContext] = field(default_factory=list)

    def to_prompt_text(self) -> str:
        parts: list[str] = []
        if self.caption:
            parts.append(f"Caption del usuario: {self.caption}")
        for attachment in self.attachments:
            parts.append(attachment.to_prompt_text())
        return "\n\n".join(parts)

    @property
    def has_content(self) -> bool:
        return bool(self.caption or self.attachments)

