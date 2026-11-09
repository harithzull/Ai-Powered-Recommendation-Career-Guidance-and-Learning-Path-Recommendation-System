from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from resume.models import ResumeDocument
from resume.storage import remove_file


class Command(BaseCommand):
    help = 'Recover stale failed/incomplete uploads without printing names, paths or text.'

    def handle(self, *args, **options):
        cutoff = timezone.now()-timedelta(minutes=30)
        recovered = failed = 0
        for document in ResumeDocument.objects.filter(status__in=['pending', 'processing', 'failed'], updated_at__lt=cutoff):
            try:
                remove_file(document)
                ResumeDocument.objects.filter(pk=document.pk).update(status='failed', file_retained=False,
                    extracted_text='', error_code='interrupted', updated_at=timezone.now())
                recovered += 1
            except Exception:
                failed += 1
        self.stdout.write(f'Recovered records: {recovered}; retry required: {failed}')
        if failed:
            raise CommandError('Some private files require a cleanup retry.')
