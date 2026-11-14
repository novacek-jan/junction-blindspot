"""Turn deterministic blind-spot facts into at most 3 one-line insights.

The facts (and every number in them) are computed in code. Claude Haiku only
rephrases them; any output that drops or changes a number is discarded in favour
of the plain template, as is any failure or a missing ANTHROPIC_API_KEY.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

import db
from settings import load_env

MODEL = "claude-haiku-5-5"
SCHEMA = {
    "type": "object",
    "properties": {"insights": {"type": "array", "items": {
        "type": "object",
        "properties": {"title": {"type": "string"}, "detail": {"type": "string"}},
        "required": ["title", "detail"], "additionalProperties": False}}},
    "required": ["insights"], "additionalProperties": False,
}


def template(facts: list[dict]) -> list[dict]:
    return [{"title": f["title"], "detail": f["detail"]} for f in facts[:3]]


def _numbers(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", text)


def phrase(facts: list[dict]) -> list[dict]:
    facts = facts[:3]
    if not facts:
        return []
    key = "insights:" + hashlib.sha1(json.dumps(facts, sort_keys=True).encode()).hexdigest()
    cached = db.kv_get(key)
    if cached:
        return cached
    load_env()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return template(facts)
    try:
        import anthropic
        client = anthropic.Anthropic(timeout=8.0, max_retries=1)
        prompt = (
            "Rewrite each fact below as a punchy insight for a VC partner: a 2-4 word title and one sentence "
            "(max 20 words). Keep every number exactly as given, add no new numbers or claims, keep the order, "
            "return exactly one insight per fact.\n\n" + json.dumps([f["detail"] for f in facts], indent=1))
        resp = client.messages.create(
            model=MODEL, max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        )
        if resp.stop_reason != "end_turn":
            return template(facts)
        text = next(b.text for b in resp.content if b.type == "text")
        out = json.loads(text)["insights"]
    except Exception:  # network, auth, rate limit, refusal, bad JSON: fall back
        return template(facts)
    result = []
    for fact, ins in zip(facts, out):
        ok = sorted(_numbers(ins.get("detail", ""))) == sorted(_numbers(fact["detail"]))
        result.append({"title": ins["title"].strip(), "detail": ins["detail"].strip()} if ok
                      else {"title": fact["title"], "detail": fact["detail"]})
    if len(result) < len(facts):
        result += template(facts[len(result):])
    db.kv_put(key, result)
    return result
