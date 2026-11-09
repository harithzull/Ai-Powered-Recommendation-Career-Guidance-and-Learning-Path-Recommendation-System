"""Launch the private worker; this command never opens the ordinary ORM DB."""
import os
from pathlib import Path
import subprocess
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Evaluate synthetic profiles in an isolated in-memory subprocess (read-only catalog source).'
    requires_system_checks = []
    requires_migrations_checks = False

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100)
        parser.add_argument('--mode', choices=['both', 'quick', 'detailed'], default='both')
        parser.add_argument('--seed', type=int, default=42)
        parser.add_argument('--source-db', type=Path, help='Read-only SQLite catalog/bank source; defaults to configured SQLite file.')
        parser.add_argument('--output-dir', type=Path, default=Path('reports'))

    def handle(self, *args, **options):
        if not 1 <= options['count'] <= 10000:
            raise CommandError('count must be between 1 and 10000')
        source = options['source_db']
        if source is None:
            db = settings.DATABASES['default']
            if db['ENGINE'] != 'django.db.backends.sqlite3' or str(db['NAME']) == ':memory:' or str(db['NAME']).startswith('file:'):
                raise CommandError('Provide --source-db with a SQLite catalog/bank snapshot; the configured database is not a SQLite file.')
            source = Path(db['NAME'])
        try:
            source = source.resolve(strict=True)
        except OSError as exc:
            raise CommandError('Read-only SQLite catalog source does not exist.') from exc
        env = {k: v for k, v in os.environ.items() if not k.startswith(('DJANGO_', 'GROQ_', 'RECOMMENDATION_'))}
        env.update(DJANGO_SETTINGS_MODULE='careercoach.simulation_settings', DJANGO_READ_DOT_ENV='false',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONUTF8='1')
        command = [sys.executable, '-B', str(settings.BASE_DIR/'scripts/simulate_profiles.py'),
            '--count', str(options['count']), '--mode', options['mode'], '--seed', str(options['seed']),
            '--source-db', str(source), '--output-dir', str(options['output_dir'].resolve())]
        result = subprocess.run(command, env=env, cwd=settings.BASE_DIR)
        if result.returncode:
            raise CommandError(f'Isolated simulation failed (exit {result.returncode}); no ordinary database writes were performed.')
