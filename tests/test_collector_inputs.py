import json
import os
import tempfile
import unittest

from scribd_exporter.collector import load_url_list, save_document_json
from scribd_exporter.models import CollectedDocument, PageImage


class CollectorInputTests(unittest.TestCase):
    def test_load_url_list_assigns_page_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "pages.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("https://example.com/1.jpg\n")
                handle.write("\n")
                handle.write("https://example.com/2.jpg\n")

            document = load_url_list(path, title="Example")

            self.assertEqual(document.title, "Example")
            self.assertEqual(document.total_pages, 2)
            self.assertEqual([page.page_number for page in document.pages], [1, 2])

    def test_save_document_json_writes_expected_shape(self) -> None:
        document = CollectedDocument(
            title="Demo",
            total_pages=1,
            pages=[PageImage(page_number=1, image_url="https://example.com/1.jpg", width=100, height=200)],
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "pages.json")
            save_document_json(document, path)

            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)

        self.assertEqual(payload["title"], "Demo")
        self.assertEqual(payload["totalPages"], 1)
        self.assertEqual(payload["pages"][0]["pageNumber"], 1)
        self.assertEqual(payload["pages"][0]["imageUrl"], "https://example.com/1.jpg")


if __name__ == "__main__":
    unittest.main()
