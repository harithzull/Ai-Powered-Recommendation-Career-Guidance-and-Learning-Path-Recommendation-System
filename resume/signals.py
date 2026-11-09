from django.db.models.signals import pre_delete
from django.dispatch import receiver

from .models import ResumeDocument
from .storage import remove_file


@receiver(pre_delete, sender=ResumeDocument)
def delete_private_original(sender, instance, **kwargs):
    # Raising aborts the DB deletion instead of leaving an untracked private file.
    # Applies to account cascades and queryset deletes as well as the owner view.
    remove_file(instance)
