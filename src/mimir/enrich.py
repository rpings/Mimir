"""AI processing — DeepSeek with type-specific prompts."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from litellm import completion

from mimir.config import LLMConfig
from mimir.models import EnrichedEntry, EntryType, RawEntry
from mimir.prompts import PROMPTS
from mimir.taxonomy import topic_ids

log = logging.getLogger(__name__)

ALL_TOPIC_IDS = topic_ids()


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if len(lines) >= 2:
            end = -1 if lines[-1].startswith("```") else None
            text = "\n".join(lines[1:end])
    return text.strip()


def _parse_response(raw: str) -> dict[str, Any]:
    text = _strip_fences(raw)
    if not text:
        raise ValueError("empty response")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError(f"no JSON in response: {text[:120]}") from None
        return json.loads(match.group(0))


def _validate(data: dict[str, Any], entry_type: EntryType) -> dict[str, Any]:
    topic = str(data.get("topic", "")).strip()
    if topic not in ALL_TOPIC_IDS:
        topic = "industry"

    result: dict[str, Any] = {
        "topic": topic,
        "priority": _valid_priority(data.get("priority", "medium")),
    }

    if entry_type == EntryType.PAPER:
        result["overview"] = str(data.get("overview", "")).strip()[:300]
        result["innovation"] = str(data.get("innovation", "")).strip()[:300]
        result["significance"] = str(data.get("significance", "")).strip()[:200]
    elif entry_type == EntryType.REPO:
        result["use_case"] = str(data.get("use_case", "")).strip()[:300]
    elif entry_type == EntryType.NEWS:
        result["key_point"] = str(data.get("key_point", "")).strip()[:200]
        result["verification"] = _valid_verification(data.get("verification", "unverified"))

    return result


def _valid_priority(p: Any) -> str:
    p = str(p).strip().lower()
    return p if p in ("high", "medium", "low") else "medium"


def _valid_venue(v: Any) -> str:
    valid = {"arXiv", "NeurIPS", "ICML", "ICLR", "CVPR", "ACL", "Other"}
    v = str(v).strip()
    return v if v in valid else "Other"


def _valid_verification(v: Any) -> str:
    valid = {"verified", "unverified", "rumor"}
    v = str(v).strip().lower()
    return v if v in valid else "unverified"


def _entry_body(entry: RawEntry) -> str:
    parts = [f"Title: {entry.title}"]
    if entry.summary:
        parts.append(f"Summary: {entry.summary[:800]}")
    return "\n".join(parts)


class Enricher:
    """Process entries through DeepSeek with type-specific prompts."""

    def __init__(self, cfg: LLMConfig):
        self._cfg = cfg

    def _completion_kwargs(self, entry_type: EntryType, body: str) -> dict[str, Any]:
        system_prompt = PROMPTS[entry_type]
        params: dict[str, Any] = {
            "model": f"{self._cfg.provider}/{self._cfg.model}",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": body},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "api_key": self._cfg.api_key,
        }
        if self._cfg.base_url:
            params["api_base"] = self._cfg.base_url
        return params

    def _call(self, entry_type: EntryType, body: str) -> dict[str, Any]:
        params = self._completion_kwargs(entry_type, body)
        try:
            response = completion(**params)
        except Exception as exc:
            if "response_format" in str(exc).lower():
                params.pop("response_format", None)
                response = completion(**params)
            else:
                raise
        content = response.choices[0].message.content or ""
        return _validate(_parse_response(content), entry_type)

    async def process(self, entry: RawEntry) -> EnrichedEntry:
        body = _entry_body(entry)
        result = await asyncio.to_thread(self._call, entry.entry_type, body)
        log.debug("processed: %s → [%s]", entry.title[:40], result["topic"])
        # Source-provided data (not from LLM)
        authors = entry.extra.get("authors", "")
        venue = "arXiv" if entry.source.startswith("arxiv") else ""
        stars = entry.extra.get("stars", 0)

        return EnrichedEntry(
            title=entry.title, link=entry.link, summary=entry.summary,
            published=entry.published, source=entry.source,
            entry_type=entry.entry_type,
            topic=result["topic"], priority=result["priority"],
            overview=result.get("overview", ""),
            innovation=result.get("innovation", ""),
            significance=result.get("significance", ""),
            authors=authors,
            venue=venue,
            use_case=result.get("use_case", ""),
            stars=stars,
            key_point=result.get("key_point", ""),
            verification=result.get("verification", ""),
        )

    async def process_all(
        self, entries: list[RawEntry], *, concurrency: int = 3,
    ) -> list[EnrichedEntry]:
        sem = asyncio.Semaphore(concurrency)
        out: list[EnrichedEntry] = []

        async def _one(entry: RawEntry) -> None:
            async with sem:
                try:
                    result = await self.process(entry)
                    out.append(result)
                except Exception as exc:
                    log.warning("enrich failed for %s: %s", entry.link[:60], exc)
                    out.append(EnrichedEntry(
                        title=entry.title, link=entry.link, summary=entry.summary,
                        published=entry.published, source=entry.source,
                        entry_type=entry.entry_type, topic="industry",
                        priority="medium",
                    ))

        await asyncio.gather(*(_one(e) for e in entries))
        return out
