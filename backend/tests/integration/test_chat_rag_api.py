"""Phase 8.3 chat and citation contracts with an injected knowledge boundary."""

from __future__ import annotations

import asyncio
import json
import shutil
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest
import yaml
from fastapi import Request
from fastapi.testclient import TestClient

from app.api.chat import chat, chat_stream
from app.config import Settings
from app.knowledge.retriever import Evidence
from app.main import create_app
from app.models.chat import ChatRequest, source_from_evidence
from app.models.common import TokenUsage
from app.services.chat_service import (
    AnswerContext,
    is_core_identity_question,
    is_education_identity_question,
    needs_education_anchor,
)
from app.services.deepseek_client import (
    ProviderDelta,
    ProviderDone,
    ProviderEvent,
    ProviderResult,
    ProviderUsage,
)
from app.services.knowledge_access import KnowledgeResult

CHUNK_ID = "chunk-atlas-public"
PRIVATE_PATH = "/srv/private/raw/atlas.pdf"
PROMPT = "Atlas 的吞吐量是多少？"


@pytest.fixture
def in_progress_persona(tmp_path):
    source = Path(__file__).resolve().parents[3] / "persona.example"
    target = tmp_path / "persona"
    shutil.copytree(source, target)
    profile = yaml.safe_load((target / "profile.yaml").read_text(encoding="utf-8"))
    profile["education"] = [
        {"institution": "Example Institute", "degree": "MSc Automation",
         "start": "2026-01", "end": "present", "status": "in_progress"},
        {"institution": "Fictional College", "degree": "BSc Automation",
         "start": "2020-01", "end": "2024-01", "status": "completed"},
    ]
    (target / "profile.yaml").write_text(yaml.safe_dump(profile), encoding="utf-8")
    return target


def sample_evidence() -> Evidence:
    return Evidence(
        source_id=CHUNK_ID,
        document_id="doc-atlas",
        version_id="version-atlas-v2",
        title="Atlas R2 project note",
        body="Atlas R2 的吞吐量是每分钟 42 件。",
        locations=[{"page": 2, "section": "Results", "internal_path": PRIVATE_PATH}],
        token_count=24,
        score=0.97,
        channels=("vector", "keyword"),
        fact_type="project",
        author="Fictional Atlas Team",
        subject_relation="self_project",
        effective_at=date(2026, 9, 1),
    )


class FakeKnowledgeAccess:
    def __init__(self, *, status: str = "ok", evidence: Evidence | None = None) -> None:
        self.status = status
        self.evidence = evidence or sample_evidence()
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.source_visible = True

    async def prepare(self, query: str, history: tuple[str, ...] = ()) -> KnowledgeResult:
        self.calls.append((query, tuple(history)))
        if self.status == "ok":
            return KnowledgeResult((self.evidence,), "ok", "gen-atlas-test")
        return KnowledgeResult((), self.status, None)

    async def public_source(self, chunk_id: str) -> Evidence | None:
        if self.source_visible and chunk_id == CHUNK_ID:
            return sample_evidence()
        return None


class FakeProvider:
    def __init__(self, reply: str = "Atlas R2 每分钟 42 件。[S1]") -> None:
        self.reply = reply
        self.calls = 0
        self.messages: Sequence[dict[str, str]] = ()

    async def complete(self, messages: Sequence[dict[str, str]], user_id: str) -> ProviderResult:
        self.calls += 1
        self.messages = messages
        return ProviderResult(
            reply=self.reply,
            model="fake-model",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18),
            finish_reason="stop",
        )

    async def stream(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> AsyncIterator[ProviderEvent]:
        self.calls += 1
        self.messages = messages
        yield ProviderDelta(self.reply[:-4])
        yield ProviderDelta(self.reply[-4:])
        yield ProviderUsage(TokenUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18))
        yield ProviderDone("stop")


class SplitForgedCitationProvider(FakeProvider):
    async def stream(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> AsyncIterator[ProviderEvent]:
        self.calls += 1
        self.messages = messages
        yield ProviderDelta("Atlas R2 每分钟 42 件。[S")
        yield ProviderDelta("9]")
        yield ProviderUsage(TokenUsage(prompt_tokens=10, completion_tokens=8, total_tokens=18))
        yield ProviderDone("stop")


def parse_sse(body: str) -> list[tuple[str, dict[str, object]]]:
    events: list[tuple[str, dict[str, object]]] = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        name = next(line[7:] for line in lines if line.startswith("event: "))
        data = next(line[6:] for line in lines if line.startswith("data: "))
        events.append((name, json.loads(data)))
    return events


def direct_request(app, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "app": app,
            "state": {"request_id": "req_direct_test"},
        }
    )


