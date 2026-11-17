from importlib.metadata import PackageNotFoundError, version

from whatsapp_kb.bot import KnowledgeBot
from whatsapp_kb.types import Outcome

__all__ = ["KnowledgeBot", "Outcome"]
try:
    __version__ = version("whatsapp-kb")
except PackageNotFoundError:
    __version__ = "0.1.0"
