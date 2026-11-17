from collections.abc import Callable
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from whatsapp_kb.textutil import split_text

MIN_PAGE_CHARS = 20


class PdfSource:
    name = "pdf"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() == ".pdf"

    def load(self, path: Path, *, transcribe: Callable[[Path, int], str] | None = None) -> list[str]:
        reader = PdfReader(str(path))
        texts: list[str] = []
        for index, page in enumerate(reader.pages):
            extracted = page.extract_text() or ""
            if len(extracted.strip()) < MIN_PAGE_CHARS and transcribe is not None:
                extracted = transcribe(path, index)
            texts.extend(split_text(extracted))
        return texts

    @staticmethod
    def write_page(path: Path, index: int, directory: Path) -> Path:
        reader = PdfReader(str(path))
        writer = PdfWriter()
        writer.add_page(reader.pages[index])
        destination = directory / "page.pdf"
        with destination.open("wb") as handle:
            writer.write(handle)
        return destination
