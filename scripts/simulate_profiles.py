"""Private offline worker; prefer `manage.py simulate_profiles` as the entrypoint."""
import argparse
import hashlib
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from time import perf_counter
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'careercoach.simulation_settings'
os.environ['DJANGO_READ_DOT_ENV'] = 'false'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--count', type=int, default=100)
    parser.add_argument('--mode', choices=['quick', 'detailed', 'both'], default='both')
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--source-db', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=Path('reports'))
    args = parser.parse_args()
    if not 1 <= args.count <= 10000:
        parser.error('count must be between 1 and 10000')
    started = perf_counter()
    def source_hashes():
        # Hashes only, never export user data. Include WAL if present so a
        # concurrent application write cannot pass as an unchanged snapshot.
        return {suffix: hashlib.sha256(Path(str(args.source_db)+suffix).read_bytes()).hexdigest()
                for suffix in ('', '-wal') if Path(str(args.source_db)+suffix).is_file()}
    def no_network(*a, **kw):
        raise AssertionError('External network access is forbidden in simulation')
    with patch('socket.socket.connect', no_network), patch('socket.socket.connect_ex', no_network), \
         patch('socket.create_connection', no_network), patch('socket.getaddrinfo', no_network):
        import django
        django.setup()
        from django.core.management import call_command
        from django.db import connections
        from recommender.simulation.catalog import fingerprints, install_snapshot, read_snapshot, require_isolation
        from recommender.simulation.runner import execute
        from recommender.simulation.reports import export_reports, validate_output_paths
        try:
            require_isolation()
            validate_output_paths(args.output_dir, args.source_db)
            file_hashes = source_hashes()
            snapshot = read_snapshot(args.source_db)
            before = fingerprints(snapshot)
            call_command('migrate', verbosity=0, interactive=False)
            install_snapshot(snapshot)
            profiles, runs, checks = execute(count=args.count, mode=args.mode, seed=args.seed,
                                             progress=lambda line: print(line, flush=True))
            after = fingerprints(read_snapshot(args.source_db))
            if before != after or file_hashes != source_hashes():
                raise AssertionError('Source database changed during simulation (possibly another process); results not exported')
            checks['source_catalog_unchanged'] = True
            checks['source_database_bytes_unchanged'] = True
            validate_output_paths(args.output_dir, args.source_db)
            export_reports(args.output_dir.resolve(), profiles, runs, checks, metadata={
                'seed': args.seed, 'requested_mode': args.mode, 'fingerprints': before,
                'catalog_counts': {key: len(rows) for key, rows in snapshot.items()},
                'test_date': datetime.now(timezone.utc).isoformat(), 'total_execution_seconds': perf_counter()-started,
                'source': 'read-only SQLite catalog and active assessment bank',
                'isolation': 'dedicated subprocess; SQLite :memory:; no users/sessions copied; connections closed on exit',
                'network': 'blocked; semantic proposals disabled; no Groq calls'})
            print(f'Reports written to {args.output_dir.resolve()}', flush=True)
        finally:
            connections.close_all()


if __name__ == '__main__':
    main()
