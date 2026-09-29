"""
Proactive AI notes: when a new alert appears, the local AI writes a short
plain-English explanation and the best next step, shown on the Advisor card
and in the timeline.

Careful with resources: one note at a time, at most 12 a day, skipped while
the graphics card is busy (a game is probably running; the note is written
later), and only when Ollama is running with the model downloaded.
"""

import queue
import threading
import time

import ai
import paths
import persona

MAX_PER_DAY = 12
GPU_BUSY_PERCENT = 50
RETRY_SECONDS = 600

PROMPT = """A new item just appeared in my Matrix Advisor:

"{title}". {detail}

In 2-3 short sentences, in your own voice: explain what this means for my PC using the live data, and name the
single best next step. No lists, no headings."""


class Explainer:
    def __init__(self, history, get_state, get_model):
        self.history = history
        self.get_state = get_state
        self.get_model = get_model
        self.queue = queue.Queue()
        self.waiting = {}  # key -> item, for items deferred while the GPU was busy

    def start(self):
        threading.Thread(target=self._loop, daemon=True, name="ai-notes").start()

    def request(self, item):
        """Called by the alert manager when an item is raised."""
        key = f"{item['id']}|{item['fingerprint']}"
        if not self.history.ai_note(key):
            self.queue.put((key, item))

    def _loop(self):
        while True:
            try:
                key, item = self.queue.get(timeout=RETRY_SECONDS)
            except queue.Empty:
                # Periodically retry anything deferred earlier.
                for key, item in list(self.waiting.items()):
                    self.queue.put((key, item))
                self.waiting.clear()
                continue
            try:
                self._explain(key, item)
            except Exception as err:
                print(f"[matrix] AI note failed: {err}")

    def _explain(self, key, item):
        if self.history.ai_note(key) or self.history.ai_notes_today() >= MAX_PER_DAY:
            return
        model = self.get_model()
        status = ai.status(model)
        state = self.get_state()
        gpu = (state["system"].get("gpus") or [{}])[0].get("usage") or 0
        if not (status["running"] and status["installed"]) or gpu >= GPU_BUSY_PERCENT:
            self.waiting[key] = item  # try again later
            return
        voice = persona.voice_for_ai_note(item) if paths.load_settings().get("personaEnabled", True) else None
        messages = [{"role": "user", "content": PROMPT.format(title=item["title"], detail=item["detail"])}]
        text = ""
        for event in ai.stream_answer(model, messages, state, think=False, voice=voice):
            if event["type"] == "content":
                text += event["text"]
            elif event["type"] == "error":
                self.waiting[key] = item
                return
        text = text.strip()
        if text:
            self.history.save_ai_note(key, text[:1200])
            self.history.log("ai", f"Matrix explained: {item['title']}", text[:400], ref=key)
        time.sleep(2)  # breathe between notes
