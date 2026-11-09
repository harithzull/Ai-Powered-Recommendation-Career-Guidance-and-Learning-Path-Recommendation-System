from pathlib import Path
from django.conf import settings
from django.core.checks import Error, register


@register()
def private_resume_storage(app_configs, **kwargs):
    private = Path(settings.PRIVATE_RESUME_ROOT).resolve()
    public = [getattr(settings, 'STATIC_ROOT', None), getattr(settings, 'MEDIA_ROOT', None),
              *getattr(settings, 'STATICFILES_DIRS', [])]
    for root in filter(None, public):
        if isinstance(root, (tuple, list)):
            root = root[1]
        public_root = Path(root).resolve()
        if private == public_root or private.is_relative_to(public_root):
            return [Error('Private resume storage must be outside public media/static directories.', id='resume.E001')]
    return []
