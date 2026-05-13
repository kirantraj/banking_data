"""
Base Agent

All agents inherit from BaseAgent which:
  • Lazily initialises the Vertex AI Gemini client.
  • Sends a prompt and parses the guaranteed-JSON response.
  • Returns a deterministic mock dict when USE_MOCK_DATA=true.

Design rule: agents contain ONLY reasoning logic.
They must never call BigQuery or read files directly —
that belongs to the MCP tools layer.
"""
import json
import os
import sys
from abc import ABC, abstractmethod
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings
from utils.logger import get_logger


class BaseAgent(ABC):
    """
    Thin wrapper around Vertex AI Gemini.

    Subclasses must implement _mock_response() so the full pipeline
    can be exercised locally without GCP credentials.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.logger = get_logger(f"agents.{agent_name}")
        self._model = None  # initialised on first use

    # ── Public API ────────────────────────────────────────────────────────────

    def generate(self, prompt: str, temperature: float = 0.1) -> dict[str, Any]:
        """
        Send a prompt to Gemini and return the parsed JSON response.

        Uses response_mime_type="application/json" so Gemini is constrained
        to emit valid JSON — no need to strip markdown fences.

        Falls back to _mock_response() in mock mode.
        """
        if settings.use_mock_data:
            self.logger.debug("Mock mode — using deterministic response")
            return self._mock_response(prompt)

        model = self._get_model()

        try:
            from vertexai.generative_models import GenerationConfig

            response = model.generate_content(
                prompt,
                generation_config=GenerationConfig(
                    temperature=temperature,
                    response_mime_type="application/json",
                ),
            )
            text = response.text.strip()
            parsed = json.loads(text)
            self.logger.debug(f"LLM response: {str(parsed)[:200]}")
            return parsed

        except json.JSONDecodeError as exc:
            self.logger.error(f"LLM returned non-JSON: {exc}\nRaw text: {text[:400]}")
            return {"error": f"LLM returned invalid JSON: {exc}", "raw": text}
        except Exception as exc:
            self.logger.error(f"Gemini API error: {exc}")
            return {"error": str(exc)}

    # ── Abstract ──────────────────────────────────────────────────────────────

    @abstractmethod
    def _mock_response(self, prompt: str) -> dict[str, Any]:
        """Return a deterministic response for local testing without Gemini."""
        ...

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get_model(self):
        """Lazily initialise Gemini to avoid import overhead at startup."""
        if self._model is None:
            import vertexai
            from vertexai.generative_models import GenerativeModel

            vertexai.init(project=settings.project_id, location=settings.location)
            self._model = GenerativeModel(settings.model_name)
            self.logger.info(f"Gemini model ready: {settings.model_name}")
        return self._model
