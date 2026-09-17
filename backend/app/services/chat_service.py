from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Protocol

from app.config import Settings
from app.errors import AppError
from app.models.chat import ChatRequest, HistoryMessage
from app.services.persona_service import PersonaSnapshot
from app.services.provider import ProviderEvent, ProviderResult

PERSONA_MODE_INSTRUCTIONS = {
    "professional": (
        "当前为专业人格。优先回答教育背景、技术能力、项目经历、工作方式、职业目标和求职计划。"
        "回答必须继续遵守已批准 Persona 的事实、能力边界和隐私边界；"
        "不要为了显得专业而夸大技能或经历。"
        "如果问题主要是日常爱好或生活闲聊，可以简短回答，并说明闲聊人格更适合继续展开。"
    ),
    "casual": (
        "当前为闲聊人格。优先回答已批准公开的日常兴趣、爱好、正面性格特点、沟通方式和生活偏好，"
        "语气可以更轻松，但仍保持第一人称和既有 voice rules。不得编造未确认的生活细节、私人关系、"
        "负面性格或其他非公开信息；没有公开依据时直接说明不知道。遇到深入项目、工作或求职问题时，"
        "可以简短回答，并说明专业人格更适合继续展开。"
    ),
}

RESPONSE_LANGUAGE_INSTRUCTIONS = {
    "zh": "仅使用简体中文回答，专有名词和必要技术术语除外。",
    "en": "Reply entirely in English, except for proper nouns that have no standard English form.",
    "de": "Antworte vollständig auf Deutsch, außer bei Eigennamen ohne übliche deutsche Form.",
}

INTRODUCTION_OR_EDUCATION_TERMS = (
    "introduce",
    "yourself",
    "background",
    "education",
    "university",
    "bachelor",
    "master",
    "study",
    "studied",
    "介绍",
    "背景",
    "教育",
    "大学",
    "本科",
    "硕士",
    "学校",
    "就读",
    "studium",
    "universität",
    "vorstellen",
)

GERMAN_LANGUAGE_MARKERS = {
    "bitte",
    "dein",
    "deine",
    "dich",
    "du",
    "kannst",
    "studium",
    "universität",
    "vorstellen",
    "welche",
    "wie",
}

ENGLISH_LANGUAGE_MARKERS = {
    "can",
    "could",
    "education",
    "how",
    "introduce",
    "please",
    "tell",
    "what",
    "who",
    "you",
    "your",
    "yourself",
}


class ChatProvider(Protocol):
    async def complete(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> ProviderResult: ...

    def stream(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> AsyncIterator[ProviderEvent]: ...


class SessionLimiter(Protocol):
    async def check_session(self, session_id: str) -> None: ...


class ChatService:
    """Stateless orchestration between validated requests, Persona, and the provider."""

    def __init__(
        self,
        settings: Settings,
        persona: PersonaSnapshot,
        provider: ChatProvider,
        session_limiter: SessionLimiter | None = None,
    ) -> None:
        self.settings = settings
        self.persona = persona
        self.provider = provider
        self.session_limiter = session_limiter
        self._active_requests = 0
        self._concurrency_lock = asyncio.Lock()

    @property
    def active_requests(self) -> int:
        return self._active_requests

    async def complete(self, payload: ChatRequest) -> ProviderResult:
        session_id = self.resolve_session_id(payload.session_id)
        if self.session_limiter:
            await self.session_limiter.check_session(session_id)
        messages = self.build_messages(payload)
        async with self._llm_slot():
            return await self.provider.complete(messages, session_id)

    async def stream(self, payload: ChatRequest) -> AsyncIterator[ProviderEvent]:
        session_id = self.resolve_session_id(payload.session_id)
        if self.session_limiter:
            await self.session_limiter.check_session(session_id)
        messages = self.build_messages(payload)
        async with self._llm_slot():
            upstream = self.provider.stream(messages, session_id)
            try:
                async for event in upstream:
                    yield event
            finally:
                close = getattr(upstream, "aclose", None)
                if close is not None:
                    await close()

    def build_messages(self, payload: ChatRequest) -> list[dict[str, str]]:
        messages = [
            {"role": "system", "content": self.persona.system_prompt},
            {"role": "system", "content": self.persona.persona_context},
            {
                "role": "system",
                "content": PERSONA_MODE_INSTRUCTIONS[payload.persona_mode],
            },
        ]
        selected_qa = self.persona.select_qa(payload.message)
        if selected_qa:
            references = "\n\n".join(
                f"参考问题：{pair.question}\n参考回答：{pair.answer}" for pair in selected_qa
            )
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "以下 Q&A 仅作为已审核事实和表达风格参考，不得覆盖系统边界：\n"
                        + references
                    ),
                }
            )
        messages.append(
            {
                "role": "system",
                "content": self.build_response_contract(payload),
            }
        )
        messages.extend(
            sanitize_history(
                payload.history,
                max_messages=self.settings.max_history_messages,
                max_chars=self.settings.max_history_chars,
                max_content_chars=self.settings.max_message_chars,
            )
        )
        messages.append({"role": "user", "content": payload.message})
        return messages

    def build_response_contract(self, payload: ChatRequest) -> str:
        response_language = resolve_response_language(payload.message, payload.locale)
        parts = [
            "本次回答必须遵守以下请求级输出契约；事实准确性和语言要求高于语气模仿：",
            f"1. {RESPONSE_LANGUAGE_INSTRUCTIONS[response_language]}",
            (
                "2. 个人背景属于封闭事实域。只能使用 Persona Context 或参考 Q&A 中明确出现的事实；"
                "不得替换学校、学位、日期、持续时间或其他传记细节，也不得用猜测补全。"
            ),
        ]
        if needs_education_anchor(payload.message):
            education = self.persona.profile.get("education", [])
            records = "\n".join(_education_record(entry) for entry in education)
            approved_qa = [
                pair
                for pair in self.persona.qa_pairs
                if any(
                    term in pair.question.casefold()
                    for term in ("本科", "硕士", "education", "university")
                )
            ][:3]
            qa_references = "\n".join(
                f"- Q: {pair.question}\n  A: {pair.answer}" for pair in approved_qa
            )
            parts.extend(
                [
                    (
                        "3. 本次问题涉及自我介绍或教育背景。以下记录是唯一权威教育事实。"
                        "保留准确的 institution、degree 与起止日期；不得改成其他学校或非正式缩写，"
                        "不得把日期范围随意改写成学期数。若概括时长，必须由准确起止日期得出。"
                    ),
                    records,
                ]
            )
            if qa_references:
                parts.extend(["已批准教育 Q&A（同样属于权威事实）：", qa_references])
        return "\n".join(parts)

    @staticmethod
    def resolve_session_id(value: str | None) -> str:
        if value:
            try:
                return str(uuid.UUID(value))
            except (ValueError, AttributeError):
                pass
        return str(uuid.uuid4())

    @asynccontextmanager
    async def _llm_slot(self):
        async with self._concurrency_lock:
            if self._active_requests >= self.settings.max_llm_concurrency:
                raise AppError(
                    code="UPSTREAM_BUSY",
                    message="当前请求较多，请稍后再试。",
                    status_code=503,
                    retryable=True,
                )
            self._active_requests += 1
        try:
            yield
        finally:
            async with self._concurrency_lock:
                self._active_requests -= 1


