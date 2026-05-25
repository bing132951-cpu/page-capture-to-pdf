import os
import tempfile
import unittest
from unittest import mock

from scribd_exporter.browser_collect import BrowserCollectError
from scribd_exporter.downloader import DownloadError
from scribd_exporter.webapp import (
    _build_error_payload,
    _safe_output_name,
    create_collection_from_payload,
    create_export_from_payload,
)


class WebAppLogicTests(unittest.TestCase):
    def test_create_export_from_payload_returns_download_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch("scribd_exporter.webapp.export_document_pdf") as export_mock:
                export_mock.return_value = (os.path.join(temp_dir, "fake.pdf"), None)
                result = create_export_from_payload(
                    {
                        "urlsText": "https://example.com/1.jpg\nhttps://example.com/2.jpg",
                        "outputName": "demo",
                    },
                    temp_dir,
                )
        self.assertEqual(result["outputName"], "demo.pdf")
        self.assertEqual(result["totalPages"], 2)
        self.assertTrue(result["pdfPath"].endswith(".pdf"))
        export_mock.assert_called_once()

    def test_build_error_payload_keeps_failed_index_and_url(self) -> None:
        error = DownloadError(3, "https://example.com/3.jpg", "HTTP 404 while downloading")
        payload = _build_error_payload(error)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["failedIndex"], 3)
        self.assertEqual(payload["failedUrl"], "https://example.com/3.jpg")

    def test_create_collection_from_payload_returns_browser_result(self) -> None:
        with mock.patch("scribd_exporter.webapp.collect_from_browser") as collect_mock:
            collect_mock.return_value = {
                "title": "Demo",
                "totalPages": 1,
                "urlsText": "https://example.com/1.jpg",
                "pagesJson": [
                    {
                        "pageNumber": 1,
                        "imageUrl": "https://example.com/files/large/1.webp?1623194059",
                        "rawImageUrl": "./files/large/1.webp?1623194059",
                        "width": 100,
                        "height": 200,
                    }
                ],
                "stopReason": "max_steps",
                "stopDetails": "Reached configured maxSteps=220.",
                "stats": {"stepsRun": 220},
                "configUsed": {"maxSteps": 220},
            }
            result = create_collection_from_payload(
                {
                    "targetUrl": "https://example.com",
                    "collectorOptions": {
                        "mode": "paginate",
                        "nextButtonSelector": ".next",
                        "imageFilterPattern": "auto",
                        "pageNumberPattern": "auto",
                    },
                }
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["totalPages"], 1)
        self.assertEqual(result["stopReason"], "max_steps")
        self.assertEqual(result["pagesJson"][0]["rawImageUrl"], "./files/large/1.webp?1623194059")
        collect_mock.assert_called_once_with(
            "https://example.com",
            collector_options={
                "mode": "paginate",
                "nextButtonSelector": ".next",
                "imageFilterPattern": "auto",
                "pageNumberPattern": "auto",
            },
        )

    def test_build_error_payload_keeps_stage(self) -> None:
        error = BrowserCollectError("launch", "Chrome failed")
        payload = _build_error_payload(error)
        self.assertEqual(payload["stage"], "launch")

    def test_safe_output_name_appends_pdf(self) -> None:
        self.assertEqual(_safe_output_name(" report "), "report.pdf")


if __name__ == "__main__":
    unittest.main()
