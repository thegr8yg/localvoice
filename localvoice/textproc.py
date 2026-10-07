"""Clean up a raw transcript before it is inserted."""

from __future__ import annotations

import re


def clean(text: str, replacements: dict[str, str] | None = None, trailing_space: bool = True) -> str:
    text = " ".join(text.split())
    for spoken, written in (replacements or {}).items():
        if spoken:
            pattern = r"(?<!\w)" + re.escape(spoken) + r"(?!\w)"
            text = re.sub(pattern, lambda _m, w=written: w, text, flags=re.IGNORECASE)
    text = text.strip()
    if text and trailing_space:
        text += " "
    return text
