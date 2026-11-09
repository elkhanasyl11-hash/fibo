"""Grounded operator and dashboard assistants with a code-only fallback."""

import re
import uuid
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from fibo_ai.assistant.repository import DataRepository, FakeRepository
from fibo_ai.assistant.tools import (
    ReadOnlyTools,
    ToolResult,
    date_range,
    numbers_are_verified,
    select_tool,
)
from fibo_ai.core.errors import ModelNotReadyError
from fibo_ai.core.i18n import get_stop_line
from fibo_ai.core.llm.base import LLMClient
from fibo_ai.core.llm.fake import FakeLLM
from fibo_ai.rag.service import RAGService
from fibo_ai.safety.rules import get_safety_engine
from fibo_ai.schemas.assistant import (
    DashboardChatRequest,
    DashboardChatResponse,
    MachineAggregate,
    OperatorChatRequest,
    OperatorChatResponse,
    RiskRow,
)
from fibo_ai.schemas.common import Lang, Usage
from fibo_ai.schemas.rag import ManualQueryRequest
from fibo_ai.settings import Settings


class OperatorDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reply: str = Field(max_length=1200)
    manual_pages: list[int] = Field(default_factory=list, max_length=5)


class DashboardDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(max_length=1200)


UNSAFE = re.compile(
    r"keep\s+running|continue\s+working|можно\s+работать|продолжайте\s+работать|"
    r"жұмысты\s+жалғастыр|ignore\s+(?:all\s+)?previous\s+instructions",
    re.IGNORECASE,
)
NUMBER = re.compile(r"(?<!\w)\d[\d,]*(?:\.\d+)?%?")


