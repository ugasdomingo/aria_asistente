from __future__ import annotations

import asyncio
import json
import os
from contextlib import nullcontext
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from openai import OpenAI

from .message_context import MessageContext
from .memory import StructuredMemoryStore
from .prompts import BASE_SYSTEM_PROMPT, MEMORY_CONTEXT_HEADER, WORKFLOW_PROMPTS
from .skills import SkillRegistry
from .tools import ToolExecutor, tool_schemas
from .tracing import TraceRecorder
from .workflows import memory_category_for_text, select_workflow

load_dotenv()

MADRID_TZ = ZoneInfo("Europe/Madrid")

try:
    from agents import Agent, FunctionTool, Runner, trace as agents_trace
except Exception:
    Agent = None
    FunctionTool = None
    Runner = None
    agents_trace = None


class AriaOrchestrator:
    def __init__(self, google, client: OpenAI | None = None):
        self.google = google
        self.client = client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.memory = StructuredMemoryStore(google)
        self.tools = ToolExecutor(google, self.memory)
        self.skills = SkillRegistry(self.memory, self.tools.drive, campaign_store=google)

    async def process_message(self, chat_id: str, user_message: str, media_context: MessageContext | None = None) -> str:
        selection = select_workflow(user_message)
        recorder = TraceRecorder(chat_id=chat_id, workflow=selection.name)
        recorder.add("workflow_selected", reasons=selection.reasons)
        if media_context and media_context.has_content:
            recorder.add("media_context_received", attachments=len(media_context.attachments))

        await self.google.save_to_history(chat_id, "usuario", user_message)

        skill_response = await self.skills.handle(chat_id, user_message)
        if skill_response:
            await self.google.save_to_history(chat_id, "aria", skill_response)
            recorder.add("skill_handled")
            recorder.finish("ok", skill_response)
            return skill_response

        captured_memory_note = ""
        if selection.needs_memory_capture:
            category = memory_category_for_text(user_message)
            record = await self.memory.capture_user_correction(user_message, category)
            captured_memory_note = f"Memoria actualizada antes de responder: {record.to_model_text()}"
            recorder.add("memory_auto_captured", memory_id=record.id, category=record.category)

        history_items, relevant_memories = await asyncio.gather(
            self.google.get_historial(chat_id, limit=16),
            self.memory.search(user_message, limit=8),
        )

        messages = self._build_messages(
            user_message=user_message,
            media_context=media_context,
            history_items=history_items,
            memory_items=relevant_memories,
            workflow_name=selection.name,
            captured_memory_note=captured_memory_note,
        )

        trace_ctx = (
            agents_trace("Aria 2 Telegram turn", group_id=chat_id, metadata={"workflow": selection.name})
            if agents_trace
            else nullcontext()
        )

        try:
            with trace_ctx:
                if self._can_use_agents_sdk():
                    final_text = await self._run_agents_sdk(messages, selection.name, recorder)
                else:
                    final_text = await self._run_llm_loop(messages, recorder)
        except Exception as exc:
            recorder.add("error", error=str(exc))
            final_text = "Algo fue mal procesando tu mensaje. Lo he registrado para corregirlo."

        await self.google.save_to_history(chat_id, "aria", final_text)
        recorder.finish("ok", final_text)
        return final_text

    async def generate_daily_summary(self) -> str:
        now = datetime.now(MADRID_TZ)
        dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
        prompt = (
            f"Hoy es {dias[now.weekday()]} {now.strftime('%d/%m/%Y')}. "
            "Genera el resumen matutino de Domingo. Revisa agenda de hoy y proximos 3 dias, "
            "tareas urgentes o proximas a vencer, y pagos o deudas que vencen pronto. "
            "Se directa, practica y termina con una frase motivadora breve."
        )
        return await self.process_message("daily_summary", prompt)

    def _build_messages(
        self,
        user_message: str,
        media_context: MessageContext | None,
        history_items: list[dict],
        memory_items,
        workflow_name: str,
        captured_memory_note: str,
    ) -> list[dict]:
        now_madrid = datetime.now(MADRID_TZ).strftime("%A %d/%m/%Y %H:%M")
        system_content = (
            f"{BASE_SYSTEM_PROMPT}\n"
            f"Fecha y hora actual en Madrid: {now_madrid}\n"
            f"{WORKFLOW_PROMPTS.get(workflow_name, WORKFLOW_PROMPTS['general'])}\n"
            "Cuando una herramienta devuelva approval_required, no intentes rodearlo: pide confirmacion explicita.\n"
        )

        if captured_memory_note:
            system_content += f"\n{captured_memory_note}\n"

        if memory_items:
            memory_text = "\n\n".join(record.to_model_text() for record in memory_items)
            system_content += f"\n{MEMORY_CONTEXT_HEADER}:\n{memory_text}\n"

        enriched_user_message = user_message
        if media_context and media_context.has_content:
            enriched_user_message = f"{user_message}\n\nCONTEXTO MULTIMEDIA:\n{media_context.to_prompt_text()}"

        messages = [{"role": "system", "content": system_content}]
        for item in history_items:
            role = "assistant" if item.get("rol") == "aria" else "user"
            content = item.get("mensaje", "")
            if content and content != user_message:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": enriched_user_message})
        return messages

    def _can_use_agents_sdk(self) -> bool:
        if os.getenv("ARIA_DISABLE_AGENTS_SDK", "").strip() == "1":
            return False
        return Agent is not None and FunctionTool is not None and Runner is not None

    async def _run_agents_sdk(self, messages: list[dict], workflow_name: str, recorder: TraceRecorder) -> str:
        system_content = str(messages[0]["content"])
        agent_input = self._messages_to_transcript(messages[1:])
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        recorder.add("agents_sdk_run", workflow=workflow_name, model=model)

        agent = Agent(
            name=f"ARIA_{workflow_name}",
            model=model,
            instructions=system_content,
            tools=self._agents_sdk_tools(),
        )
        result = await Runner.run(agent, input=agent_input, max_turns=10)
        return str(result.final_output or "")

    def _agents_sdk_tools(self) -> list:
        sdk_tools = []
        for schema in tool_schemas():
            fn = schema["function"]
            name = fn["name"]
            description = fn["description"]
            params_json_schema = fn["parameters"]

            async def invoke_tool(ctx, args: str, tool_name=name) -> str:
                try:
                    parsed = json.loads(args or "{}")
                except json.JSONDecodeError:
                    parsed = {}
                return await self.tools.execute(tool_name, parsed)

            sdk_tools.append(
                FunctionTool(
                    name=name,
                    description=description,
                    params_json_schema=params_json_schema,
                    on_invoke_tool=invoke_tool,
                )
            )
        return sdk_tools

    def _messages_to_transcript(self, messages: list[dict]) -> str:
        lines: list[str] = []
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content") or ""
            if role == "tool":
                role = "tool_result"
            lines.append(f"{role.upper()}: {content}")
        return "\n\n".join(lines)

    async def _run_llm_loop(self, messages: list[dict], recorder: TraceRecorder) -> str:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        for step in range(10):
            recorder.add("llm_step", step=step, model=model)
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model=model,
                messages=messages,
                tools=tool_schemas(),
                tool_choice="auto",
                max_tokens=4096,
            )
            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            if finish_reason == "stop":
                return msg.content or ""

            if finish_reason == "tool_calls" and msg.tool_calls:
                messages.append(
                    {
                        "role": "assistant",
                        "content": msg.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                            }
                            for tc in msg.tool_calls
                        ],
                    }
                )
                for tool_call in msg.tool_calls:
                    try:
                        tool_input = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        tool_input = {}
                    recorder.add("tool_call", name=tool_call.function.name)
                    result = await self.tools.execute(tool_call.function.name, tool_input)
                    messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
                continue

            break

        return "No pude cerrar la respuesta con fiabilidad. Intentalo de nuevo con una instruccion mas concreta."
