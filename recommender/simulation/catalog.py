"""Read only public catalog/bank tables; never copy application users or sessions."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction

from assessment.models import InterestItem, QuestionBank
from recommender.engine.fingerprint import digest
from recommender.models import Career, CareerEnrichment, CareerFamily, CareerSkill, Skill, SkillAlias

CATALOG_MODELS = (CareerFamily, Career, Skill, CareerSkill, CareerEnrichment, SkillAlias)
COPY_MODELS = (*CATALOG_MODELS, QuestionBank, InterestItem)


def require_isolation():
    name = str(connection.settings_dict['NAME'])
    memory = name == ':memory:' or (name.startswith('file:memorydb_') and 'mode=memory' in name)
    if not getattr(settings, 'CAREERCOACH_SIMULATION_ISOLATED', False) or connection.vendor != 'sqlite' or not memory:
        raise RuntimeError('Synthetic writes require the dedicated in-memory simulation settings')


def read_snapshot(source):
    """Single SQLite read transaction, mode=ro and query_only. No ORM aliases."""
    source = Path(source).resolve(strict=True)
    snapshot = {}
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro', uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        # Fixed model table/column names only; user input is never interpolated.
        for model in COPY_MODELS:
            table = model._meta.db_table
            columns = ','.join('"'+field.column+'"' for field in model._meta.fields)
            where = " WHERE status='active'" if model is QuestionBank else (
                " WHERE bank_id IN (SELECT id FROM assessment_questionbank WHERE status='active')" if model is InterestItem else '')
            records = [dict(row) for row in db.execute(f'SELECT {columns} FROM "{table}"{where} ORDER BY id')]
            snapshot[model._meta.label_lower] = records
    if len(snapshot[QuestionBank._meta.label_lower]) != 1:
        raise ValueError('Source must contain exactly one active assessment bank')
    if not snapshot[Career._meta.label_lower] or not snapshot[Skill._meta.label_lower]:
        raise ValueError('Source must contain real careers and canonical skills')
    return snapshot


def fingerprints(snapshot):
    return {'catalog': digest({m._meta.label_lower: snapshot[m._meta.label_lower] for m in CATALOG_MODELS}),
            'assessment_bank': digest({m._meta.label_lower: snapshot[m._meta.label_lower] for m in (QuestionBank, InterestItem)})}


def install_snapshot(snapshot):
    require_isolation()
    with transaction.atomic():
        # Fresh migrations publish a default bank. Replace it with the actual
        # source bank only inside the empty private worker database.
        InterestItem.objects.all().delete()
        QuestionBank.objects.all().delete()
        if any(m.objects.exists() for m in CATALOG_MODELS):
            raise RuntimeError('Simulation requires an empty catalog destination')
        for model in COPY_MODELS:
            records = []
            for raw in snapshot[model._meta.label_lower]:
                values = {}
                for field in model._meta.fields:
                    value = raw[field.column]
                    if field.get_internal_type() == 'JSONField' and isinstance(value, str):
                        value = json.loads(value)
                    else:
                        value = field.to_python(value)
                    values[field.attname] = value
                records.append(model(**values))
            model.objects.bulk_create(records, batch_size=300)
