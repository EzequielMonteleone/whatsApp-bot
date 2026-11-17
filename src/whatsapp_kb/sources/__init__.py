from whatsapp_kb.plugins import load_entry_points
from whatsapp_kb.sources.pdf import PdfSource
from whatsapp_kb.sources.xlsx import XlsxSource

BUILTIN_SOURCES = (PdfSource, XlsxSource)


def default_sources() -> list[object]:
    sources: list[object] = [cls() for cls in BUILTIN_SOURCES]
    known = {type(source) for source in sources}
    for cls in load_entry_points("whatsapp_kb.sources"):
        if cls in known:
            continue
        sources.append(cls())
        known.add(cls)
    return sources
