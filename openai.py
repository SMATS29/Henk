"""Lichte fallback stub voor openai package in offline test-omgeving."""


class OpenAI:
    def __init__(self, *args, **kwargs):
        self.chat = _ChatNamespace()


class _ChatNamespace:
    def __init__(self):
        self.completions = _CompletionsNamespace()


class _CompletionsNamespace:
    def create(self, *args, **kwargs):
        raise RuntimeError("openai package is niet beschikbaar in deze omgeving")
