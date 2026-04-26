from __future__ import annotations

import shutil
from typing import Any

from claude import ClaudeProvider
from codex import CodexProvider


def _provider_config(config: dict[str, Any], name: str) -> dict[str, Any]:
    providers = config.get("providers", {})
    if isinstance(providers, dict):
        value = providers.get(name, {})
        return value if isinstance(value, dict) else {}
    return {}


def build_provider(name: str, config: dict[str, Any] | None = None):
    config = config or {}
    if name == "claude":
        provider_config = _provider_config(config, "claude")
        return ClaudeProvider(binary=str(provider_config.get("binary", "claude")))
    if name == "codex":
        provider_config = _provider_config(config, "codex")
        return CodexProvider(binary=str(provider_config.get("binary", "codex")))
    raise ValueError(f"Unknown provider: {name}")


def available_provider_names(config: dict[str, Any] | None = None) -> list[str]:
    names = []
    for name in ("codex", "claude"):
        try:
            provider = build_provider(name, config)
        except ValueError:
            continue
        if provider.available():
            names.append(name)
    return names


def get_provider(name: str | None = None, config: dict[str, Any] | None = None):
    config = config or {}
    requested = name or str(config.get("default_provider", "auto"))
    if requested and requested != "auto":
        provider = build_provider(requested, config)
        if provider.available():
            return provider
        fallback = str(config.get("fallback_provider", ""))
        if fallback:
            fallback_provider = build_provider(fallback, config)
            if fallback_provider.available():
                return fallback_provider
        raise RuntimeError(f"Requested provider is unavailable: {requested}")

    for candidate in ("codex", "claude"):
        provider = build_provider(candidate, config)
        if provider.available():
            return provider
    raise RuntimeError("No supported provider found. Install codex or claude.")
