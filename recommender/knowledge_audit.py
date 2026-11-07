"""Database-side coverage and integrity checks beyond the source CSV audit."""
from collections import Counter, defaultdict

from django.core.exceptions import ValidationError

from .models import Career, CareerEnrichment, CareerSkill, Skill, SkillAlias
from .normalization import normalize_label


def audit_database(max_examples=20):
    findings = []

    def add(code, category, table, records, action):
        if records:
            examples = records if max_examples == 0 else records[:max_examples]
            findings.append({"code": code, "category": category, "table": table, "count": len(records),
                             "records": examples, "examples_truncated": len(examples) < len(records),
                             "suggested_action": action})

    careers, skills, relationships = list(Career.objects.all()), list(Skill.objects.all()), list(CareerSkill.objects.all())
    for kind, objects, label in [("careers", careers, "title"), ("skills", skills, "name")]:
        keys = defaultdict(list)
        for obj in objects:
            keys[normalize_label(getattr(obj, label))].append(obj.pk)
        add("ambiguous_canonical_labels", "error", kind, [{"key": key, "ids": ids} for key, ids in keys.items() if len(ids) > 1], "Review duplicates; never merge automatically.")
        add("missing_source_identifier", "unknown", kind, [{"id": obj.pk, label: getattr(obj, label)} for obj in objects if not obj.esco_uri], "Recover only with authoritative evidence; leave unknown meanwhile.")
        add("unknown_source_version", "unknown", kind, [{"id": obj.pk} for obj in objects if not isinstance(obj.source_metadata, dict) or not obj.source_metadata.get("source_version")], "Record verified original extraction version if recovered.")
    career_ids, skill_ids = {obj.pk for obj in careers}, {obj.pk for obj in skills}
    add("orphan_relationships", "error", "relationships", [{"id": obj.pk} for obj in relationships if obj.career_id not in career_ids or obj.skill_id not in skill_ids], "Repair references after backup and manual review.")
    pairs = Counter((obj.career_id, obj.skill_id) for obj in relationships)
    add("duplicate_relationships", "error", "relationships", [{"career_id": pair[0], "skill_id": pair[1], "count": n} for pair, n in pairs.items() if n > 1], "Review duplicates before applying a uniqueness constraint.")
    enrichments = {obj.career_id: obj for obj in CareerEnrichment.objects.all()}
    add("unclassified_careers", "optional", "careers", [{"id": obj.pk, "title": obj.title} for obj in careers if obj.pk not in enrichments or not enrichments[obj.pk].family_id], "Review and curate a CareerCoach family; retain an explicit unclassified state.")
    add("enrichment_needs_review", "review", "careers", [{"id": obj.career_id} for obj in enrichments.values() if obj.review_status != "reviewed"], "Review source descriptions and curation rationale.")
    canonical = {normalize_label(obj.name): obj.pk for obj in skills}
    invalid_aliases = []
    for obj in SkillAlias.objects.all():
        if obj.normalized_name != normalize_label(obj.name) or obj.normalized_name in canonical:
            invalid_aliases.append({"id": obj.pk, "name": obj.name})
    add("invalid_alias_keys", "error", "aliases", invalid_aliases, "Resolve canonical/alias conflicts; do not override canonical concepts.")
    invalid = []
    for obj in [*careers, *skills, *relationships, *enrichments.values(), *SkillAlias.objects.all()]:
        try:
            obj.full_clean(validate_unique=False, validate_constraints=False)
        except ValidationError as exc:
            invalid.append({"model": obj._meta.model_name, "id": obj.pk, "messages": exc.messages})
    add("model_validation", "error", "database", invalid, "Review invalid source/enrichment metadata before editing.")
    return {"schema_version": 1, "input_kind": "database", "counts": {"careers": len(careers), "skills": len(skills), "relationships": len(relationships), "enrichments": len(enrichments), "aliases": SkillAlias.objects.count()},
            "statistics": {"career_source_taxonomies": dict(Counter(obj.source_taxonomy for obj in careers)),
                           "skill_source_taxonomies": dict(Counter(obj.source_taxonomy for obj in skills)),
                           "unknown_source_relationship_types": sum(not obj.source_relation_type for obj in relationships),
                           "unknown_source_importance": sum(obj.source_importance is None for obj in relationships),
                           "unknown_source_proficiency": sum(not obj.source_proficiency for obj in relationships)},
            "finding_counts": {kind: sum(f["count"] for f in findings if f["category"] == kind) for kind in ["error", "review", "optional", "unknown"]},
            "findings": findings}
