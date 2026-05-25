import os
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urlparse
from typing import Optional

from .models import PageImage


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


class DownloadError(RuntimeError):
    """Raised when an image cannot be downloaded or validated."""

    def __init__(self, page_number: int, image_url: str, message: str) -> None:
        super().__init__(f"Page {page_number}: {message}: {image_url}")
        self.page_number = page_number
        self.image_url = image_url
        self.message = message


def download_page_image(page: PageImage, output_dir: str, cookie: Optional[str] = None) -> str:
    os.makedirs(output_dir, exist_ok=True)
    target_path = os.path.join(output_dir, f"page-{page.page_number:04d}.jpg")
    request = urllib.request.Request(page.image_url, headers={"User-Agent": USER_AGENT})
    if cookie:
        request.add_header("Cookie", cookie)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
    except urllib.error.HTTPError as exc:
        raise DownloadError(page.page_number, page.image_url, f"HTTP {exc.code} while downloading") from exc
    except urllib.error.URLError as exc:
        raise DownloadError(page.page_number, page.image_url, f"network error while downloading ({exc.reason})") from exc

    if status != 200:
        raise DownloadError(page.page_number, page.image_url, f"HTTP {status} while downloading")
    if _is_jpeg_response(content_type, data):
        with open(target_path, "wb") as handle:
            handle.write(data)
        return target_path

    source_extension = _infer_source_extension(page.image_url, content_type)
    if not source_extension:
        raise DownloadError(
            page.page_number,
            page.image_url,
            f"unsupported image content, expected JPEG/PNG/WebP but got {content_type or 'unknown'}",
        )

    source_path = os.path.join(output_dir, f"page-{page.page_number:04d}{source_extension}")
    with open(source_path, "wb") as handle:
        handle.write(data)
    _convert_to_jpeg_with_sips(page, source_path, target_path)
    return target_path


def _is_jpeg_response(content_type: str, data: bytes) -> bool:
    lowered = (content_type or "").lower()
    return "jpeg" in lowered or data[:2] == b"\xff\xd8"


def _infer_source_extension(image_url: str, content_type: str) -> str:
    lowered_type = (content_type or "").split(";")[0].strip().lower()
    if lowered_type in SUPPORTED_CONTENT_TYPES:
        return SUPPORTED_CONTENT_TYPES[lowered_type]

    path = urlparse(image_url).path.lower()
    for extension in SUPPORTED_IMAGE_EXTENSIONS:
        if path.endswith(extension):
            return extension
    return ""


def _convert_to_jpeg_with_sips(page: PageImage, source_path: str, target_path: str) -> None:
    result = subprocess.run(
        ["sips", "-s", "format", "jpeg", source_path, "--out", target_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not os.path.exists(target_path):
        stderr = (result.stderr or result.stdout or "").strip() or "unknown conversion error"
        raise DownloadError(page.page_number, page.image_url, f"failed to convert image to JPEG ({stderr})")
