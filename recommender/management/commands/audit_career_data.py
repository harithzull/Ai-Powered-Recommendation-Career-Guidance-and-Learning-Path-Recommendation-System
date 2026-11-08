import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from recommender.data_audit import audit_tables
from recommender.datasets import read_tables


class Command(BaseCommand):
    help = "Audit career/skill CSV datasets without modifying them or database records."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", type=Path, default=settings.BASE_DIR / "data")
        parser.add_argument("--format", choices=["text", "json"], default="text")
        parser.add_argument("--output", type=Path)
        parser.add_argument("--max-examples", type=int, default=20, help="Examples per warning; 0 includes every record.")
        parser.add_argument("--fail-on-errors", action="store_true")
        parser.add_argument("--database", action="store_true", help="Audit persisted source/enrichment records instead of CSVs.")

    def handle(self, *args, **options):
        if options["max_examples"] < 0:
            raise CommandError("--max-examples must be nonnegative")
        if options["database"]:
            from recommender.knowledge_audit import audit_database
            report = audit_database(options["max_examples"])
        else:
            report = audit_tables(read_tables(options["data_dir"]), options["max_examples"])
        if options["format"] == "json":
            result = json.dumps(report, ensure_ascii=False, indent=2)
        else:
            lines = ["CareerCoach dataset audit (read-only)",
                     "Counts: " + ", ".join(f"{key}={value}" for key, value in report["counts"].items()),
                     "Finding instances: " + ", ".join(f"{key}={value}" for key, value in report["finding_counts"].items())]
            lines += [f"[{f['category']}] {f['table']}.{f['code']}: {f['count']} — {f['suggested_action']}" for f in report["findings"]]
            result = "\n".join(lines)
        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(result + "\n", encoding="utf-8")
        else:
            self.stdout.write(result)
        if options["fail_on_errors"] and report["finding_counts"]["error"]:
            raise CommandError("Confirmed dataset errors found; see audit report.")
