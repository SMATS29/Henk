"""Security proxy voor uitgaand HTTP-verkeer."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import requests as http_requests


class SecurityProxy:
    """Filtert alle uitgaande netwerkverzoeken."""

    def __init__(self, allowed_domains: list[str], allowed_methods: list[str]):
        self.allowed_domains = {d.lower() for d in allowed_domains}
        self.allowed_methods = {m.upper() for m in allowed_methods}

    def _validate_query(self, url: str) -> None:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        suspicious = ["api_key", "token", "secret", "password"]
        for key in query:
            if any(marker in key.lower() for marker in suspicious):
                raise PermissionError("Verdachte querystring geblokkeerd.")

    def request(self, method: str, url: str, **kwargs) -> http_requests.Response:
        """Voer een HTTP request uit na validatie."""
        normalized_method = method.upper()
        if normalized_method not in self.allowed_methods:
            raise PermissionError(f"HTTP methode niet toegestaan: {normalized_method}")

        parsed = urlparse(url)
        domain = (parsed.hostname or "").lower()
        if domain not in self.allowed_domains:
            raise PermissionError(f"Domein niet toegestaan: {domain}")

        self._validate_query(url)

        timeout = kwargs.get("timeout", 10)
        return http_requests.request(normalized_method, url, timeout=timeout)
