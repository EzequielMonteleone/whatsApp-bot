from pathlib import Path

from openpyxl import load_workbook


def row_text(headers: list[str], values: list[object]) -> str:
    parts: list[str] = []
    for header, value in zip(headers, values):
        label = header.strip()
        if value is None:
            continue
        cell = str(value).strip()
        if not cell:
            continue
        parts.append(f"{label}: {cell}" if label else cell)
    return ". ".join(parts)


class XlsxSource:
    name = "xlsx"

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in {".xlsx", ".xls"}

    def load(self, path: Path, **_kwargs: object) -> list[str]:
        if path.suffix.lower() == ".xls":
            raise ValueError(f"{path.name} está en .xls. Guardalo como .xlsx.")
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            many_sheets = len(workbook.worksheets) > 1
            texts: list[str] = []
            for sheet in workbook.worksheets:
                rows = list(sheet.iter_rows(values_only=True))
                if not rows:
                    continue
                headers = ["" if cell is None else str(cell).strip() for cell in rows[0]]
                for values in rows[1:]:
                    line = row_text(headers, list(values))
                    if not line:
                        continue
                    if many_sheets:
                        line = f"Hoja: {sheet.title}. {line}"
                    texts.append(line)
            return texts
        finally:
            workbook.close()
