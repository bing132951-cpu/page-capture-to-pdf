import base64
import os
import tempfile
import unittest

from scribd_exporter.pdf_writer import write_pdf_from_jpegs
from fixtures import JPEG_BASE64


class PdfWriterTests(unittest.TestCase):
    def test_write_pdf_from_jpegs_creates_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = os.path.join(temp_dir, "page-0001.jpg")
            pdf_path = os.path.join(temp_dir, "output.pdf")

            with open(image_path, "wb") as handle:
                handle.write(base64.b64decode(JPEG_BASE64))

            write_pdf_from_jpegs([image_path], pdf_path)

            self.assertTrue(os.path.exists(pdf_path))
            with open(pdf_path, "rb") as handle:
                content = handle.read()
            self.assertTrue(content.startswith(b"%PDF-1.4"))


if __name__ == "__main__":
    unittest.main()
