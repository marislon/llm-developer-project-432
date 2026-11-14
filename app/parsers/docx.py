from dataclasses import dataclass

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


@dataclass
class DocxBlock:
    text: str
    section: str

    page: int



def parse_docx(file_path: str) -> list[DocxBlock]:
    document = Document(file_path)
    blocks = []


    for block in document.iter_inner_content():
        if isinstance(block, Paragraph):

            text = block.text.strip()

            if text:
                blocks.append(
                    DocxBlock(
                        text=text,
                        section="paragraph",
                        page=1,
                    )
                )

        elif isinstance(block, Table):
            table = block

            headers = [cell.text.strip() for cell in table.rows[0].cells]

            for row in table.rows[1:]:
                values = [cell.text.strip() for cell in row.cells]

                text = "; ".join(
                    f"{header}: {value}"
                    for header, value in zip(headers, values)
                )

                blocks.append(
                    DocxBlock(
                        text=text,
                        section="table",
                        page=1,
                    )
                )

    return blocks
