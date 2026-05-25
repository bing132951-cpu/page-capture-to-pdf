import unittest

from scribd_exporter.url_input import UrlInputError, parse_urls_text


class UrlInputTests(unittest.TestCase):
    def test_parse_urls_text_preserves_order_and_ignores_blank_lines(self) -> None:
        document = parse_urls_text("https://example.com/1.jpg\n\nhttps://example.com/2.jpeg\n", title="Demo")

        self.assertEqual(document.title, "Demo")
        self.assertEqual(document.total_pages, 2)
        self.assertEqual([page.page_number for page in document.pages], [1, 2])
        self.assertEqual(document.pages[1].image_url, "https://example.com/2.jpeg")

    def test_parse_urls_text_rejects_non_jpeg_url(self) -> None:
        with self.assertRaises(UrlInputError) as error:
            parse_urls_text("https://example.com/image.png")
        self.assertIn(".jpg/.jpeg", str(error.exception))


if __name__ == "__main__":
    unittest.main()
