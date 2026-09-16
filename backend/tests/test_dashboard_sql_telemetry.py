import asyncio
import json
from types import SimpleNamespace

import httpx
from openai import AsyncOpenAI

from apps.dashboard.crud.ai_sql_generator import _async_invoke_llm_json
from apps.dashboard.crud.sql_generation_lifecycle import current_generation_run, run_sql_generation


def test_records_actual_openai_retry_separately_from_generation_round():
    async def scenario():
        attempts = []

        async def respond(request):
            attempts.append(request.headers.get("x-stainless-retry-count"))
            if len(attempts) == 1:
                return httpx.Response(500, json={"error": {"message": "temporary"}})
            return httpx.Response(200, json={"id": "test", "object": "chat.completion", "created": 0,
                "model": "test", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": json.dumps({"success": True, "sql": "SELECT 1"})}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            root = AsyncOpenAI(api_key="test", base_url="https://example.test/v1", max_retries=1, http_client=client)

            class Model:
                root_async_client = root

                async def ainvoke(self, messages):
                    result = await root.chat.completions.create(model="test", messages=[{"role": "user", "content": "test"}])
                    return SimpleNamespace(content=result.choices[0].message.content)

            async def generate():
                response = await _async_invoke_llm_json(Model(), [], node="test_generate")
                return response, current_generation_run()

            result, run = await run_sql_generation(generate())
            assert result.success
            assert run.llm_calls == 1
            assert run.http_attempts == 2
            assert run.network_retries == 1
            assert attempts == ["0", "1"]

    asyncio.run(scenario())


def test_sync_only_model_counts_once_in_async_path():
    class Model:
        def invoke(self, messages):
            return SimpleNamespace(content='{"success":true,"sql":"SELECT 1"}')

    async def generate():
        await _async_invoke_llm_json(Model(), [])
        return current_generation_run()

    run = asyncio.run(run_sql_generation(generate()))
    assert run.llm_calls == 1
