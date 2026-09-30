"""Multilingual lexical terms for PostgreSQL simple FTS."""
from __future__ import annotations

import re

import jieba

_WORD = re.compile(r"[A-Za-zÄÖÜäöüß0-9]+(?:[-./][A-Za-zÄÖÜäöüß0-9]+)*|[\u3400-\u9fff]+")
_STOP = {
    "a", "an", "and", "are", "as", "at", "be", "by", "der", "die", "das", "den",
    "dem", "des", "ein", "eine", "for", "from", "has", "have", "how", "in", "ist",
    "mit", "of", "on", "or", "the", "to", "und", "was", "were", "what", "when",
    "which", "who", "wie", "wo", "with", "zum", "zur", "了", "什么", "多少", "是否",
    "目前", "现在", "的是", "哪些", "这个", "那个", "根据", "项目", "报告", "版本",
}


def terms(text: str) -> list[str]:
    chunks = _WORD.findall(text)
    out: list[str] = []
    for chunk in chunks:
        if "\u3400" <= chunk[0] <= "\u9fff":
            out.extend(jieba.lcut(chunk))
        else:
            out.append(chunk)
            if "-" in chunk:
                out.extend(chunk.split("-"))
    return list(dict.fromkeys(
        word.lower() for word in out if word.strip() and word.lower() not in _STOP
    ))[:80]


def indexed_text(text: str) -> str:
    return " ".join(terms(text))


def tsquery(text: str) -> str:
    # Terms are quoted individually, then joined by OR for recall across languages.
    values = [w.replace("'", "''") for w in terms(text)[:20]]
    return " | ".join("'" + w + "'" for w in values)