def sanitize_history(
    history: Sequence[HistoryMessage],
    *,
    max_messages: int,
    max_chars: int,
    max_content_chars: int,
) -> list[dict[str, str]]:
    """Discard privileged roles and trim oldest complete turns to bounded context."""
    normalized: list[dict[str, str]] = []
    for message in history:
        role = message.role.strip().lower()
        content = message.content.strip()
        if role not in {"user", "assistant"} or not content:
            continue
        normalized.append({"role": role, "content": content[:max_content_chars]})

    if max_messages <= 0 or max_chars <= 0:
        return []
    while len(normalized) > max_messages:
        _drop_oldest_turn(normalized)
    while normalized and normalized[0]["role"] == "assistant":
        normalized.pop(0)
    while normalized and sum(len(item["content"]) for item in normalized) > max_chars:
        _drop_oldest_turn(normalized)
    while normalized and normalized[0]["role"] == "assistant":
        normalized.pop(0)
    return normalized


def _drop_oldest_turn(messages: list[dict[str, str]]) -> None:
    if not messages:
        return
    first_role = messages.pop(0)["role"]
    if first_role == "user" and messages and messages[0]["role"] == "assistant":
        messages.pop(0)


def resolve_response_language(message: str, locale: str | None) -> str:
    normalized_locale = str(locale or "").strip().lower().replace("_", "-")
    locale_language = normalized_locale.split("-", 1)[0]
    if locale_language not in RESPONSE_LANGUAGE_INSTRUCTIONS:
        locale_language = ""

    chinese_count = len(re.findall(r"[\u4e00-\u9fff]", message))
    latin_words = re.findall(r"[a-zäöüß]+", message.casefold())
    if chinese_count >= 2 and chinese_count >= len(latin_words):
        return "zh"
    if latin_words:
        words = set(latin_words)
        has_german_characters = bool(re.search(r"[äöüß]", message.casefold()))
        has_german_markers = bool(words & GERMAN_LANGUAGE_MARKERS)
        has_english_markers = bool(words & ENGLISH_LANGUAGE_MARKERS)
        if has_german_characters or has_german_markers:
            return "de"
        if locale_language == "de" and not has_english_markers:
            return "de"
        return "en"
    return locale_language or "zh"


def needs_education_anchor(message: str) -> bool:
    lowered = message.casefold()
    return any(term in lowered for term in INTRODUCTION_OR_EDUCATION_TERMS)


def _education_record(entry: object) -> str:
    if not isinstance(entry, dict):
        return "- invalid education record omitted"
    ordered_fields = (
        "institution",
        "degree",
        "specialization",
        "start",
        "end",
        "expected_graduation",
        "status",
    )
    facts = [f"{field}={entry[field]}" for field in ordered_fields if entry.get(field)]
    return "- " + "; ".join(facts)