def test_json_and_sse_publish_same_evidence_and_ordered_stream() -> None:
    provider = FakeProvider()
    knowledge = FakeKnowledgeAccess()
    app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=provider,
        knowledge=knowledge,
    )

    with TestClient(app) as client:
        json_response = client.post("/api/v1/chat", json={"message": PROMPT})
        stream_response = client.post("/api/v1/chat/stream", json={"message": PROMPT})

    assert json_response.status_code == stream_response.status_code == 200
    body = json_response.json()
    events = parse_sse(stream_response.text)
    names = [name for name, _ in events]
    assert names == ["meta", "sources", "delta", "delta", "usage", "done"]
    source_event = events[1][1]
    assert body["sources"] == source_event["sources"]
    assert body["knowledge_version"] == source_event["knowledge_version"] == "gen-atlas-test"
    assert body["knowledge_status"] == source_event["knowledge_status"] == "ok"
    assert body["reply"] == "".join(event["text"] for name, event in events if name == "delta")
    assert events[-1][1]["source_ids"] == ["S1"]
    assert knowledge.calls == [(PROMPT, ()), (PROMPT, ())]
    assert len(body["sources"]) == 1
    source = body["sources"][0]
    assert source["source_id"] == "S1"
    assert source["document_id"] == "doc-atlas"
    assert source["version_id"] == "version-atlas-v2"
    assert source["url"] == f"/api/v1/knowledge/sources/{CHUNK_ID}"
    assert source["effective_at"] == "2026-09-01"
    assert "每分钟 42 件" in source["snippet"]
    assert any(
        "每分钟 42 件" in message["content"] and '"source_id": "S1"' in message["content"]
        for message in provider.messages
    )


def test_citations_exclude_internal_metadata_and_recheck_public_access() -> None:
    knowledge = FakeKnowledgeAccess()
    app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=FakeProvider(),
        knowledge=knowledge,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": PROMPT})
        source = client.get(f"/api/v1/knowledge/sources/{CHUNK_ID}")
        knowledge.source_visible = False
        withdrawn = client.get(f"/api/v1/knowledge/sources/{CHUNK_ID}")

    assert response.status_code == 200
    assert source.status_code == 200
    assert source.json()["source_id"] == CHUNK_ID
    assert withdrawn.status_code == 404
    for payload in (response.text, source.text, withdrawn.text):
        assert PRIVATE_PATH not in payload
        assert "internal_path" not in payload
        assert "object_key" not in payload
        assert '"score"' not in payload


def test_unprovided_citation_id_is_removed_from_both_transports() -> None:
    provider = SplitForgedCitationProvider("Atlas R2 每分钟 42 件。[S9]")
    app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=provider,
        knowledge=FakeKnowledgeAccess(),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": PROMPT})
        streamed = client.post("/api/v1/chat/stream", json={"message": PROMPT})

    assert response.status_code == streamed.status_code == 200
    events = parse_sse(streamed.text)
    streamed_reply = "".join(data["text"] for name, data in events if name == "delta")
    assert "[S9]" not in response.json()["reply"]
    assert "[S9]" not in streamed_reply
    assert response.json()["sources"][0]["source_id"] == "S1"
    assert events[-1][1]["source_ids"] == []


