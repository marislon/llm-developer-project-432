
from dataclasses import dataclass

from openpyxl import load_workbook


@dataclass
class XlsxBlock:
    text: str
    section: str
    page: int
    row: int


def parse_xlsx(file_path: str) -> list[XlsxBlock]:
    workbook = load_workbook(
        file_path,
        read_only=True,
        data_only=True,
    )

    blocks = []

    for sheet in workbook.worksheets:

        rows = sheet.iter_rows(values_only=True)
        headers = next(rows, None)

        if headers is None:
            continue

        headers = [
            str(value).strip() if value is not None else ""
            for value in headers
        ]


        for row_number, values in enumerate(rows, start=2):
            fields = [
                f"{header}: {value}"
                for header, value in zip(headers, values)
                if header and value is not None
            ]

            if not fields:
                continue


            blocks.append(
                XlsxBlock(
                    text="; ".join(fields),
                    section=sheet.title,
                    page=1,
                    row=row_number,
                )
            )


    workbook.close()
    return blocks
