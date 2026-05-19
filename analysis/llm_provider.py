from abc import ABC, abstractmethod
import httpx


class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str) -> str:
        ...


class OllamaProvider(LLMProvider):
    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        self.model = model

    async def generate(self, prompt: str) -> str:
        url = f"http://{self.host}/api/generate"
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                url,
                json={"model": self.model, "prompt": prompt, "stream": False},
            )
            r.raise_for_status()
            return r.json()["response"]

    async def ping(self) -> bool:
        """Return True if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"http://{self.host}/api/tags")
                return r.status_code == 200
        except Exception:
            return False
