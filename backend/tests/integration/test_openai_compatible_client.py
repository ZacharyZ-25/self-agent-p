from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.config import Settings
from app.services.openai_compatible_client import OpenAICompatibleClient


def completion_body() -> dict[str, object]:
    return {
        "id": "chatcmpl_local_test",
        "object": "chat.completion",
        "created": 1,
        "model": "local-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "LOCAL_OK"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
    }


@pytest.mark.asyncio
@respx.mock
async def test_local_provider_uses_llama_thinking_contract() -> None:
    route = respx.post("http://local.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=completion_body())
    )
    settings = Settings(
        app_env="test",
        llm_provider="local",
        llm_base_url="http://local.test/v1",
        llm_model="local-model",
        llm_thinking_enabled=False,
        llm_max_retries=0,
    )
    client = OpenAICompatibleClient.from_settings(settings)
    try:
        result = await client.complete([{"role": "user", "content": "hello"}], "session")
    finally:
        await client.close()

    assert result.reply == "LOCAL_OK"
    assert result.usage.total_tokens == 5
    request_body = json.loads(route.calls[0].request.content)
    assert request_body["model"] == "local-model"
    assert request_body["chat_template_kwargs"] == {"enable_thinking": False}
    assert "thinking" not in request_body


@pytest.mark.asyncio
@respx.mock
async def test_remote_llama_cpp_provider_uses_auth_and_the_qwen_template_contract() -> None:
    route = respx.post("https://model.example.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=completion_body())
    )
    settings = Settings(
        app_env="test",
        llm_provider="llama_cpp",
        llm_api_key="test-only-key",
        llm_base_url="https://model.example.com/v1",
        llm_model="local-model",
        llm_thinking_enabled=False,
        llm_max_retries=0,
    )
    client = OpenAICompatibleClient.from_settings(settings)
    try:
        result = await client.complete([{"role": "user", "content": "hello"}], "session")
    finally:
        await client.close()

    assert result.reply == "LOCAL_OK"
    request = route.calls[0].request
    request_body = json.loads(request.content)
    assert request.headers["Authorization"] == "Bearer test-only-key"
    assert request_body["chat_template_kwargs"] == {"enable_thinking": False}
