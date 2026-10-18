import hashlib
import json
import re
import unicodedata

from ml.constants import EMBEDDING_MODEL_ID


SEARCH_DOCUMENT_VERSION = "context-v1"
_RELATED = re.compile(r"^(?:читайте?\s+(?:также|подробнее)|читать\s+подробнее|к\s+статье)\s*:", re.I)
_NOTE = re.compile(r"^#{0,6}\s*примечани[ея]\b", re.I)


def clean_text(text: str) -> str:
    text = re.split(r"(?:читайте?\s+(?:также|подробнее)|читать\s+подробнее)\s*:", text, maxsplit=1, flags=re.I)[0]
    text = re.sub(r"\[([^\]]+)\]\(https?://[^\s]+\)", r"\1", text)
    text = re.sub(r"https?://[^\s)]+", "", text)
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"[*_`☐]+", "", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def normalized_title(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold().replace("ё", "е")
    return " ".join(re.findall(r"[^\W_]+", text))


def source_hash(title: str, bodies: list[str]) -> str:
    data = json.dumps([SEARCH_DOCUMENT_VERSION, EMBEDDING_MODEL_ID, title, bodies], ensure_ascii=False)
    return hashlib.sha256(data.encode()).hexdigest()


def _split(text: str, size: int = 560) -> list[str]:
    result = []
    while len(text) > size:
        matches = list(re.finditer(r"(?<=[.!?;])\s+|\n+", text[:size + 1]))
        cut = matches[-1].end() if matches else text.rfind(" ", 0, size) + 1
        if cut < size // 2:
            cut = size
        result.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        result.append(text)
    return result


def prepare_documents(title: str, bodies: list[str]) -> list[str]:
    title = clean_text(title)
    sections: list[tuple[str, str]] = []
    heading = ""
    related = False
    for body in bodies:
        if _NOTE.match(body.strip()):
            continue
        for block in re.split(r"\n\s*\n", body):
            lines = []
            for line in block.splitlines():
                if _RELATED.match(line.lstrip("#*_ ")):
                    related = True
                    continue
                cleaned = clean_text(line).lstrip("# ")
                if not cleaned or re.match(r"^автор\s*:", cleaned, re.I):
                    continue
                if related and cleaned.startswith(("«", '"')):
                    continue
                related = False
                if re.match(r"^\s*#{1,6}\s", line):
                    if lines:
                        sections.append((heading, "\n".join(lines)))
                        lines = []
                    heading = cleaned
                elif not lines and len(cleaned) < 80 and not re.search(r"[.!?;]", cleaned) and not cleaned.startswith("-"):
                    heading = cleaned
                else:
                    lines.append(cleaned)
            if lines:
                text = "\n".join(lines)
                if len(text) >= 12:
                    sections.append((heading, text))
    merged: list[tuple[str, str]] = []
    for heading, text in sections:
        if merged and merged[-1][0] == heading and len(merged[-1][1]) + len(text) < 560:
            previous = merged.pop()[1]
            text = previous + "\n" + text
        merged.append((heading, text))
    documents = []
    for heading, text in merged:
        context = title + ("\n" + heading if heading and normalized_title(heading) != normalized_title(title) else "")
        documents.extend(context + "\n\n" + part for part in _split(text))
    return list(dict.fromkeys(documents))
