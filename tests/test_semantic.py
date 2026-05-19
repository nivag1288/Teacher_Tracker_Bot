import pytest
import respx
import httpx
from unittest.mock import AsyncMock

from analysis.llm_provider import OllamaProvider
from analysis.semantic import SemanticAnalyzer, _parse_response


# ── OllamaProvider ────────────────────────────────────────────────────────────

@respx.mock
async def test_ollama_provider_calls_generate_endpoint():
    route = respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"response": "hello"})
    )
    provider = OllamaProvider(host="localhost:11434", model="llama3.2")
    result = await provider.generate("test prompt")
    assert route.called
    assert result == "hello"


@respx.mock
async def test_ollama_provider_sends_model_and_prompt():
    route = respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(200, json={"response": "ok"})
    )
    provider = OllamaProvider(host="localhost:11434", model="llama3.2")
    await provider.generate("my prompt")
    body = route.calls[0].request.content
    import json
    payload = json.loads(body)
    assert payload["model"] == "llama3.2"
    assert payload["prompt"] == "my prompt"
    assert payload["stream"] is False


@respx.mock
async def test_ollama_provider_raises_on_http_error():
    respx.post("http://localhost:11434/api/generate").mock(
        return_value=httpx.Response(500)
    )
    provider = OllamaProvider(host="localhost:11434", model="llama3.2")
    with pytest.raises(httpx.HTTPStatusError):
        await provider.generate("prompt")


@respx.mock
async def test_ollama_ping_returns_true_on_200():
    respx.get("http://localhost:11434/api/tags").mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    provider = OllamaProvider(host="localhost:11434", model="llama3.2")
    assert await provider.ping() is True


@respx.mock
async def test_ollama_ping_returns_false_on_error():
    respx.get("http://localhost:11434/api/tags").mock(side_effect=httpx.ConnectError("down"))
    provider = OllamaProvider(host="localhost:11434", model="llama3.2")
    assert await provider.ping() is False


# ── _parse_response ───────────────────────────────────────────────────────────

def test_parse_response_valid_json():
    raw = '{"topics": ["gaming", "meta"], "sentiment": "positive", "key_themes": ["fun"], "summary": "Nice chat."}'
    result = _parse_response(raw)
    assert result["topics"] == ["gaming", "meta"]
    assert result["sentiment"] == "positive"
    assert result["summary"] == "Nice chat."


def test_parse_response_json_embedded_in_text():
    raw = 'Here is the analysis:\n{"topics": ["x"], "sentiment": "neutral", "key_themes": [], "summary": "ok."}\nDone.'
    result = _parse_response(raw)
    assert result["topics"] == ["x"]
    assert result["sentiment"] == "neutral"


def test_parse_response_invalid_sentiment_defaults_neutral():
    raw = '{"topics": [], "sentiment": "very positive", "key_themes": [], "summary": "s."}'
    result = _parse_response(raw)
    assert result["sentiment"] == "neutral"


def test_parse_response_no_json_returns_degraded():
    result = _parse_response("I cannot analyze this.")
    assert result["sentiment"] == "neutral"
    assert result["topics"] == []
    assert "I cannot analyze" in result["summary"]


def test_parse_response_empty_string():
    result = _parse_response("")
    assert result["sentiment"] == "neutral"
    assert result["summary"] == "Analysis could not be parsed."


def test_parse_response_all_fields_present():
    raw = '{"topics": ["a"], "sentiment": "negative", "key_themes": ["b"], "summary": "s."}'
    result = _parse_response(raw)
    assert set(result.keys()) == {"topics", "sentiment", "key_themes", "summary"}


# ── SemanticAnalyzer ──────────────────────────────────────────────────────────

async def test_analyzer_calls_provider():
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = (
        '{"topics": ["testing"], "sentiment": "positive", "key_themes": ["qa"], "summary": "Tests passed."}'
    )
    analyzer = SemanticAnalyzer(mock_provider)
    result = await analyzer.analyze("Alice: hello\nBob: world")
    mock_provider.generate.assert_called_once()
    assert result["sentiment"] == "positive"
    assert result["topics"] == ["testing"]


async def test_analyzer_empty_transcript_skips_llm():
    mock_provider = AsyncMock()
    analyzer = SemanticAnalyzer(mock_provider)
    result = await analyzer.analyze("   ")
    mock_provider.generate.assert_not_called()
    assert result["summary"] == "No messages in transcript."


async def test_analyzer_returns_structured_dict():
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = (
        '{"topics": ["a", "b"], "sentiment": "neutral", "key_themes": ["c"], "summary": "Test."}'
    )
    analyzer = SemanticAnalyzer(mock_provider)
    result = await analyzer.analyze("some content")
    assert "topics" in result
    assert "sentiment" in result
    assert "key_themes" in result
    assert "summary" in result


async def test_analyzer_handles_bad_llm_response():
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "This is not JSON at all."
    analyzer = SemanticAnalyzer(mock_provider)
    result = await analyzer.analyze("content")
    assert result["sentiment"] == "neutral"
    assert isinstance(result["topics"], list)
