from dataclasses import dataclass

import pymupdf


@dataclass
class PdfPage:
    text: str
    page: int


def parse_pdf(file_path: str) -> list[PdfPage]:
    pages = []

    with pymupdf.open(file_path) as document:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text")

            pages.append(
                PdfPage(
                    text=text,
                    page=page_number,
                )
            )

    return pages
