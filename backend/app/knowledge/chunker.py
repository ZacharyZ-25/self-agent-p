from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

import tiktoken

CHUNKER_VERSION = "1.1-cl100k_base"


def encoding():
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(
        Path(__file__).resolve().parents[3] / "knowledge-data/tokenizer-cache"))
    return tiktoken.get_encoding("cl100k_base")


def chunk(blocks: list[dict], target: int = 600, overlap: int = 80) -> list[dict]:
    enc = encoding()

    def count(text):
        return len(enc.encode(text, disallowed_special=()))

    def tail(text):
        # Never split a Unicode codepoint at a tokenizer boundary.
        if not overlap:
            return ""
        return enc.decode(enc.encode(text, disallowed_special=())[-overlap:], errors="ignore")
    out = []
    pending, locations, previous_section = "", [], None
    def emit(text, locs):
        if text.strip():
            out.append({"body":text, "locations":locs, "token_count":count(text),
                        "content_hash":hashlib.sha256(text.encode()).hexdigest()})
    for b in blocks:
        section = b["location"].get("section", "")
        prefix = (section + "\n" if section else "") + (b["header"] + "\n" if b["table"] else "")
        if count(prefix) >= target // 2:
            # Preserve full source in parsed_blocks; unusually long headings need review.
            from app.knowledge.parsers import IngestionError
            raise IngestionError("HEADING_OR_TABLE_HEADER_TOO_LONG", review=True)
        text = prefix + b["text"]
        new_page = bool(locations and "page" in b["location"] and
                        b["location"]["page"] != locations[-1].get("page"))
        if pending and (new_page or section != previous_section or
                        count(pending+"\n\n"+text) > target):
            emit(pending, locations)
            shared = tail(pending) if section == previous_section and not new_page else ""
            pending, locations = shared, locations[-1:] if shared else []
        if count(text) <= target:
            if pending and count(pending+"\n\n"+text) > target:
                pending, locations = "", []
            pending = pending+"\n\n"+text if pending else text
            locations = [*locations, b["location"]]
        else:
            emit(pending, locations)
            pending, locations = "", []
            # Prefer sentence/newline boundaries; split only oversized units with exact offsets.
            source, start = b["text"], 0
            while start < len(source):
                low, high = start+1, len(source)
                while low < high:
                    mid = (low + high + 1) // 2
                    if count(prefix + source[start:mid]) <= target:
                        low = mid
                    else:
                        high = mid-1
                end = low
                breaks = list(re.finditer(r"[。！？.!?\n]\s*", source[start:end]))
                if end < len(source) and breaks and breaks[-1].end() > (end-start)*.6:
                    end = start+breaks[-1].end()
                emit(prefix+source[start:end], [
                    {**b["location"], "char_start":start, "char_end":end}
                ])
                if end == len(source):
                    break
                shared = tail(source[start:end])
                start = max(start+1, end-len(shared))
        previous_section = section
    emit(pending, locations)
    return out
