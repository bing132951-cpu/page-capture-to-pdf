from typing import List
from urllib.parse import urlparse

from .models import CollectedDocument, PageImage


class UrlInputError(ValueError):
    """Raised when user-provided URL input cannot be accepted."""


def parse_urls_text(urls_text: str, title: str = "Untitled document") -> CollectedDocument:
    lines = [line.strip() for line in urls_text.splitlines()]
    urls = [line for line in lines if line]
    if not urls:
        raise UrlInputError("No image URLs were provided.")

    pages = []
    for index, url in enumerate(urls, start=1):
        _validate_jpeg_url(url, index)
        pages.append(PageImage(page_number=index, image_url=url))
    return CollectedDocument(title=title, total_pages=len(pages), pages=pages)


def _validate_jpeg_url(url: str, line_number: int) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UrlInputError(f"Line {line_number}: only http/https URLs are supported.")
    if not parsed.netloc:
        raise UrlInputError(f"Line {line_number}: URL is missing a host.")
    path = parsed.path.lower()
    if not (path.endswith(".jpg") or path.endswith(".jpeg")):
        raise UrlInputError(f"Line {line_number}: only .jpg/.jpeg URLs are supported.")
