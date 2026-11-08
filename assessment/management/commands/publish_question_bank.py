from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from assessment.models import QuestionBank
from assessment.scoring import AssessmentError
from assessment.services import validate_bank


class Command(BaseCommand):
    help = "Validate and publish a draft bank version, retiring the previous active version."

    def add_arguments(self, parser):
        parser.add_argument("version")

    @transaction.atomic
    def handle(self, *args, **options):
        bank = QuestionBank.objects.select_for_update().filter(version=options["version"]).first()
        if bank is None or bank.status != "draft":
            raise CommandError("Publish a new draft version; existing published versions are immutable.")
        try:
            validate_bank(bank)
        except AssessmentError as exc:
            raise CommandError(str(exc)) from exc
        QuestionBank.objects.filter(status="active").update(status="retired")
        bank.status = "active"
        bank.save(update_fields=["status"])
        self.stdout.write(f"Published {bank.version}. Existing sessions keep their frozen question sets.")