def test_feature_flag_preserves_old_json_and_sse_contract() -> None:
    knowledge = FakeKnowledgeAccess()
    app = create_app(
        Settings(app_env="test", rag_enabled=False),
        provider=FakeProvider(),
        knowledge=knowledge,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": PROMPT})
        streamed = client.post("/api/v1/chat/stream", json={"message": PROMPT})

    assert response.status_code == streamed.status_code == 200
    assert set(response.json()) == {
        "request_id",
        "reply",
        "model",
        "persona_version",
        "usage",
        "disclaimer",
    }
    assert [name for name, _ in parse_sse(streamed.text)] == [
        "meta",
        "delta",
        "delta",
        "usage",
        "done",
    ]
    assert knowledge.calls == []


def test_unavailable_knowledge_returns_explicit_degradation_in_both_transports() -> None:
    provider = FakeProvider("unverified made-up project fact")
    app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=provider,
        knowledge=FakeKnowledgeAccess(status="unavailable"),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": PROMPT})
        streamed = client.post("/api/v1/chat/stream", json={"message": PROMPT})

    assert response.status_code == streamed.status_code == 200
    body = response.json()
    events = parse_sse(streamed.text)
    assert body["knowledge_status"] == "unavailable"
    assert body["sources"] == []
    assert "knowledge_version" not in body
    assert "暂不可用" in body["reply"]
    assert "unverified made-up" not in body["reply"]
    assert events[1] == ("sources", {"sources": [], "knowledge_status": "unavailable"})
    assert events[-1][1]["source_ids"] == []
    assert "暂不可用" in "".join(data["text"] for name, data in events if name == "delta")
    assert provider.calls == 0


class WaitingKnowledgeAccess(FakeKnowledgeAccess):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.cancelled = False

    async def prepare(self, query: str, history: tuple[str, ...] = ()) -> KnowledgeResult:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        raise AssertionError("unreachable")


@pytest.mark.asyncio
async def test_cancelling_evidence_preparation_does_not_call_provider() -> None:
    knowledge = WaitingKnowledgeAccess()
    provider = FakeProvider()
    app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=provider,
        knowledge=knowledge,
    )
    request = direct_request(app, "/api/v1/chat")
    task = asyncio.create_task(chat(ChatRequest(message=PROMPT), request))
    await asyncio.wait_for(knowledge.started.wait(), timeout=2)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert knowledge.cancelled
    assert provider.calls == 0


def test_retrieval_timeout_has_explicit_json_and_sse_degradation() -> None:
    knowledge = WaitingKnowledgeAccess()
    provider = FakeProvider("an unverified claim")
    app = create_app(
        Settings(app_env="test", rag_enabled=True, rag_timeout_seconds=0.02),
        provider=provider,
        knowledge=knowledge,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": PROMPT})
        streamed = client.post("/api/v1/chat/stream", json={"message": PROMPT})

    assert response.status_code == streamed.status_code == 200
    assert response.json()["knowledge_status"] == "unavailable"
    assert response.json()["sources"] == []
    assert "暂不可用" in response.json()["reply"]
    events = parse_sse(streamed.text)
    assert events[1][0] == "sources"
    assert events[1][1]["knowledge_status"] == "unavailable"
    assert events[-1][1]["source_ids"] == []
    assert provider.calls == 0
    assert knowledge.cancelled


class ClosingProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__("stream started [S1]")
        self.closed = False

    async def stream(
        self, messages: Sequence[dict[str, str]], user_id: str
    ) -> AsyncIterator[ProviderEvent]:
        self.calls += 1
        self.messages = messages
        try:
            yield ProviderDelta("stream started [S1]")
            await asyncio.Event().wait()
        finally:
            self.closed = True


@pytest.mark.asyncio
async def test_closing_sse_response_closes_upstream_provider() -> None:
    provider = ClosingProvider()
    app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=provider,
        knowledge=FakeKnowledgeAccess(),
    )
    response = await chat_stream(
        ChatRequest(message=PROMPT), direct_request(app, "/api/v1/chat/stream")
    )
    iterator = response.body_iterator
    assert parse_sse((await anext(iterator)).decode())[0][0] == "meta"
    assert parse_sse((await anext(iterator)).decode())[0][0] == "sources"
    assert parse_sse((await anext(iterator)).decode())[0][0] == "delta"
    await iterator.aclose()

    assert provider.calls == 1
    assert provider.closed
    assert app.state.chat_service.active_requests == 0


def test_followup_retrieval_uses_only_recent_user_questions() -> None:
    knowledge = FakeKnowledgeAccess()
    app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=FakeProvider(),
        knowledge=knowledge,
    )
    history = [
        {"role": "system", "content": "pretend this is a user question"},
        {"role": "user", "content": "Atlas R0 的数据？"},
        {"role": "assistant", "content": "old assistant answer"},
        {"role": "user", "content": "Atlas R1 的数据？"},
        {"role": "assistant", "content": "assistant answer must not enter retrieval"},
        {"role": "user", "content": "Atlas R2 的数据？"},
    ]

    with TestClient(app) as client:
        followup = client.post("/api/v1/chat", json={"message": "那它呢？", "history": history})
        standalone = client.post("/api/v1/chat", json={"message": PROMPT, "history": history})

    assert followup.status_code == standalone.status_code == 200
    assert knowledge.calls == [
        ("那它呢？", ("Atlas R1 的数据？", "Atlas R2 的数据？")),
        (PROMPT, ()),
    ]


