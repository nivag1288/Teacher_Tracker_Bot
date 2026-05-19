import json
import re
from analysis.llm_provider import LLMProvider

_PROMPT_TEMPLATE = """Analyze the following Discord chat transcript and return ONLY a JSON object with this exact structure (no extra text before or after):

{{
  "topics": ["topic1", "topic2", "topic3"],
  "sentiment": "positive",
  "key_themes": ["theme1", "theme2"],
  "summary": "One paragraph summary of the conversation."
}}

Rules:
- "sentiment" must be exactly one of: "positive", "neutral", "negative"
- "topics" should be 2-5 short phrases describing what was discussed
- "key_themes" should be 2-4 broader themes
- "summary" should be one paragraph, 2-4 sentences

Transcript:
{transcript}"""


def _build_prompt(transcript: str) -> str:
    return _PROMPT_TEMPLATE.format(transcript=transcript[:12000])


def _parse_response(raw: str) -> dict:
    """Extract JSON from LLM output; return degraded result on failure."""
    # Try to find a JSON object in the response
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            data = json.loads(match.group())
            return {
                "topics": data.get("topics", []),
                "sentiment": data.get("sentiment", "neutral")
                    if data.get("sentiment") in ("positive", "neutral", "negative")
                    else "neutral",
                "key_themes": data.get("key_themes", []),
                "summary": data.get("summary", ""),
            }
        except (json.JSONDecodeError, ValueError):
            pass

    # Degraded fallback
    return {
        "topics": [],
        "sentiment": "neutral",
        "key_themes": [],
        "summary": raw.strip()[:1000] if raw.strip() else "Analysis could not be parsed.",
    }


class SemanticAnalyzer:
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def analyze(self, transcript_text: str) -> dict:
        """Send transcript to LLM and return structured analysis dict."""
        if not transcript_text.strip():
            return {
                "topics": [],
                "sentiment": "neutral",
                "key_themes": [],
                "summary": "No messages in transcript.",
            }
        prompt = _build_prompt(transcript_text)
        raw = await self.provider.generate(prompt)
        return _parse_response(raw)
