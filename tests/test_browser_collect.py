import unittest
from unittest import mock

from scribd_exporter.browser_collect import (
    BrowserCollectError,
    collect_from_browser,
    normalize_collector_options,
)


class BrowserCollectTests(unittest.TestCase):
    def test_collect_from_browser_returns_payload(self) -> None:
        fake_payload = {
            "title": "Demo",
            "totalPages": 2,
            "urlsText": (
                "https://example.com/files/large/1.webp?1623194059\n"
                "https://example.com/files/large/2.webp?1623194059"
            ),
            "pagesJson": [
                {
                    "pageNumber": 1,
                    "imageUrl": "https://example.com/files/large/1.webp?1623194059",
                    "rawImageUrl": "./files/large/1.webp?1623194059",
                    "width": 900,
                    "height": 1200,
                },
                {
                    "pageNumber": 2,
                    "imageUrl": "https://example.com/files/large/2.webp?1623194059",
                    "rawImageUrl": "./files/large/2.webp?1623194059",
                    "width": 900,
                    "height": 1200,
                },
            ],
            "stopReason": "no_new_limit",
            "stopDetails": "Stopped after 18 consecutive no-new cycles.",
            "stats": {"stepsRun": 42},
            "configUsed": {"maxSteps": 220},
        }

        fake_client = mock.Mock()
        fake_client.send.side_effect = [
            {},
            {},
            {"result": {"value": fake_payload}},
        ]

        with mock.patch("scribd_exporter.browser_collect.launch_debug_chrome") as launcher:
            launcher.return_value.__enter__.return_value = {"web_socket_debugger_url": "ws://127.0.0.1/devtools/page/1"}
            launcher.return_value.__exit__.return_value = False
            with mock.patch("scribd_exporter.browser_collect.CdpClient", return_value=fake_client):
                with mock.patch("scribd_exporter.browser_collect._wait_for_page_ready"):
                    result = collect_from_browser("https://example.com")

        self.assertEqual(result["totalPages"], 2)
        self.assertIn("https://example.com/files/large/1.webp?1623194059", result["urlsText"])
        self.assertEqual(result["stopReason"], "no_new_limit")
        self.assertEqual(result["pagesJson"][0]["rawImageUrl"], "./files/large/1.webp?1623194059")

    def test_collect_from_browser_raises_stage_error_for_empty_payload(self) -> None:
        fake_client = mock.Mock()
        fake_client.send.side_effect = [{}, {}, {"result": {"value": {"title": "Demo", "totalPages": 0}}}]

        with mock.patch("scribd_exporter.browser_collect.launch_debug_chrome") as launcher:
            launcher.return_value.__enter__.return_value = {"web_socket_debugger_url": "ws://127.0.0.1/devtools/page/1"}
            launcher.return_value.__exit__.return_value = False
            with mock.patch("scribd_exporter.browser_collect.CdpClient", return_value=fake_client):
                with mock.patch("scribd_exporter.browser_collect._wait_for_page_ready"):
                    with self.assertRaises(BrowserCollectError) as error:
                        collect_from_browser("https://example.com")
        self.assertEqual(error.exception.stage, "collect")

    def test_normalize_collector_options_uses_auto_patterns_by_default(self) -> None:
        options = normalize_collector_options(
            {
                "imageFilterPattern": "   ",
                "pageNumberPattern": "",
                "maxSteps": "12",
                "delayMs": "150",
            }
        )
        self.assertEqual(options["imageFilterPattern"], "auto")
        self.assertEqual(options["pageNumberPattern"], "auto")
        self.assertEqual(options["maxSteps"], 12)
        self.assertEqual(options["delayMs"], 150)

    def test_normalize_collector_options_requires_selector_for_paginate_mode(self) -> None:
        with self.assertRaises(ValueError):
            normalize_collector_options({"mode": "paginate"})

    def test_normalize_collector_options_keeps_paginate_settings(self) -> None:
        options = normalize_collector_options(
            {
                "mode": "paginate",
                "nextButtonSelector": ".next",
                "pageIndicatorSelector": ".pager",
                "maxPages": "20",
                "clickDelayMs": "900",
                "maxUnchangedSteps": "4",
            }
        )
        self.assertEqual(options["mode"], "paginate")
        self.assertEqual(options["nextButtonSelector"], ".next")
        self.assertEqual(options["pageIndicatorSelector"], ".pager")
        self.assertEqual(options["maxPages"], 20)
        self.assertEqual(options["clickDelayMs"], 900)
        self.assertEqual(options["maxUnchangedSteps"], 4)


if __name__ == "__main__":
    unittest.main()
