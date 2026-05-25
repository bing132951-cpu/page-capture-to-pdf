import os
import urllib.error
import urllib.request
from io import BytesIO
from urllib.parse import urlparse
from typing import Optional

from PIL import Image, UnidentifiedImageError

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
    """Download one page image and normalize it to a local JPEG file.

    Export always writes JPEG pages into the final PDF, so non-JPEG sources
    are downloaded first and then converted locally. The caller only needs the
    returned path and does not have to care whether the source was JPEG, PNG,
    or WebP.
    """
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
        # Fast path: if the server already gives us JPEG bytes, keep them as-is
        # so we avoid an unnecessary re-encode step and preserve fidelity.
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
    # Conversion works from in-memory bytes, but we also keep the source file on
    # disk briefly so a failed run leaves a debuggable artifact near the output.
    _convert_to_jpeg_with_pillow(page, data, source_path, target_path)
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


def _convert_to_jpeg_with_pillow(page: PageImage, image_bytes: bytes, source_path: str, target_path: str) -> None:
    """Decode a non-JPEG payload with Pillow and save it as a JPEG file."""
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            converted = _prepare_image_for_jpeg(image)
            converted.save(target_path, format="JPEG", quality=95)
            converted.close()
    except UnidentifiedImageError as exc:
        raise DownloadError(page.page_number, page.image_url, "failed to decode image for JPEG conversion") from exc
    except OSError as exc:
        raise DownloadError(page.page_number, page.image_url, f"failed to convert image to JPEG ({exc})") from exc

    if not os.path.exists(target_path):
        raise DownloadError(page.page_number, page.image_url, "failed to convert image to JPEG (no output file)")

    if os.path.exists(source_path) and source_path != target_path:
        os.remove(source_path)


def _prepare_image_for_jpeg(image: Image.Image) -> Image.Image:
    """Return an image object Pillow can safely encode as JPEG.

    JPEG does not support alpha channels or palette modes directly. We flatten
    transparency onto a white background and normalize everything else to RGB so
    downstream PDF generation only ever sees a consistent file format.
    """
    if image.mode in {"RGBA", "LA"}:
        background = Image.new("RGB", image.size, (255, 255, 255))
        alpha = image.getchannel("A")
        background.paste(image.convert("RGBA"), mask=alpha)
        return background
    if image.mode == "P":
        return _prepare_image_for_jpeg(image.convert("RGBA"))
    if image.mode != "RGB":
        return image.convert("RGB")
    return image.copy()
