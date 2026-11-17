import re
from decimal import Decimal, InvalidOperation

_CURRENCY = r"(?:USD|ARS|EUR|U\$S|€|\$)"
_NUMBER = r"(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\d+[.,]\d+|\d+)"
AMOUNT = re.compile(
    rf"(?:{_CURRENCY})\s*{_NUMBER}|\d{{1,3}}(?:\.\d{{3}})+(?:,\d{{1,2}})?|\d{{1,3}}(?:,\d{{3}})+(?:\.\d{{1,2}})?"
)
INTEGER = re.compile(r"(?<!\d)(\d{2,})(?!\d)")
URL = re.compile(r"https?://[^\s<>'\"]+|www\.[^\s<>'\"]+", re.IGNORECASE)
EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)\+?(?:\d[\s().-]*){7,}\d(?!\d)")
_PREFIX = re.compile(rf"^(?:{_CURRENCY})\s*", re.IGNORECASE)


def _parse_number(raw: str) -> Decimal | None:
    cleaned = _PREFIX.sub("", raw).strip()
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", cleaned):
        return None
    if "." in cleaned and "," in cleaned:
        decimal = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        cleaned = cleaned.replace(thousands, "").replace(decimal, ".")
    elif "," in cleaned or "." in cleaned:
        separator = "," if "," in cleaned else "."
        parts = cleaned.split(separator)
        if all(len(part) == 3 for part in parts[1:]):
            cleaned = "".join(parts)
        elif len(parts[-1]) <= 2:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
        else:
            cleaned = "".join(parts)
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _values(text: str) -> list[Decimal] | None:
    found: list[Decimal] = []
    for match in AMOUNT.finditer(text):
        value = _parse_number(match.group())
        if value is None:
            return None
        found.append(value)
    return found


def _covered(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start >= left and end <= right for left, right in spans)


def _token(text: str, token: str) -> bool:
    return re.search(rf"(?<!\d){re.escape(token)}(?!\d)", text) is not None


def _digit_run(text: str, digits: str) -> bool:
    if not digits:
        return False
    gap = r"[\s().+\-]*"
    pattern = r"(?<!\d)" + gap.join(re.escape(digit) for digit in digits) + r"(?!\d)"
    return re.search(pattern, text) is not None


class AmountGuard:
    name = "amounts"

    def allow(self, text: str, cited: str) -> bool:
        reply = _values(text)
        known = _values(cited)
        if reply is None or known is None:
            return False
        return all(value in known for value in reply)


class CitationGuard:
    name = "citations"

    def allow(self, text: str, cited: str) -> bool:
        cited_folded = cited.casefold()
        for match in URL.finditer(text):
            url = match.group().rstrip(".,);]")
            if url.casefold() not in cited_folded:
                return False
        for match in EMAIL.finditer(text):
            if match.group().casefold() not in cited_folded:
                return False
        phone_spans = [match.span() for match in PHONE.finditer(text)]
        for match in PHONE.finditer(text):
            digits = re.sub(r"\D", "", match.group())
            if not _digit_run(cited, digits):
                return False
        amount_spans = [match.span() for match in AMOUNT.finditer(text)]
        for match in INTEGER.finditer(text):
            if _covered(match.span(), amount_spans) or _covered(match.span(), phone_spans):
                continue
            if not _token(cited, match.group(1)):
                return False
        return True