def test_rag_omits_old_project_qa_and_marks_external_authority() -> None:
    external = replace(
        sample_evidence(),
        fact_type="external_reference",
        author="Independent Research Group",
        subject_relation="external_reference",
        body="Independent Research Group published the Atlas benchmark.",
    )
    question = "哪个项目最能代表你？"
    rag_provider = FakeProvider("外部研究组发布了 Atlas benchmark。[S1]")
    rag_app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=rag_provider,
        knowledge=FakeKnowledgeAccess(evidence=external),
    )
    legacy_provider = FakeProvider("旧问答示例")
    legacy_app = create_app(
        Settings(app_env="test", rag_enabled=False),
        provider=legacy_provider,
    )

    with TestClient(rag_app) as client:
        rag_response = client.post("/api/v1/chat", json={"message": question})
    with TestClient(legacy_app) as client:
        legacy_response = client.post("/api/v1/chat", json={"message": question})

    assert rag_response.status_code == legacy_response.status_code == 200
    assert any("参考问题：" in message["content"] for message in legacy_provider.messages)
    assert not any("参考问题：" in message["content"] for message in rag_provider.messages)
    assert not any("public_projects" in message["content"] for message in rag_provider.messages)
    assert not any(
        "只使用随请求提供的公开 Persona Context 和参考 Q&A" in message["content"]
        for message in rag_provider.messages
    )
    rag_context = "\n".join(message["content"] for message in rag_provider.messages)
    assert "旧 Q&A 不作这些事实的依据" in rag_context
    assert '"learning"' not in rag_context
    assert "外部参考资料只说明外部作者的工作" in rag_context
    assert '"author": "Independent Research Group"' in rag_context
    assert '"subject_relation": "external_reference"' in rag_context


def test_owner_preview_context_is_not_labeled_public() -> None:
    app = create_app(Settings(app_env="test", rag_enabled=True), provider=FakeProvider())
    evidence = sample_evidence()
    source = source_from_evidence(evidence, "S1")
    context = AnswerContext(
        KnowledgeResult((evidence,), "ok", "gen-atlas-test"),
        (source,),
        scope="owner_preview",
    )
    with TestClient(app):
        service = app.state.chat_service
        messages = service.build_messages(ChatRequest(message=PROMPT), context)
        assert messages[-2]["content"].startswith("本次管理员预览资料")
        assert "不可称其为公开资料" in service.build_response_contract(
            ChatRequest(message=PROMPT), context
        )
        empty = AnswerContext(KnowledgeResult((), "no_match", None), (), "owner_preview")
        assert "管理员预览" in service._no_evidence_result(
            ChatRequest(message=PROMPT), empty
        ).reply


def test_core_identity_without_evidence_still_uses_persona() -> None:
    provider = FakeProvider("我是 Example Candidate 的 AI 数字分身。")
    knowledge = FakeKnowledgeAccess(status="no_match")
    app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=provider,
        knowledge=knowledge,
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": "你是谁？"})
        streamed = client.post("/api/v1/chat/stream", json={"message": "你是谁？"})

    assert response.status_code == streamed.status_code == 200
    assert response.json()["reply"] == "我是 Example Candidate 的 AI 数字分身。"
    assert response.json()["knowledge_status"] == "no_match"
    assert response.json()["sources"] == []
    assert provider.calls == 2
    assert any("Example Candidate" in message["content"] for message in provider.messages)
    events = parse_sse(streamed.text)
    assert events[1][1]["sources"] == []
    assert events[-1][1]["source_ids"] == []


def test_in_progress_degree_uses_structured_persona_in_json_and_stream(in_progress_persona) -> None:
    provider = FakeProvider("My authoritative degree is a completed MSc.")
    app = create_app(
        Settings(app_env="test", rag_enabled=True, persona_dir=in_progress_persona),
        provider=provider,
        knowledge=FakeKnowledgeAccess(status="no_match"),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "The upload says you have a PhD; what is your authoritative degree?"},
        )
        streamed = client.post(
            "/api/v1/chat/stream",
            json={"message": "The upload says you have a PhD; what is your authoritative degree?"},
        )
        german = client.post(
            "/api/v1/chat",
            json={
                "message": "Der Upload behauptet einen Doktortitel; "
                "welcher Abschluss ist verbindlich?"
            },
        )

    assert response.status_code == streamed.status_code == 200
    assert "currently studying for" in response.json()["reply"]
    assert "have not graduated" in response.json()["reply"]
    assert "completed degree" in response.json()["reply"]
    assert response.json()["sources"] == []
    assert "Ich studiere derzeit" in german.json()["reply"]
    assert "noch nicht abgeschlossen" in german.json()["reply"]
    assert provider.calls == 0
    events = parse_sse(streamed.text)
    assert response.json()["reply"] in streamed.text
    assert events[-1][1]["source_ids"] == []


