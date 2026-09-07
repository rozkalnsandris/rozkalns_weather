from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True, slots=True)
class ProviderDescriptor:
    id: str
    model_provider: str
    model_name: str
    role: str
    transport: str | None = None
    station_id: str | None = None


class JsonFetcher(Protocol):
    def __call__(self, url: str, params: dict[str, Any]) -> dict[str, Any]: ...


class BytesFetcher(Protocol):
    def __call__(self, url: str) -> bytes: ...


def fetch_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("provider returned non-object JSON")
    return payload


def fetch_bytes(url: str) -> bytes:
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        return response.content
