"""Read the project's CSV interchange format without mutating the database."""
import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path


FILES = {
    "careers": ("careers_clean (1).csv", {"title", "industry", "summary", "description", "work_environment"}),
    "skills": ("skills_clean (1).csv", {"name", "description", "category"}),
    "relationships": ("career_skills_clean (1).csv", {"career", "skill", "skill_type", "required_level", "importance", "is_core"}),
}


@dataclass
class Row:
    values: dict
    line: int


@dataclass
class Table:
    filename: str
    sha256: str = ""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def read_tables(directory):
    tables = {}
    for kind, (filename, required) in FILES.items():
        table = tables[kind] = Table(filename)
        path = Path(directory) / filename
        try:
            table.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                table.columns = reader.fieldnames or []
                if len(set(table.columns)) != len(table.columns) or not required.issubset(table.columns):
                    table.errors.append({"line": 1, "message": "Missing or duplicate CSV columns", "required": sorted(required)})
                    continue
                for record in reader:
                    if None in record or any(value is None for value in record.values()):
                        table.errors.append({"line": reader.line_num, "message": "CSV row width differs from header"})
                    else:
                        table.rows.append(Row(record, reader.line_num))
                if not table.rows:
                    table.errors.append({"line": 1, "message": "CSV contains no records"})
        except (OSError, UnicodeError, csv.Error) as exc:
            table.errors.append({"line": None, "message": f"Cannot read CSV ({type(exc).__name__})"})
    return tables
