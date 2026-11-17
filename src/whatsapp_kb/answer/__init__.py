from whatsapp_kb.answer.guards import AmountGuard, CitationGuard
from whatsapp_kb.plugins import load_entry_points


def default_guards() -> list:
    guards: list = [AmountGuard(), CitationGuard()]
    known = {type(guard) for guard in guards}
    for cls in load_entry_points("whatsapp_kb.guards"):
        if cls in known:
            continue
        guards.append(cls())
        known.add(cls)
    return guards
