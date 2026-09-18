"""OMR engines behind one interface. `get_engine(name)` is the only entry point (ADR 0002)."""
from __future__ import annotations

from .base import Engine, EngineError

_REGISTRY: dict[str, type[Engine]] = {}


def register(cls: type[Engine]) -> type[Engine]:
    _REGISTRY[cls.name] = cls
    return cls


def get_engine(name: str, **kwargs) -> Engine:
    from . import audiveris, fake, homr  # noqa: F401  (registration side effect)

    try:
        cls = _REGISTRY[name]
    except KeyError as e:
        raise EngineError(f"unknown engine {name!r}; known: {sorted(_REGISTRY)}") from e
    return cls(**kwargs)


__all__ = ["Engine", "EngineError", "get_engine", "register"]
