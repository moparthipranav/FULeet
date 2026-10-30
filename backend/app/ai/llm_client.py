import json
from typing import Dict, List, Optional
import httpx

from app.config import settings
from app.ai.state_machine import AgentTurnOutput


class LLMClient:
    def __init__(
        self,
        api_key: Optional[str] = getattr(settings, "OPENAI_API_KEY", None),
        base_url: str = getattr(settings, "LLM_BASE_URL", "https://api.openai.com/v1"),
        model: str = getattr(settings, "LLM_MODEL", "gpt-4o"),
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def generate_turn(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
    ) -> AgentTurnOutput:
        """Sends the structured prompt to the LLM and parses the response into the AgentTurnOutput."""
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY must be configured to use the interview agent")

        payload = {
            "model": self.model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                *messages,
            ]
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )

            if resp.status_code != 200:
                print(f"\n[OPENAI ERROR {resp.status_code}]:", resp.text)
            resp.raise_for_status()
            data = resp.json()
            

        raw_content = data["choices"][0]["message"]["content"]
        parsed_json = json.loads(raw_content)

        return AgentTurnOutput(**parsed_json)