"""Kleine lokale requests-compat layer voor testomgevingen zonder requests package."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.request import Request, urlopen


@dataclass
class Response:
    status_code: int
    text: str

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP foutstatus: {self.status_code}")


def request(method: str, url: str, timeout: int = 10) -> Response:
    req = Request(url=url, method=method.upper())
    with urlopen(req, timeout=timeout) as raw:
        body = raw.read().decode("utf-8", errors="replace")
        return Response(status_code=getattr(raw, "status", 200), text=body)
