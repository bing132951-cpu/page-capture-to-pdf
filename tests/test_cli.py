import unittest

from scribd_exporter.cli import build_parser, _collector_options_from_args


class CliTests(unittest.TestCase):
    def test_collect_parser_accepts_paginate_arguments(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "collect",
                "--target-url",
                "https://example.com/book",
                "--output",
                "output/pages.json",
                "--mode",
                "paginate",
                "--next-button-selector",
                ".flip_button_right.button",
                "--page-indicator-selector",
                ".page-count",
                "--max-pages",
                "30",
                "--click-delay-ms",
                "1200",
                "--max-unchanged-steps",
                "4",
            ]
        )

        options = _collector_options_from_args(args)
        self.assertEqual(options["mode"], "paginate")
        self.assertEqual(options["nextButtonSelector"], ".flip_button_right.button")
        self.assertEqual(options["pageIndicatorSelector"], ".page-count")
        self.assertEqual(options["maxPages"], 30)
        self.assertEqual(options["clickDelayMs"], 1200)
        self.assertEqual(options["maxUnchangedSteps"], 4)


if __name__ == "__main__":
    unittest.main()
