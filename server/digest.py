"""
Weekly digest: once a week, the local AI reads the week's history and
writes a short, plain-language digest with ranked suggestions -- Ask
Matrix for the whole week, instead of one question at a time.

Free (it's the same local model, through Ollama) and only runs if Ollama is
up. Matrix checks roughly every hour whether 7 days have passed since the
last digest, and can also be asked to write one right away.
"""

import time
from datetime import datetime

import ai
import paths
import persona

DIGEST_SECONDS = 7 * 86400

SYSTEM_PROMPT = "You write short, plain-language weekly summaries of one person's Windows PC for its owner."

DIGEST_PROMPT = """Write this week's digest for the PC described below. Rules:
- Plain language, no jargon. Under 200 words total.
- First line: the single most important thing this week, or say the week was quiet if nothing stands out.
- Then up to 4 bullet points, ranked by what matters most: what changed, what's new, what's worth doing.
- End with one concrete, specific suggestion if there is one worth making.
- Only use what's in the data below. Never invent a device, app or number that isn't there.

DATA:
{data}"""


def _building_blocks(state, history):
    lines = [ai.summarize(state)]
    lines.append("\n## This week's timeline")
    items = history.timeline(limit=200, since=time.time() - DIGEST_SECONDS)
    if items:
        for item in items[:50]:
            lines.append(f"- {datetime.fromtimestamp(item['ts']):%a %d} {item['title']}")
    else:
        lines.append("Nothing logged this week.")

    changes = state.get("changes")
    if changes and changes.get("sections"):
        lines.append(f"\n## What changed since {changes['since']}")
        for s in changes["sections"]:
            bits = []
            if s.get("added"):
                bits.append(f"added {', '.join(s['added'][:5])}")
            if s.get("removed"):
                bits.append(f"removed {', '.join(s['removed'][:5])}")
            if s.get("changed"):
                bits.append(s["changed"])
            lines.append(f"- {s['label']}: {'; '.join(bits)}")
        if changes.get("effect"):
            lines.append(f"- {changes['effect']}")
    return "\n".join(lines)


def due(history, now=None):
    latest = history.latest_digest()
    now = now or time.time()
    return latest is None or now - latest["ts"] >= DIGEST_SECONDS


def build(model, state, history):
    """Ask the local model to write the digest now. Returns the text, or None if Ollama isn't reachable."""
    data = _building_blocks(state, history)
    voice = persona.ARGUS if paths.load_settings().get("personaEnabled", True) else None
    return ai.generate(model, SYSTEM_PROMPT, DIGEST_PROMPT.format(data=data), voice=voice)
