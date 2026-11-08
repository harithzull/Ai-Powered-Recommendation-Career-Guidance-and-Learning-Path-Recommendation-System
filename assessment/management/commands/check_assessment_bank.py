from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from assessment.models import QuestionBank
from assessment.scoring import AssessmentError
from assessment.services import validate_bank


class Command(BaseCommand):
    help = "Check that a published or draft bank supplies balanced 18/36-item forms."

    def add_arguments(self, parser):
        parser.add_argument("--bank-version")

    def handle(self, *args, **options):
        bank = QuestionBank.objects.filter(version=options["bank_version"]).first() if options["bank_version"] else QuestionBank.objects.filter(status="active").first()
        if bank is None:
            raise CommandError("No matching question bank.")
        try:
            items = validate_bank(bank)
        except AssessmentError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"{bank.version}: {len(items)} active items; {dict(Counter(i.dimension for i in items))}; Quick=18, Detailed=36. Unvalidated instrument.")
