from __future__ import annotations

import base64
import mimetypes
import os
from pathlib import Path
from tempfile import TemporaryDirectory


class OpenAIMediaAnalyzer:
    def __init__(self, client=None):
        if client is None:
            from openai import OpenAI

            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.client = client
        self.vision_model = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini")
        self.transcribe_model = os.getenv("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")
        self.video_max_frames = int(os.getenv("ARIA_VIDEO_MAX_FRAMES", "4"))

    def analyze_image(self, path: str, prompt: str = "") -> str:
        user_prompt = prompt or (
            "Analiza esta imagen para que ARIA pueda responder al usuario. "
            "Describe elementos relevantes, texto visible, contexto, posibles acciones y cualquier dato util."
        )
        response = self.client.responses.create(
            model=self.vision_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_prompt},
                        {"type": "input_image", "image_url": _data_url(path), "detail": "auto"},
                    ],
                }
            ],
        )
        return getattr(response, "output_text", "").strip()

    def analyze_images(self, paths: list[str], prompt: str = "") -> str:
        if not paths:
            return ""
        content = [
            {
                "type": "input_text",
                "text": prompt
                or "Analiza estos fotogramas de un video y resume que ocurre, objetos/personas visibles y detalles utiles.",
            }
        ]
        for path in paths:
            content.append({"type": "input_image", "image_url": _data_url(path), "detail": "low"})
        response = self.client.responses.create(
            model=self.vision_model,
            input=[{"role": "user", "content": content}],
        )
        return getattr(response, "output_text", "").strip()

    def transcribe_audio(self, path: str) -> str:
        with open(path, "rb") as handle:
            response = self.client.audio.transcriptions.create(
                model=self.transcribe_model,
                file=handle,
            )
        return getattr(response, "text", "").strip()

    def analyze_video(self, path: str) -> tuple[str, str, str]:
        transcript = ""
        summary = ""
        warning = ""

        try:
            transcript = self.transcribe_audio(path)
        except Exception as exc:
            warning = f"No se pudo transcribir el audio del video: {exc}"

        try:
            with TemporaryDirectory() as tmpdir:
                frames = extract_video_frames(path, tmpdir, self.video_max_frames)
                if frames:
                    summary = self.analyze_images(frames)
                else:
                    warning = _append_warning(warning, "No se pudieron extraer fotogramas representativos.")
        except Exception as exc:
            warning = _append_warning(warning, f"No se pudieron analizar fotogramas: {exc}")

        return transcript, summary, warning


def extract_video_frames(path: str, output_dir: str, max_frames: int) -> list[str]:
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("opencv-python-headless no esta instalado") from exc

    capture = cv2.VideoCapture(path)
    if not capture.isOpened():
        return []

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if frame_count <= 0:
        capture.release()
        return []

    max_frames = max(1, max_frames)
    positions = sorted({int((frame_count - 1) * (idx + 1) / (max_frames + 1)) for idx in range(max_frames)})
    frame_paths: list[str] = []

    for idx, position in enumerate(positions):
        capture.set(cv2.CAP_PROP_POS_FRAMES, position)
        ok, frame = capture.read()
        if not ok:
            continue
        frame_path = str(Path(output_dir) / f"frame_{idx}.jpg")
        cv2.imwrite(frame_path, frame)
        frame_paths.append(frame_path)

    capture.release()
    return frame_paths


def _data_url(path: str) -> str:
    mime_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _append_warning(current: str, extra: str) -> str:
    return f"{current} {extra}".strip() if current else extra
