from pathlib import Path


def test_library_source_has_no_business_copy():
    root = Path(__file__).resolve().parents[1] / "src"
    text = "\n".join(path.read_text(encoding="utf-8").lower() for path in root.rglob("*.py"))
    assert "pasteler" not in text
    assert "bueti" not in text
