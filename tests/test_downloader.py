import io
import os
import tempfile
import unittest
from unittest import mock

from scribd_exporter.downloader import DownloadError, download_page_image
from scribd_exporter.models import PageImage
from fixtures import JPEG_BASE64
import base64


class DownloaderTests(unittest.TestCase):
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

    def test_download_page_image_converts_webp_with_sips(self) -> None:
        class FakeResponse:
            status = 200

            def __init__(self) -> None:
                self.headers = {"Content-Type": "image/webp"}

            def read(self) -> bytes:
                return b"RIFFfakewebp"

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

        page = PageImage(page_number=3, image_url="https://example.com/3.webp")

        def fake_run(cmd, capture_output, text, check):
            out_path = cmd[-1]
            with open(out_path, "wb") as handle:
                handle.write(base64.b64decode(JPEG_BASE64))
            return mock.Mock(returncode=0, stderr="", stdout="")

        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("urllib.request.urlopen", return_value=FakeResponse()):
                with mock.patch("subprocess.run", side_effect=fake_run) as run_mock:
                    path = download_page_image(page, temp_dir)
            self.assertTrue(os.path.exists(path))
            run_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
