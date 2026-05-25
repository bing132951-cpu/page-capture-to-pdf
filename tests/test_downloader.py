import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from scribd_exporter.downloader import DownloadError, download_page_image
from scribd_exporter.models import PageImage
from fixtures import JPEG_BASE64
import base64


class DownloaderTests(unittest.TestCase):
    @staticmethod
    def _png_bytes(mode: str = "RGB", color=None) -> bytes:
        image = Image.new(mode, (3, 3), color=color or ((255, 0, 0, 255) if "A" in mode else (255, 0, 0)))
        with tempfile.NamedTemporaryFile(suffix=".png") as handle:
            image.save(handle.name, format="PNG")
            handle.seek(0)
            return handle.read()

    def test_download_page_image_accepts_valid_jpeg(self) -> None:
        jpeg_bytes = base64.b64decode(JPEG_BASE64)

        class FakeResponse:
            status = 200

            def __init__(self, data: bytes) -> None:
                self._data = data
                self.headers = {"Content-Type": "image/jpeg"}

            def read(self) -> bytes:
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        page = PageImage(page_number=1, image_url="https://example.com/1.jpg")
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("urllib.request.urlopen", return_value=FakeResponse(jpeg_bytes)):
                path = download_page_image(page, temp_dir)
            self.assertTrue(os.path.exists(path))

    def test_download_page_image_rejects_non_jpeg_content(self) -> None:
        class FakeResponse:
            status = 200

            def __init__(self) -> None:
                self.headers = {"Content-Type": "text/plain"}

            def read(self) -> bytes:
                return b"not-a-jpeg"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        page = PageImage(page_number=2, image_url="https://example.com/2.jpg")
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
                with self.assertRaises(DownloadError) as error:
                    download_page_image(page, temp_dir)
        self.assertEqual(error.exception.page_number, 2)
        self.assertEqual(error.exception.image_url, "https://example.com/2.jpg")

    def test_download_page_image_converts_webp_with_pillow(self) -> None:
        class FakeResponse:
            status = 200

            def __init__(self, data: bytes) -> None:
                self.headers = {"Content-Type": "image/webp"}
                self._data = data

            def read(self) -> bytes:
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        page = PageImage(page_number=3, image_url="https://example.com/3.webp")
        png_bytes = self._png_bytes("RGB", (0, 128, 255))

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("urllib.request.urlopen", return_value=FakeResponse(png_bytes)):
                path = download_page_image(page, temp_dir)
            self.assertTrue(os.path.exists(path))
            with Image.open(path) as converted:
                self.assertEqual(converted.format, "JPEG")
                self.assertEqual(converted.mode, "RGB")

    def test_download_page_image_converts_transparent_png_to_jpeg(self) -> None:
        class FakeResponse:
            status = 200

            def __init__(self, data: bytes) -> None:
                self.headers = {"Content-Type": "image/png"}
                self._data = data

            def read(self) -> bytes:
                return self._data

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        page = PageImage(page_number=4, image_url="https://example.com/4.png")
        png_bytes = self._png_bytes("RGBA", (0, 0, 0, 0))

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("urllib.request.urlopen", return_value=FakeResponse(png_bytes)):
                path = download_page_image(page, temp_dir)
            self.assertTrue(os.path.exists(path))
            with Image.open(path) as converted:
                self.assertEqual(converted.format, "JPEG")
                self.assertEqual(converted.mode, "RGB")


if __name__ == "__main__":
    unittest.main()
