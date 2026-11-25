"""Split Deskville content documents into chunks (D30).

One chunk per '## ' section (each section is one resident question and its
answer). Sections longer than MAX_CHARS are split at paragraph boundaries.
Each chunk's text starts with the council and document title, so similar
questions in different councils never produce identical text.
Front matter is kept as metadata, never embedded.
Standard library only.
"""
import hashlib
import re
from pathlib import Path

MAX_CHARS = 1500
MODEL = "amazon.titan-embed-text-v2:0"
DIMENSIONS = 1024
COUNCIL = {"wigan": "Wigan", "bury": "Bury"}


def parse_front_matter(text):
    """Minimal YAML subset used by our docs: 'key: value' and '  - item' lists."""
    if not text.startswith("---\n"):
        raise ValueError("missing front matter")
    end = text.index("\n---\n", 4)
    meta, key = {}, None
    for line in text[4:end].splitlines():
        if line.startswith("  - ") and key:
            meta.setdefault(key, []).append(line[4:].strip())
        elif ":" in line:
            key, _, value = line.partition(":")
            key, value = key.strip(), value.strip()
            meta[key] = [] if value in ("", "[]") else value
    return meta, text[end + 5:]


def split_long(body):
    """Split a section body at blank lines into pieces of at most MAX_CHARS."""
    if len(body) <= MAX_CHARS:
        return [body]
    pieces, current = [], ""
    for para in re.split(r"\n\s*\n", body):
        if current and len(current) + len(para) + 2 > MAX_CHARS:
            pieces.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        pieces.append(current)
    return pieces


def cache_key(text):
    return hashlib.sha256(f"{MODEL}|{DIMENSIONS}|{text}".encode()).hexdigest()


def chunk_document(tenant, text):
    meta, body = parse_front_matter(text)
    if meta.get("tenant") != tenant:
        raise ValueError(f"{meta.get('id')}: front matter tenant {meta.get('tenant')!r} != folder {tenant!r}")
    title = meta["title"]
    sections = re.split(r"^## ", body, flags=re.M)
    intro = re.sub(r"^#.*\n", "", sections[0]).strip()  # drop the '# title' line
    if intro:
        # Text before the first section (e.g. the canaries' banner) is never dropped.
        sections[0] = "About this document\n" + intro
    else:
        sections = sections[1:]
    chunks = []
    for section in sections:
        heading, _, sbody = section.partition("\n")
        for part in split_long(sbody.strip()):
            if not part:
                continue
            text = f"{COUNCIL[tenant]} - {title}: {heading.strip()}\n\n{part}"
            chunks.append({
                "tenant": tenant,
                "doc_id": meta["id"],
                "chunk_index": len(chunks),
                "title": title,
                "heading": heading.strip(),
                "text": text,
                "sources": meta.get("sources", []),
                "retrieved": meta.get("retrieved"),
                "visibility": meta.get("visibility", "public"),
                "cache_key": cache_key(text),
            })
    return chunks


def chunk_tenant(content_dir, tenant):
    out = []
    for path in sorted(Path(content_dir, tenant).glob("*.md")):
        out.extend(chunk_document(tenant, path.read_text(encoding="utf-8")))
    return out
