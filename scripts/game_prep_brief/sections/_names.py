from __future__ import annotations

import re

_SUFFIX_MAP = {
    "JR": "Jr",
    "JR.": "Jr.",
    "SR": "Sr",
    "SR.": "Sr.",
    "II": "II",
    "III": "III",
    "IV": "IV",
    "V": "V",
}


def _title_token(token: str) -> str:
    token = token.strip()
    if not token:
        return token
    upper = token.upper()
    if upper in _SUFFIX_MAP:
        return _SUFFIX_MAP[upper]
    if token.isalpha() and len(token) == 1:
        return token.upper()
    if token.isalpha() and len(token) <= 3 and token.upper() == token and not re.search(r"[AEIOU]", token.upper()):
        return token.upper()
    if len(token) == 2 and token.endswith(".") and token[0].isalpha():
        return f"{token[0].upper()}."
    if "." in token and token.replace(".", "").isalpha():
        return ".".join(_title_token(part) for part in token.split(".") if part) + ("." if token.endswith(".") else "")

    def _cap_piece(piece: str) -> str:
        if not piece:
            return piece
        return re.sub(r"[A-Za-z]+", lambda m: m.group(0)[:1].upper() + m.group(0)[1:].lower(), piece)

    token = "'".join(_cap_piece(piece) for piece in token.split("'"))
    token = "-".join(_cap_piece(piece) for piece in token.split("-"))
    return token


def _normalize_name_part(part: str) -> str:
    return " ".join(_title_token(token) for token in part.strip().split())


def format_player_name(name: str | None) -> str:
    if not name:
        return "?"
    raw = str(name).strip()
    if not raw:
        return "?"
    if "→" in raw:
        return " → ".join(format_player_name(part) for part in raw.split("→"))
    if "," in raw:
        last, first = raw.split(",", 1)
        return f"{_normalize_name_part(last)},{_normalize_name_part(first)}"
    return _normalize_name_part(raw)
