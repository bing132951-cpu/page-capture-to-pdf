from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional


@dataclass
class PageImage:
    page_number: int
    image_url: str
    width: Optional[int] = None
    height: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return {
            "pageNumber": data["page_number"],
            "imageUrl": data["image_url"],
            "width": data["width"],
            "height": data["height"],
        }


@dataclass
class CollectedDocument:
    title: str
    total_pages: int
    pages: List[PageImage]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "totalPages": self.total_pages,
            "pages": [page.to_dict() for page in self.pages],
        }

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "CollectedDocument":
        pages = [
            PageImage(
                page_number=int(item["pageNumber"]),
                image_url=item["imageUrl"],
                width=item.get("width"),
                height=item.get("height"),
            )
            for item in value["pages"]
        ]
        return cls(
            title=value.get("title", "Untitled document"),
            total_pages=int(value["totalPages"]),
            pages=pages,
        )
