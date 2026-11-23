"""
openai mock / client module for local development, testing, and offline execution.
"""
from __future__ import annotations
from types import SimpleNamespace
import os


class ChatCompletion:
    @staticmethod
    def create(*, model: str, messages, temperature: float = 0):
        """Return a mock OpenAI response supporting intelligent SQL generation.

        The returned object matches the real OpenAI API shape: ``choices[0].message.content``.
        Tests can monkey-patch this method to test arbitrary SQL strings and error flows.
        """
        # Extract combined prompt text from messages
        prompt_text = ""
        for m in messages:
            if isinstance(m, dict):
                prompt_text += " " + str(m.get("content", ""))
            elif hasattr(m, "content"):
                prompt_text += " " + str(getattr(m, "content", ""))
        prompt_lower = prompt_text.lower()

        # Handle self-correction when previous query had an invalid column (e.g., created_at)
        if "no such column" in prompt_lower or "failed with error" in prompt_lower or "please correct" in prompt_lower:
            sql = "SELECT id, order_date FROM orders;"
        elif "created_at" in prompt_lower:
            # First attempt with requested invalid column to exercise self-correction
            sql = "SELECT id, created_at FROM orders;"
        elif "count" in prompt_lower or "how many" in prompt_lower:
            sql = "SELECT count(*) AS total_orders FROM orders;"
        elif "orders" in prompt_lower or "order" in prompt_lower:
            sql = "SELECT id, order_date FROM orders;"
        elif "constant" in prompt_lower:
            sql = "SELECT 1;"
        else:
            sql = "SELECT 1;"

        msg = SimpleNamespace(content=sql)
        choice = SimpleNamespace(message=msg)
        return SimpleNamespace(choices=[choice])
