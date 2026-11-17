import logging
from importlib.metadata import entry_points

logger = logging.getLogger("whatsapp_kb")


def load_entry_points(group: str) -> list[type]:
    try:
        selected = entry_points().select(group=group)
    except Exception:
        return []
    loaded: list[type] = []
    for item in selected:
        try:
            loaded.append(item.load())
        except Exception:
            logger.exception("no se pudo cargar %s", getattr(item, "name", group))
    return loaded
