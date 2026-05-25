from typing import Callable, Optional, Tuple

from .downloader import download_page_image
from .models import CollectedDocument
from .pdf_writer import write_pdf_from_jpegs


def export_document_pdf(
    output_path: str,
    document: Optional[CollectedDocument] = None,
    work_dir: str = "output/downloads",
    logger: Optional[Callable[[str], None]] = None,
) -> Tuple[str, CollectedDocument]:
    if document is None:
        raise ValueError("A parsed document is required for export.")

    _validate_document(document)
    if logger is not None:
        logger(f"Downloading {document.total_pages} page image(s) into {work_dir}")
    image_paths = [_download_with_logging(page, work_dir, logger=logger) for page in document.pages]
    if logger is not None:
        logger(f"Writing PDF to {output_path}")
    write_pdf_from_jpegs(image_paths, output_path)
    return output_path, document


def _validate_document(document: CollectedDocument) -> None:
    expected = list(range(1, document.total_pages + 1))
    actual = [page.page_number for page in document.pages]
    if actual != expected:
        raise RuntimeError(
            f"Collected pages are not continuous. Expected {expected[:3]}...{expected[-3:]}, got {actual[:3]}...{actual[-3:]}"
        )
    if any(not page.image_url for page in document.pages):
        raise RuntimeError("One or more pages are missing image URLs.")


def _download_with_logging(page, work_dir: str, logger: Optional[Callable[[str], None]]) -> str:
    if logger is not None:
        logger(f"Downloading page {page.page_number}: {page.image_url}")
    return download_page_image(page, work_dir)
