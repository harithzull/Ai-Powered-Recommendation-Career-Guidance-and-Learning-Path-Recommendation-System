"""Backward-compatible command name with non-destructive import semantics."""
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from recommender.data_import import ImportRejected, import_tables
from recommender.datasets import read_tables


class Command(BaseCommand):
    help = "Validate and upsert ESCO-derived export records, preserving IDs and enrichment. Never deletes catalog rows."

    def add_arguments(self, parser):
        parser.add_argument("--data-dir", type=Path, default=settings.BASE_DIR / "data")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--source-version", help="Only supply a version verified from the original extraction.")
        parser.add_argument("--format", choices=["text", "json"], default="text")
        parser.add_argument("--output", type=Path)
        parser.add_argument("--replace-existing", action="store_true", help="Removed unsafe option: always rejected.")

    def handle(self, *args, **options):
        if options["replace_existing"]:
            raise CommandError("Destructive replacement is no longer supported. Use the idempotent importer, optionally with --dry-run.")
        failure = None
        try:
            report = import_tables(read_tables(options["data_dir"]), dry_run=options["dry_run"], source_version=options["source_version"])
        except ImportRejected as exc:
            report, failure = exc.report, str(exc)
        except (ValidationError, IntegrityError) as exc:
            # All import writes run in one atomic block and have rolled back.
            report = {"errors": [{"message": str(exc)}], "rolled_back": True}
            failure = "Import validation failed; the complete transaction was rolled back."
        if options["format"] == "json":
            result = json.dumps(report, ensure_ascii=False, indent=2)
        else:
            lines = ["CareerCoach import: " + ("DRY RUN (rolled back)" if options["dry_run"] else "non-destructive upsert")]
            for kind, counts in report.get("counts", {}).items():
                lines.append(kind + ": " + ", ".join(f"{key}={value}" for key, value in counts.items()))
            lines += ["ERROR: " + json.dumps(error, ensure_ascii=False) for error in report.get("errors", [])]
            if report.get("embedding_rebuild_required"):
                lines.append("New canonical skills were inserted: build_skill_vectors is required before using them in matching.")
            result = "\n".join(lines)
        if options["output"]:
            options["output"].parent.mkdir(parents=True, exist_ok=True)
            options["output"].write_text(result + "\n", encoding="utf-8")
        else:
            self.stdout.write(result)
        if failure:
            raise CommandError(failure)
