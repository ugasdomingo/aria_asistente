from __future__ import annotations

from dotenv import load_dotenv

from aria_core.orchestrator import AriaOrchestrator
from google_apis import GoogleAPIs

load_dotenv()

google = GoogleAPIs()
orchestrator = AriaOrchestrator(google)


async def process_message(chat_id: str, user_message: str) -> str:
    return await orchestrator.process_message(chat_id, user_message)


async def generate_daily_summary() -> str:
    return await orchestrator.generate_daily_summary()
