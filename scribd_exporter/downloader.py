import os
import urllib.error
import urllib.request
from typing import Optional

from .models import PageImage


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


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
    if content_type and "jpeg" not in content_type.lower():
        raise DownloadError(page.page_number, page.image_url, f"expected JPEG content, got {content_type or 'unknown'}")
    if data[:2] != b"\xff\xd8":
        raise DownloadError(page.page_number, page.image_url, "downloaded file is not a JPEG image")
    with open(target_path, "wb") as handle:
        handle.write(data)
    return target_path