class AssistantService:
    def __init__(
        self,
        settings: Settings,
        repo: DataRepository | None = None,
        llm: LLMClient | None = None,
        rag: RAGService | None = None,
    ) -> None:
        self.settings = settings
        self.repo = repo if repo is not None else (FakeRepository() if settings.ai_stub_mode else None)
        self._fake_repo = repo is None and settings.ai_stub_mode
        self.llm = llm
        self.rag = rag
        self.tools = ReadOnlyTools(self.repo) if self.repo is not None else None

    def _prompt(self, name: str, lang: Lang) -> str:
        path = Path("prompts") / lang.value / f"{name}_v1_0.txt"
        return path.read_text(encoding="utf-8") if path.exists() else "Use only the supplied evidence."

    @staticmethod
    def _operator_fallback(lang: Lang, page: int | None = None) -> str:
        if lang == Lang.kk:
            return (
                f"Нұсқаулықтың {page}-бетін қараңыз; расталған үзінділерден қысқа жауап құрастыру мүмкін болмады."
                if page
                else "Бұл станок нұсқаулығында жауап табылмады. Механикке хабарласыңыз."
            )
        if lang == Lang.en:
            return (
                f"See manual page {page}; a verified short answer could not be composed."
                if page
                else "The answer was not found in this machine's manual. Contact a mechanic."
            )
        return (
            f"См. страницу {page} руководства; не удалось составить проверенный краткий ответ."
            if page
            else "В руководстве этого станка ответ не найден. Обратитесь к механику."
        )

    async def operator_chat(self, req: OperatorChatRequest) -> OperatorChatResponse:
        request_id = f"asst-op-{uuid.uuid4().hex[:8]}"
        safety = get_safety_engine().evaluate(req.question)
        if safety.force_stop:
            reply = get_stop_line(req.lang)
            return OperatorChatResponse(
                request_id=request_id,
                model_version=self.settings.model_version,
                config_version=self.settings.config_version,
                reply=reply,
                safety_applied=True,
                usage=Usage(),
            )

        degraded: list[str] = []
        fragments = []
        if self.rag:
            try:
                result = await self.rag.query_manual(
                    ManualQueryRequest(machine_id=req.machine_id, query=req.question, top_k=5)
                )
                fragments = result.fragments
            except Exception as exc:
                degraded.append(f"operator_rag_unavailable:{type(exc).__name__}")
        pages = sorted({fragment.page for fragment in fragments})
        reply = self._operator_fallback(req.lang, pages[0] if pages else None)
        cited_pages: list[int] = [pages[0]] if pages else []
        usage = Usage()
        if fragments and self.llm and not isinstance(self.llm, FakeLLM):
            excerpts = "\n".join(
                f'<untrusted_manual_page page="{fragment.page}">{fragment.snippet}</untrusted_manual_page>'
                for fragment in fragments
            )
            prompt = (
                f"{self._prompt('operator_chat', req.lang)}\nMachine ID={req.machine_id}. "
                f"<untrusted_question>{req.question[:1000]}</untrusted_question>\n{excerpts}\n"
                f"Citable pages only: {pages}. Return concise safe advice, without unsupported numbers."
            )
            try:
                draft, usage = await self.llm.generate_json(prompt, OperatorDraft, temperature=0.0, timeout_s=10.0)
                text_pages = {
                    int(number) for number in re.findall(r"(?:с\.|стр\.|p\.|page)\s*(\d+)", draft.reply, re.I)
                }
                allowed = set(pages)
                allowed_numbers = {str(page) for page in pages}
                allowed_numbers.update(
                    value.replace(",", "") for fragment in fragments for value in NUMBER.findall(fragment.snippet)
                )
                answer_numbers = {value.replace(",", "") for value in NUMBER.findall(draft.reply)}
                numbers_verified = all(value.rstrip("%") in allowed_numbers for value in answer_numbers)
                if set(draft.manual_pages) <= allowed and text_pages <= allowed and numbers_verified:
                    if not UNSAFE.search(draft.reply):
                        reply = draft.reply
                        cited_pages = sorted(set(draft.manual_pages) | text_pages)
                    else:
                        degraded.append("operator_answer_safety_fallback")
                else:
                    degraded.append("operator_citation_or_number_verification_fallback")
            except Exception as exc:
                degraded.append(f"operator_llm_fallback:{type(exc).__name__}")
        if UNSAFE.search(reply):
            reply = self._operator_fallback(req.lang, pages[0] if pages else None)
            cited_pages = [pages[0]] if pages else []
        post_safety = get_safety_engine().evaluate(reply)
        safety_applied = safety.force_stop or post_safety.force_stop
        if post_safety.force_stop:
            reply = get_stop_line(req.lang)
            cited_pages = []
        return OperatorChatResponse(
            request_id=request_id,
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            reply=reply,
            manual_pages=cited_pages,
            safety_applied=safety_applied,
            degraded=degraded + (["fake_repository_synthetic_demo_data"] if self._fake_repo else []),
            usage=usage,
        )

    @staticmethod
    def _dashboard_table(result: ToolResult, lang: Lang) -> tuple[str, list[str]]:
        refs: list[str] = []
        if result.tool_name == "top_machines":
            headers = {
                Lang.ru: ("Станок", "Инцидентов", "Простой (ч)", "Убыток (KZT)"),
                Lang.kk: ("Станок", "Оқиға", "Тоқтау (сағ)", "Шығын (KZT)"),
                Lang.en: ("Machine", "Incidents", "Downtime (h)", "Loss (KZT)"),
            }[lang]
            lines = [f"| {' | '.join(headers)} |", "|---|---:|---:|---:|"]
            for row in result.rows:
                if isinstance(row, MachineAggregate):
                    lines.append(
                        f"| {row.machine_name} | {row.incidents_count} | {row.downtime_hours:g} | {row.loss_kzt:,} |"
                    )
                    refs.append(row.machine_id)
            return "\n".join(lines), refs
        if result.tool_name == "get_risk_ranking":
            labels = {
                Lang.ru: ("Станок", "Индекс риска", "Приоритет (KZT)"),
                Lang.kk: ("Станок", "Тәуекел индексі", "Басымдық (KZT)"),
                Lang.en: ("Machine", "Risk index", "Priority (KZT)"),
            }[lang]
            lines = [f"| {' | '.join(labels)} |", "|---|---:|---:|"]
            for row in result.rows:
                if isinstance(row, RiskRow):
                    lines.append(f"| {row.machine_name} | {row.risk_index:g} | {row.priority_kzt:,} |")
                    refs.append(row.machine_id)
            return "\n".join(lines), refs
        lines = ["| ID | Станок / запись | Значения |", "|---|---|---|"]
        for row in result.rows:
            dump = row.model_dump()
            identifier = str(dump.get("id", dump.get("machine_id", "")))
            values = "; ".join(f"{key}: {value}" for key, value in dump.items() if key not in {"id", "machine_id"})
            lines.append(
                f"| {identifier} | {dump.get('machine_name', dump.get('name', dump.get('machine_id', '')))} | {values} |"
            )
            refs.append(identifier)
        return "\n".join(lines), refs

    @staticmethod
    def _dashboard_fallback(result: ToolResult, lang: Lang) -> str:
        if not result.rows:
            return {
                Lang.kk: "Таңдалған аралықта деректер табылмады.",
                Lang.en: "No records were found for the selected period.",
                Lang.ru: "За выбранный период записей не найдено.",
            }[lang]
        first = result.rows[0]
        if isinstance(first, MachineAggregate):
            if lang == Lang.kk:
                return f"Ең жоғары көрсеткіш: {first.machine_name}; оқиғалар: {first.incidents_count}, тоқтау: {first.downtime_hours:g} сағ, шығын: {first.loss_kzt:,} KZT."
            if lang == Lang.en:
                return f"Highest result: {first.machine_name}; incidents: {first.incidents_count}, downtime: {first.downtime_hours:g} h, loss: {first.loss_kzt:,} KZT."
            return f"Наибольший показатель у **{first.machine_name}**: {first.incidents_count} инцидентов, простой {first.downtime_hours:g} ч, убыток {first.loss_kzt:,} KZT."
        if isinstance(first, RiskRow):
            return f"{first.machine_name}: риск {first.risk_index:g}, приоритет {first.priority_kzt:,} KZT."
        return f"Получены данные инструмента `{result.tool_name}`; таблица содержит строки с источниками."

    async def dashboard_chat(self, req: DashboardChatRequest) -> DashboardChatResponse:
        if self.tools is None:
            raise ModelNotReadyError(
                "Inject the backend's read-only DataRepository when constructing FiboAI for dashboard queries"
            )
        since, until = date_range(req.query)
        tool_name, argument = select_tool(req.query)
        result = await self.tools.execute(
            tool_name,
            workshop_id=req.workshop_id,
            since=since,
            until=until,
            argument=argument,
            limit=5,
        )
        table, refs = self._dashboard_table(result, req.lang)
        answer = self._dashboard_fallback(result, req.lang)
        usage = Usage()
        degraded: list[str] = []
        if self.llm and not isinstance(self.llm, FakeLLM) and result.rows:
            prompt = (
                f"{self._prompt('dashboard_agent', req.lang)}\nQuestion=<untrusted>{req.query[:1000]}</untrusted>\n"
                f"Read-only tool `{result.tool_name}` returned these records: "
                f"<untrusted_tool_result>{[row.model_dump() for row in result.rows]}</untrusted_tool_result>\n"
                "Summarize briefly. Use only numbers present in tool records. Do not invent facts."
            )
            try:
                draft, usage = await self.llm.generate_json(prompt, DashboardDraft, temperature=0.0, timeout_s=10.0)
                if numbers_are_verified(draft.summary, result):
                    answer = draft.summary
                else:
                    degraded.append("dashboard_number_verification_fallback")
            except Exception as exc:
                degraded.append(f"dashboard_llm_fallback:{type(exc).__name__}")
        return DashboardChatResponse(
            request_id=f"asst-db-{uuid.uuid4().hex[:8]}",
            model_version=self.settings.model_version,
            config_version=self.settings.config_version,
            answer_markdown=answer,
            table_markdown=table,
            data_refs=refs,
            tools_called=[result.tool_name],
            degraded=degraded + (["fake_repository_synthetic_demo_data"] if self._fake_repo else []),
            usage=usage,
        )
