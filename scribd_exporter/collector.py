import json
from typing import Dict, Optional

from .models import CollectedDocument
from .url_input import parse_urls_text


def load_document_json(path: str) -> CollectedDocument:
    with open(path, "r", encoding="utf-8") as handle:
        return CollectedDocument.from_dict(json.load(handle))


def load_url_list(path: str, title: str = "Untitled document") -> CollectedDocument:
    with open(path, "r", encoding="utf-8") as handle:
        return parse_urls_text(handle.read(), title=title)


def save_document_json(document: CollectedDocument, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document.to_dict(), handle, ensure_ascii=False, indent=2)


def save_pages_payload(payload: Dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
