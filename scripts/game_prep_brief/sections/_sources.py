"""Data source indicator tags for game prep brief HTML output."""
from __future__ import annotations


def _src(label: str) -> str:
    return f'<sup class="src">{label}</sup>'


SRC_PBP = _src("pbp")
SRC_CFB = _src("cfb")
SRC_PFF = _src("pff")
SRC_API = _src("api")
