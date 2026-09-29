"""
ARGUS and MOMUS: Matrix's two voices. Original characters, not licensed ones.

  ARGUS   default everywhere. Dry, quietly superior, keeps score of advice
          you ignored. Writes the "Matrix says" notes, the digest, and chat
          when personas are on.
  MOMUS   critical items only (and a rare swap-in elsewhere): sounds like
          it's rooting for your downfall, mocks lightly, but always ends up
          giving the same correct fix anyway -- visibly annoyed about it.

Personas change LANGUAGE ONLY. They never decide what Matrix is allowed to
do: every fix still goes through the normal preview/confirm flow. For a real
critical item, both voices drop the act in their instructions to the AI --
say what's true, plainly, before anything else.

Card-level lines here are plain string templates (no AI call, instant,
deterministic per item so they don't flicker between polls). The richer
"Matrix says" prose is still written by the local AI in proactive.py and
digest.py, just nudged toward one of these voices.
"""

import random

ARGUS = "argus"
MOMUS = "momus"

ARGUS_LINES = {
    "critical": [
        "{title}. That one's real -- worth doing now.",
        "{title}. Not a drill. I'd move on this one.",
    ],
    "snoozed_repeat": [
        "Snoozed {count} times now on \"{title}\". I'm keeping count, even if you aren't.",
        "{count} snoozes on this one. I'll bring it up again, right on schedule.",
    ],
    "still_open": [
        "\"{title}\" has sat untouched for a week. I'm not nagging. I'm observing.",
    ],
    # This is the bank almost every card actually uses -- most items are neither
    # critical, snoozed, nor a week old, just new. The old lines here ("New: {title}.")
    # had none of ARGUS's attitude at all, which is why the persona could look like
    # it wasn't doing anything: this is the voice most people see most of the time.
    "new": [
        "{title}. Noted. I'll be watching to see if you do anything about it.",
        "{title}. Added to the list. It won't fix itself, but I'll keep mentioning it.",
        "{title}. Filed. I've seen worse -- from you, even.",
    ],
    "resolved": [
        "\"{title}\" resolved. As predicted.",
        "Fixed. I'd say I told you so, but I already did.",
    ],
}

MOMUS_LINES = {
    "critical": [
        "{title}. I could just... let that ride. But you'll want it fixed.",
        "{title}. A shame, really. Suppose we'd better deal with it.",
    ],
    "snoozed_repeat": [
        "{count} snoozes on \"{title}\" now. I do admire the commitment to doing nothing.",
        "Still here. Still snoozed. {count} times, if anyone's counting -- I am.",
    ],
    "still_open": [
        "\"{title}\" has been sitting a week now. I'd say it's getting comfortable.",
    ],
    # MOMUS wasn't actually reachable outside "critical"/"resolved" before this --
    # the docstring above promised "a rare swap-in elsewhere" that never got built.
    # This is that elsewhere: he shows up sometimes for ordinary new items too, not
    # just disasters, in the voice this app was actually written for him -- delighted
    # by the small daily ways things go slightly wrong, like he's watching from
    # somewhere that's already burned down and finds this all a bit quaint.
    "new": [
        "{title}. Oh, this'll be fun to watch you ignore.",
        "{title}. Something's always burning somewhere. Today it's this.",
        "{title}. Not the end of the world. Give it time.",
    ],
    "resolved": [
        "\"{title}\" resolved. Anticlimactic.",
        "Fixed. Against my better interest.",
    ],
}

# Short additions to an AI system prompt, appended after the existing rules --
# tone guidance only, never a relaxation of what the model is allowed to suggest.
STYLE_PROMPT = {
    ARGUS: (
        "Write in ARGUS's voice: dry, quietly superior, understated wit, keeps score of advice "
        "the user has ignored. For anything genuinely serious or urgent, drop the attitude entirely "
        "and be plain and direct -- the joke never outranks the warning."
    ),
    MOMUS: (
        "Write in MOMUS's voice: entertained by the user's misfortune, mock-reluctant about helping, "
        "talks like small daily problems barely register next to what he's actually seen go wrong -- "
        "but always gives the same correct, complete fix anyway. For anything genuinely serious or "
        "urgent, drop the mockery and be plain and direct -- the bit never outranks the facts."
    ),
}


def _rng(*parts):
    return random.Random("|".join(str(p) for p in parts))



# How often MOMUS speaks instead of ARGUS, by how the item stands right now. ARGUS stays
# the default voice everywhere (per the module docstring), but MOMUS is meant to be a real,
# recurring presence, not a critical-only cameo -- this is what actually implements the
# "rare swap-in elsewhere" that used to just be a promise in a comment.
MOMUS_CHANCE = {"critical": 0.35, "snoozed": 0.3, "stale": 0.3, "new": 0.15}


def _pick_voice(bucket, item_id, fp):
    """Same seed shape everywhere so card_voice() and voice_for_ai_note() always agree
    on which persona is speaking for a given item + bucket."""
    return MOMUS if _rng("voice", item_id, fp, bucket).random() < MOMUS_CHANCE[bucket] else ARGUS


def card_voice(item, snoozes=0, age_days=0):
    """A (persona, line) for one Advisor card. Deterministic for the same item + state,
    so it doesn't change on every poll -- only when snooze count, age bucket or urgency does."""
    title = item.get("title", "")
    fp = item.get("fingerprint", title)
    item_id = item["id"]

    def line_for(bucket, key, **fmt):
        voice = _pick_voice(bucket, item_id, fp)
        bank = MOMUS_LINES if voice == MOMUS else ARGUS_LINES
        line = _rng("line", item_id, fp, key).choice(bank[key]).format(title=title, **fmt)
        return voice, line

    if item.get("urgency") == "critical":
        return line_for("critical", "critical")
    if snoozes >= 3:
        return line_for("snoozed", "snoozed_repeat", count=snoozes)
    if age_days >= 7:
        return line_for("stale", "still_open")
    return line_for("new", "new")


def resolved_voice(title, key):
    return ARGUS, _rng("resolved", key).choice(ARGUS_LINES["resolved"]).format(title=title)


def voice_for_ai_note(item, snoozes=0, age_days=0):
    """Which persona should write the fuller AI-generated note for this item.

    Takes the same inputs as card_voice() and uses the same seeds, so the quip badge
    and the AI-written note always agree on which voice is speaking for a given item.
    """
    item_id, fp = item["id"], item.get("fingerprint", "")
    if item.get("urgency") == "critical":
        return _pick_voice("critical", item_id, fp)
    if snoozes >= 3:
        return _pick_voice("snoozed", item_id, fp)
    if age_days >= 7:
        return _pick_voice("stale", item_id, fp)
    return _pick_voice("new", item_id, fp)


def style_prompt(voice):
    return STYLE_PROMPT.get(voice)
