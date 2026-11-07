from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import SecurityCounter


class Command(BaseCommand):
    help = "Remove expired rate counters and work leases. Schedule daily."

    def handle(self, *args, **options):
        count, _ = SecurityCounter.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Removed {count} expired counters.")
