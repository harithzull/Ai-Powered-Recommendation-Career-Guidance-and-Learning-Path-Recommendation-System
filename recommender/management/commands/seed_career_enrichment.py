import json

from django.core.management.base import BaseCommand

from recommender.curation import seed_examples


class Command(BaseCommand):
    help = "Seed editable CareerCoach families and explicit, documented examples; never overwrite existing curation."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(seed_examples(dry_run=options["dry_run"]), indent=2))
