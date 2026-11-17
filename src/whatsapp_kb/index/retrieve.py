from whatsapp_kb.types import Hit


def pack_hits(hits: list[Hit], *, top_k: int, max_context_tokens: int) -> list[Hit]:
    ranked = sorted(hits, key=lambda hit: hit.distance)
    budget = max_context_tokens * 4
    chosen: list[Hit] = []
    used = 0
    for hit in ranked[:top_k]:
        room = budget - used
        if chosen and room <= 0:
            break
        excerpt = hit.text if len(hit.text) <= room else hit.text[:room]
        if not excerpt:
            break
        chosen.append(Hit(id=hit.id, path=hit.path, text=excerpt, distance=hit.distance))
        used += len(excerpt)
    return chosen
