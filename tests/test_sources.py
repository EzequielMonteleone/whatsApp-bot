from pathlib import Path

import pytest
from openpyxl import Workbook
from pypdf import PdfWriter

from whatsapp_kb.sources.pdf import PdfSource
from whatsapp_kb.sources.xlsx import XlsxSource, row_text
from whatsapp_kb.textutil import split_text


def test_row_text_uses_headers():
    text = row_text(["Producto", "Precio", ""], ["Mesa", "$20", None])
    assert text == "Producto: Mesa. Precio: $20"


def test_xlsx_reads_rows_and_sheet_name(tmp_path: Path):
    book = Workbook()
    first = book.active
    first.title = "uno"
    first.append(["Nombre", "Valor"])
    first.append(["Alfa", "1"])
    second = book.create_sheet("dos")
    second.append(["Nombre", "Valor"])
    second.append(["Beta", "2"])
    path = tmp_path / "datos.xlsx"
    book.save(path)

    texts = XlsxSource().load(path)

    assert texts == [
        "Hoja: uno. Nombre: Alfa. Valor: 1",
        "Hoja: dos. Nombre: Beta. Valor: 2",
    ]


def test_xls_is_rejected(tmp_path: Path):
    path = tmp_path / "viejo.xls"
    path.write_bytes(b"no es un xlsx")
    with pytest.raises(ValueError):
        XlsxSource().load(path)


def test_blank_pdf_has_no_text(tmp_path: Path):
    path = tmp_path / "vacio.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    with path.open("wb") as handle:
        writer.write(handle)
    assert PdfSource().load(path) == []


def test_long_text_splits():
    parts = split_text("a\n" * 800, limit=100)
    assert len(parts) > 1
    assert all(len(part) <= 100 for part in parts)
