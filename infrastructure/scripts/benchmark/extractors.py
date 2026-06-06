#!/usr/bin/env python3
"""
extractors.py - Provider-agnostic bell-schedule extractors for the benchmark.

One interface, swappable backends: local Ollama OR a cloud API (Anthropic, Gemini, OpenAI).
All providers reuse ExtractionService's system/user prompt, JSON parsing, time normalization,
and validation — only the model call (`_complete`) differs. This keeps the benchmark a fair
apples-to-apples comparison and lets the same code path serve production.

Model spec format: "provider:model"
    ollama:qwen2.5vl:7b        gemini:gemini-2.5-flash-lite
    anthropic:claude-haiku-4-5 openai:gpt-4o-mini
(no prefix -> ollama, for backward compatibility)

Cloud SDKs/keys are resolved lazily; a provider only needs to work when actually selected.
Vision: pass image paths to `extract(..., images=[...])`; providers that support vision use them.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from infrastructure.api.services.extraction_service import (
    ExtractionService, ExtractionResult, ExtractedSchedule,
)

MAX_TEXT_LEN = 12000  # raised from production's 6000 (schedules can be spread across files)


class BaseExtractor:
    """Shared parse/normalize/validate; subclasses implement `_complete`."""

    provider = "base"
    supports_vision = False

    def __init__(self, model: str):
        self.model = model
        self._svc = ExtractionService(model=model)  # reused for prompt + parsing helpers

    def _complete(self, system: str, user: str, images: list[str] | None = None) -> str:
        raise NotImplementedError

    def extract(self, text: str, district_id: str, district_name: str, state: str,
                images: list[str] | None = None) -> dict:
        svc = self._svc
        result = ExtractionResult(
            district_id=district_id, district_name=district_name, state=state,
            extraction_date=__import__("datetime").datetime.utcnow().isoformat(),
            extractor=f"{self.provider}:{self.model}",
        )
        if text and len(text) > MAX_TEXT_LEN:
            text = text[: int(MAX_TEXT_LEN * 0.7)] + "\n...[truncated]...\n" + text[-int(MAX_TEXT_LEN * 0.3):]
        user = svc.USER_PROMPT_TEMPLATE.format(
            district_name=district_name, state=state, pdf_text=text or "(see attached images)")
        try:
            content = self._complete(svc.SYSTEM_PROMPT, user, images=images)
            result.raw_response = content
            data = svc._extract_json_from_response(content)
            if not data:
                result.success = False; result.error = "Could not parse JSON response"; return result.to_dict()
            if data.get("error"):
                result.success = False; result.error = data["error"]; return result.to_dict()
            for item in data.get("schedules", []):
                start = svc._normalize_time(item.get("start_time", ""))
                end = svc._normalize_time(item.get("end_time", ""))
                if not start or not end:
                    continue
                result.schedules.append(ExtractedSchedule(
                    grade_level=item.get("grade_level", "unknown"),
                    start_time=start, end_time=end,
                    school_name=item.get("school_name"),
                    confidence=item.get("confidence", "medium"),
                    raw_text_snippet=item.get("raw_text_snippet", ""),
                    notes=item.get("notes", ""),
                ))
            if not result.schedules:
                result.success = False; result.error = "No valid schedules extracted"
            else:
                result = svc._validate_and_enhance_extraction(result)
        except Exception as e:  # noqa: BLE001 - surface as a scored failure
            result.success = False; result.error = f"{type(e).__name__}: {e}"
        return result.to_dict()


def _img_b64(path: str) -> tuple[str, str]:
    data = base64.standard_b64encode(Path(path).read_bytes()).decode()
    ext = Path(path).suffix.lower().lstrip(".")
    media = {"jpg": "jpeg", "tif": "tiff"}.get(ext, ext)
    return data, f"image/{media}"


class OllamaExtractor(BaseExtractor):
    provider = "ollama"
    supports_vision = True  # vision used only if the model is a VLM; harmless otherwise

    def _complete(self, system, user, images=None):
        import ollama
        from infrastructure.api.services.ollama_launcher import ensure_ollama_running
        ensure_ollama_running()
        user_msg = {"role": "user", "content": user}
        if images:
            user_msg["images"] = images  # Ollama accepts file paths for VLMs
        resp = ollama.chat(
            model=self.model,
            messages=[{"role": "system", "content": system}, user_msg],
            options={"temperature": 0.1, "num_predict": 1200},
        )
        return resp.get("message", {}).get("content", "")


class AnthropicExtractor(BaseExtractor):
    provider = "anthropic"
    supports_vision = True

    def _complete(self, system, user, images=None):
        import anthropic  # lazy; needs `pip install anthropic` + ANTHROPIC_API_KEY
        client = anthropic.Anthropic()
        content: list[dict] = [{"type": "text", "text": user}]
        for img in (images or []):
            data, media = _img_b64(img)
            content.append({"type": "image", "source": {"type": "base64", "media_type": media, "data": data}})
        msg = client.messages.create(
            model=self.model, max_tokens=1500, system=system,
            messages=[{"role": "user", "content": content}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


class GeminiExtractor(BaseExtractor):
    provider = "gemini"
    supports_vision = True

    def _complete(self, system, user, images=None):
        import google.generativeai as genai  # present in this env
        genai.configure(api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        model = genai.GenerativeModel(self.model, system_instruction=system)
        parts: list = [user]
        for img in (images or []):
            data, media = _img_b64(img)
            parts.append({"mime_type": media, "data": base64.b64decode(data)})
        resp = model.generate_content(parts, generation_config={"temperature": 0.1})
        return resp.text or ""


class OpenAIExtractor(BaseExtractor):
    provider = "openai"
    supports_vision = True

    def _complete(self, system, user, images=None):
        import openai  # lazy; needs `pip install openai` + OPENAI_API_KEY
        client = openai.OpenAI()
        content: list[dict] = [{"type": "text", "text": user}]
        for img in (images or []):
            data, media = _img_b64(img)
            content.append({"type": "image_url",
                            "image_url": {"url": f"data:{media};base64,{data}"}})
        resp = client.chat.completions.create(
            model=self.model, temperature=0.1, max_tokens=1500,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": content}],
        )
        return resp.choices[0].message.content or ""


_PROVIDERS = {
    "ollama": OllamaExtractor, "anthropic": AnthropicExtractor,
    "gemini": GeminiExtractor, "openai": OpenAIExtractor,
}


def make_extractor(spec: str) -> BaseExtractor:
    """Parse 'provider:model' (default provider=ollama) -> Extractor instance."""
    if ":" in spec and spec.split(":", 1)[0] in _PROVIDERS:
        provider, model = spec.split(":", 1)
    else:
        provider, model = "ollama", spec
    return _PROVIDERS[provider](model)
