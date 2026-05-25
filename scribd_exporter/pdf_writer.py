import os
import struct
from typing import Iterable, List, Tuple


class PdfWriterError(RuntimeError):
    """Raised when an image cannot be embedded into the output PDF."""


def write_pdf_from_jpegs(image_paths: Iterable[str], output_path: str) -> None:
    images = [_read_jpeg(path) for path in image_paths]
    if not images:
        raise PdfWriterError("No images were provided for PDF export.")

    objects: List[bytes] = []
    page_ids: List[int] = []
    pages_root_id = 2

    for image in images:
        image_id = len(objects) + 3
        contents_id = image_id + 1
        page_id = image_id + 2
        page_ids.append(page_id)
        objects.append(_image_object(image["data"], image["width"], image["height"]))
        objects.append(_content_object(image["width"], image["height"]))
        objects.append(
            _page_object(
                pages_root_id,
                image_id,
                contents_id,
                image["width"],
                image["height"],
            )
        )

    pages_object = _pages_object(page_ids)
    catalog_object = _catalog_object(pages_root_id)

    numbered_objects = [catalog_object, pages_object] + objects
    pdf = _assemble_pdf(numbered_objects)

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "wb") as handle:
        handle.write(pdf)


def _assemble_pdf(objects: List[bytes]) -> bytes:
    chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
    offsets = [0]
    current = len(chunks[0])
    for index, obj in enumerate(objects, start=1):
        offsets.append(current)
        entry = f"{index} 0 obj\n".encode("ascii") + obj + b"\nendobj\n"
        chunks.append(entry)
        current += len(entry)

    xref_offset = current
    xref = [f"xref\n0 {len(objects) + 1}\n".encode("ascii")]
    xref.append(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))

    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    return b"".join(chunks + xref + [trailer])


def _catalog_object(pages_root_id: int) -> bytes:
    return f"<< /Type /Catalog /Pages {pages_root_id} 0 R >>".encode("ascii")


def _pages_object(page_ids: List[int]) -> bytes:
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    return f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("ascii")


def _content_object(width: int, height: int) -> bytes:
    stream = f"q\n{width} 0 0 {height} 0 0 cm\n/Im0 Do\nQ\n".encode("ascii")
    return f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"


def _page_object(
    pages_root_id: int,
    image_id: int,
    contents_id: int,
    width: int,
    height: int,
) -> bytes:
    return (
        f"<< /Type /Page /Parent {pages_root_id} 0 R "
        f"/MediaBox [0 0 {width} {height}] "
        f"/Resources << /XObject << /Im0 {image_id} 0 R >> >> "
        f"/Contents {contents_id} 0 R >>".encode("ascii")
    )


def _image_object(data: bytes, width: int, height: int) -> bytes:
    header = (
        f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
        f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(data)} >>\nstream\n"
    ).encode("ascii")
    return header + data + b"\nendstream"


def _read_jpeg(path: str) -> dict:
    with open(path, "rb") as handle:
        data = handle.read()
    width, height = _jpeg_size(data)
    return {"path": path, "data": data, "width": width, "height": height}


def _jpeg_size(data: bytes) -> Tuple[int, int]:
    if data[:2] != b"\xff\xd8":
        raise PdfWriterError("Only JPEG images are supported by the built-in PDF writer.")

    offset = 2
    while offset < len(data):
        if data[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(data) and data[offset] == 0xFF:
            offset += 1
        if offset >= len(data):
            break
        marker = data[offset]
        offset += 1

        if marker in (0xD8, 0xD9):
            continue
        if offset + 2 > len(data):
            break
        segment_length = struct.unpack(">H", data[offset : offset + 2])[0]
        if segment_length < 2:
            raise PdfWriterError("Invalid JPEG segment encountered.")
        segment_start = offset + 2
        segment_end = offset + segment_length
        if segment_end > len(data):
            raise PdfWriterError("Truncated JPEG file encountered.")

        if marker in {
            0xC0,
            0xC1,
            0xC2,
            0xC3,
            0xC5,
            0xC6,
            0xC7,
            0xC9,
            0xCA,
            0xCB,
            0xCD,
            0xCE,
            0xCF,
        }:
            if segment_start + 5 > len(data):
                raise PdfWriterError("Invalid JPEG frame header.")
            height = struct.unpack(">H", data[segment_start + 1 : segment_start + 3])[0]
            width = struct.unpack(">H", data[segment_start + 3 : segment_start + 5])[0]
            return width, height

        offset = segment_end

    raise PdfWriterError("Unable to determine JPEG dimensions.")
