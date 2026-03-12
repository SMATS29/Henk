"""Security proxy voor uitgaand HTTP-verkeer."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


@dataclass
class SimpleResponse:
    """Kleine response wrapper voor toolgebruik."""

    status_code: int
    text: str

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP foutstatus: {self.status_code}")


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

    def request(self, method: str, url: str, **kwargs) -> SimpleResponse:
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
        req = Request(url=url, method=normalized_method)
        with urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            status = getattr(response, "status", 200)
        return SimpleResponse(status_code=status, text=body)
