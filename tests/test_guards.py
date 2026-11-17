from whatsapp_kb.answer.decision import parse_decision
from whatsapp_kb.answer.guards import AmountGuard


def test_parse_decision_reads_json_inside_extra_text():
    decision = parse_decision('listo\n{"action":"answer","text":"Hola","chunk_ids":["a"]}\n')
    assert decision is not None
    assert decision.action == "answer"
    assert decision.chunk_ids == ["a"]


def test_amount_must_appear_in_the_cited_text():
    guard = AmountGuard()
    assert guard.allow("Sale $1000.", "Precio: $1000")
    assert guard.allow("Sale $1.000.", "Precio: $1000")
    assert guard.allow("Sale $10,00.", "Precio: $10.00")
    assert not guard.allow("Sale $9999.", "Precio: $1000")
    assert not guard.allow("Sale $10.00.", "Precio: $1000")


def test_plain_numbers_links_and_phones_must_be_cited():
    from whatsapp_kb.answer.guards import CitationGuard

    guard = CitationGuard()
    cited = "Precio: $1000. Anticipación: 48 horas. Mail: hola@ejemplo.test. Tel: 5491126467590."
    assert guard.allow("Sale $1000. Pedilo con 48 horas.", cited)
    assert not guard.allow("Sale 9999.", cited)
    assert not guard.allow("Son 480 horas.", "Son 48 horas.")
    assert not guard.allow("Mirá https://evil.test", cited)
    assert guard.allow("Escribí a hola@ejemplo.test", cited)
    assert not guard.allow("Escribí a otro@evil.test", cited)
    assert guard.allow("Tel 5491126467590", cited)
    assert not guard.allow("Tel 5491100000000", cited)
