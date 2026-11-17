from whatsapp_kb.textutil import fence
from whatsapp_kb.types import Hit


def build_prompt(system: str, hits: list[Hit], question: str) -> str:
    blocks = []
    for hit in hits:
        blocks.append(f'<chunk id="{hit.id}">\n{fence(hit.text)}\n</chunk>')
    context = "\n".join(blocks)
    return (
        f"{system.strip()}\n\n"
        f"<context>\n{context}\n</context>\n\n"
        f"<user_message>\n{fence(question)}\n</user_message>"
    )