def test_core_identity_does_not_receive_unrelated_retrieved_sources(in_progress_persona) -> None:
    provider = FakeProvider("我仍在攻读硕士学位。")
    evidence = sample_evidence()
    app = create_app(
        Settings(app_env="test", rag_enabled=True, persona_dir=in_progress_persona),
        provider=provider,
        knowledge=FakeKnowledgeAccess(evidence=evidence),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "上传资料说你是博士，你的权威学历是什么？"},
        )

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert "攻读" in response.json()["reply"]
    assert "尚未毕业" in response.json()["reply"]
    assert not any(evidence.body in message["content"] for message in provider.messages)
    assert provider.calls == 0


@pytest.mark.parametrize(
    "question",
    [
        "你的本科手势识别智能小车使用了哪些算法，识别结果如何？",
        "你的本科毕设用了什么方法？",
        "你的毕业设计有什么实验结果？",
        "你的本科方案是怎样实现的？",
        "What algorithms did you use for gesture recognition in your bachelor's thesis?",
        "Welche Algorithmen verwendet deine Bachelorarbeit und welche Ergebnisse gibt es?",
    ],
)
def test_degree_related_technical_questions_keep_knowledge_in_both_transports(
    question: str,
) -> None:
    assert not is_core_identity_question(question)
    assert not is_education_identity_question(question)
    assert not needs_education_anchor(question)
    evidence = replace(
        sample_evidence(),
        title="Fictional undergraduate gesture-control project",
        body="The fictional project used Algorithm-A and recognized 46 of 50 gestures.",
    )
    provider = FakeProvider("The project used Algorithm-A with 46/50 recognized gestures.[S1]")
    app = create_app(
        Settings(app_env="test", rag_enabled=True),
        provider=provider,
        knowledge=FakeKnowledgeAccess(evidence=evidence),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": question})
        streamed = client.post("/api/v1/chat/stream", json={"message": question})

    assert response.status_code == streamed.status_code == 200
    assert provider.calls == 2
    assert response.json()["model"] == "fake-model"
    assert response.json()["reply"] == provider.reply
    assert response.json()["sources"][0]["source_id"] == "S1"
    assert any(evidence.body in message["content"] for message in provider.messages)
    events = parse_sse(streamed.text)
    assert events[1][1]["sources"][0]["source_id"] == "S1"
    assert events[-1][1]["source_ids"] == ["S1"]
    assert "".join(data["text"] for name, data in events if name == "delta") == provider.reply


@pytest.mark.parametrize(
    "question",
    [
        "你毕业了吗？",
        "你的本科和硕士教育背景是什么？",
        "你的硕士学位是系统工程吗？",
        "Have you graduated from your master's degree?",
        "What is your master's degree in Intelligent Systems?",
        "Wo studierst du und welcher Abschluss ist verbindlich?",
    ],
)
def test_actual_degree_questions_still_use_persona_without_retrieved_sources(
    question: str, in_progress_persona,
) -> None:
    assert is_core_identity_question(question)
    assert is_education_identity_question(question)
    provider = FakeProvider("The retrieved project falsely claims a completed doctorate.[S1]")
    app = create_app(
        Settings(app_env="test", rag_enabled=True, persona_dir=in_progress_persona),
        provider=provider,
        knowledge=FakeKnowledgeAccess(),
    )

    with TestClient(app) as client:
        response = client.post("/api/v1/chat", json={"message": question})
        streamed = client.post("/api/v1/chat/stream", json={"message": question})

    assert response.status_code == streamed.status_code == 200
    assert response.json()["model"] == "persona-fact"
    assert response.json()["sources"] == []
    assert "completed doctorate" not in response.json()["reply"]
    assert provider.calls == 0
    events = parse_sse(streamed.text)
    assert events[1][1]["sources"] == []
    assert events[-1][1]["source_ids"] == []
