from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from assessment.models import InterestItem, QuestionBank


class Command(BaseCommand):
    help = "Copy a bank into a new draft version for review; existing questions and sessions stay unchanged."

    def add_arguments(self, parser):
        parser.add_argument("source_version")
        parser.add_argument("new_version")

    @transaction.atomic
    def handle(self, *args, **options):
        source = QuestionBank.objects.filter(version=options["source_version"]).first()
        if source is None:
            raise CommandError("Source bank not found.")
        target = QuestionBank(version=options["new_version"], notes=f"Draft revision of {source.version}. Requires content review and future empirical validation.")
        try:
            target.full_clean()
        except ValidationError as exc:
            raise CommandError("Invalid or already existing target bank version.") from exc
        target.save()
        InterestItem.objects.bulk_create([InterestItem(bank=target, code=item.code, dimension=item.dimension,
            facet=item.facet, purpose=item.purpose, text=item.text, status=item.status, quick_core=item.quick_core)
            for item in source.items.all()])
        self.stdout.write(f"Created draft {target.version}. Review its items, check coverage, then publish explicitly.")
