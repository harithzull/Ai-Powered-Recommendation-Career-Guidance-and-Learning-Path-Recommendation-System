"""Atomic, non-destructive source upserts for the existing CSV interchange format."""
from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction

from .data_audit import audit_tables
from .knowledge_validation import validate_occupation_uri, validate_skill_uri
from .models import CachedRecommendation, Career, CareerSkill, Skill, SkillAlias, SourceTaxonomy
from .normalization import normalize_label


class ImportRejected(ValueError):
    def __init__(self, report):
        report["rolled_back"] = True
        self.report = report
        super().__init__("Import rejected; no database changes were made.")


def _source_metadata(table, row, version):
    return {
        "dataset": "careercoach-legacy-esco-derived-export", "source_version": version,
        "file": table.filename, "file_sha256": table.sha256, "line": row.line,
        "exported_record": row.values,
        "verification": "ESCO derivation confirmed by project owner; original record fidelity unverified",
    }


def _label_index(objects, display_field, source_field):
    index = defaultdict(set)
    for obj in objects:
        for value in [getattr(obj, display_field), getattr(obj, source_field)]:
            if value:
                index[normalize_label(value)].add(obj.pk)
    return index


def import_tables(tables, *, dry_run=False, source_version=None):
    """No fuzzy matches, pruning, canonical renames, or scoring-field overwrites.

    On existing rows only provenance/source snapshots change. On new rows the
    provided legacy export fields initialize compatibility fields. Authoritative
    relationship metadata is never inferred from numeric legacy estimates.
    """
    report = {
        "dry_run": dry_run, "source_version": source_version,
        "counts": {kind: dict.fromkeys(["inserted", "updated", "skipped", "rejected"], 0) for kind in tables},
        "errors": [], "warnings": [], "embedding_rebuild_required": False,
    }
    audit = audit_tables(tables)
    for issue in audit["findings"]:
        if issue["category"] == "error":
            report["errors"].append(issue)
            report["counts"][issue["table"]]["rejected"] += issue["count"]
    # Validate complete incoming records before any database operation.
    for kind in ["careers", "skills"]:
        for row in tables[kind].rows:
            r = row.values
            label = "title" if kind == "careers" else "name"
            try:
                if len(r[label].strip()) > 255:
                    raise ValidationError("Label exceeds 255 characters.")
                if kind == "careers" and (len(r["industry"]) > 255 or len(r["work_environment"]) > 100):
                    raise ValidationError("Career metadata exceeds field length.")
                (validate_occupation_uri if kind == "careers" else validate_skill_uri)(r.get("esco_uri", ""))
            except ValidationError as exc:
                report["errors"].append({"table": kind, "line": row.line, "message": "; ".join(exc.messages)})
                report["counts"][kind]["rejected"] += 1
    for row in tables["relationships"].rows:
        r = row.values
        try:
            if len(r.get("source_relation_type", "")) > 50 or len(r.get("source_proficiency", "")) > 100:
                raise ValueError
            if r.get("source_importance") and not 0 <= int(r["source_importance"]) <= 32767:
                raise ValueError
        except ValueError:
            report["errors"].append({"table": "relationships", "line": row.line, "message": "Invalid explicit source relationship metadata."})
            report["counts"]["relationships"]["rejected"] += 1
    if report["errors"]:
        raise ImportRejected(report)

    with transaction.atomic():
        # Lock existing records while matching. Operations should run with one
        # catalog writer; DB uniqueness/atomic rollback handles conflicting inserts.
        plans, entity_maps = {}, {}
        alias_targets = dict(SkillAlias.objects.values_list("normalized_name", "skill_id"))
        for kind, model, display, source in [("careers", Career, "title", "source_title"),
                                             ("skills", Skill, "name", "source_name")]:
            objects = list(model.objects.select_for_update().all())
            by_pk = {obj.pk: obj for obj in objects}
            by_uri = {obj.esco_uri: obj for obj in objects if obj.esco_uri}
            by_label = _label_index(objects, display, source)
            seen_uris, target_ids = set(), set()
            plan, entity_map = [], {}
            for row in tables[kind].rows:
                r = row.values
                uri = r.get("esco_uri", "").strip() or None
                key = normalize_label(r[display])
                candidates = by_label.get(key, set())
                obj = by_uri.get(uri) if uri else None
                reason = None
                if uri and uri in seen_uris:
                    reason = "Duplicate incoming URI."
                elif obj is None and len(candidates) > 1:
                    reason = "Ambiguous normalized label matches multiple existing records."
                elif obj is None and candidates:
                    obj = by_pk[next(iter(candidates))]
                if obj is not None:
                    if not isinstance(obj.source_metadata, dict):
                        reason = "Existing source metadata is invalid; review it before importing."
                    elif candidates and candidates != {obj.pk}:
                        reason = "URI and normalized label point to different existing records."
                    elif obj.pk in target_ids:
                        reason = "More than one input row targets the same existing record."
                    elif obj.source_taxonomy == SourceTaxonomy.CAREERCOACH:
                        reason = "A curated CareerCoach concept cannot be silently claimed as ESCO."
                    elif uri and obj.esco_uri and obj.esco_uri != uri:
                        reason = "Source URI conflicts with the existing record."
                    target_ids.add(obj.pk)
                if uri:
                    seen_uris.add(uri)
                if kind == "skills" and key in alias_targets and (obj is None or obj.pk != alias_targets[key]):
                    reason = "Incoming canonical label conflicts with an existing alias; manual review is required."
                if reason:
                    report["errors"].append({"table": kind, "line": row.line, display: r[display], "message": reason})
                    report["counts"][kind]["rejected"] += 1
                    continue
                source_values = {
                    "source_taxonomy": SourceTaxonomy.ESCO,
                    source: r[display], "source_description": r["description"],
                    "source_metadata": _source_metadata(tables[kind], row, source_version),
                }
                # Missing identifiers in a later file never erase known identifiers.
                if uri:
                    source_values["esco_uri"] = uri
                if obj is None:
                    legacy_fields = (["title", "industry", "summary", "description", "work_environment"] if kind == "careers"
                                     else ["name", "description", "category"])
                    obj = model(**{field: r[field].strip() for field in legacy_fields})
                    status = "inserted"
                else:
                    source_values["source_metadata"] = {**obj.source_metadata, **source_values["source_metadata"]}
                    status = "updated" if any(getattr(obj, field) != value for field, value in source_values.items()) else "skipped"
                for field, value in source_values.items():
                    setattr(obj, field, value)
                plan.append((obj, status))
                entity_map[key] = obj
            plans[kind], entity_maps[kind] = plan, entity_map
        if report["errors"]:
            raise ImportRejected(report)

        for kind in ["careers", "skills"]:
            for obj, status in plans[kind]:
                report["counts"][kind][status] += 1
                if status != "skipped":
                    obj.full_clean()
                    obj.save()
                if kind == "skills" and status == "inserted":
                    report["embedding_rebuild_required"] = True

        existing = {(r.career_id, r.skill_id): r for r in CareerSkill.objects.select_for_update().all()}
        for row in tables["relationships"].rows:
            r = row.values
            career = entity_maps["careers"][normalize_label(r["career"])]
            skill = entity_maps["skills"][normalize_label(r["skill"])]
            obj = existing.get((career.pk, skill.pk))
            values = {
                "source_taxonomy": SourceTaxonomy.ESCO,
                "source_metadata": _source_metadata(tables["relationships"], row, source_version),
            }
            # These fields can be supplied only as explicit source metadata; none
            # are copied from legacy is_core/importance/required_level.
            for input_name, model_name in [("source_relation_type", "source_relation_type"),
                                           ("source_proficiency", "source_proficiency")]:
                if r.get(input_name):
                    values[model_name] = r[input_name].strip()
            if r.get("source_importance"):
                try:
                    values["source_importance"] = int(r["source_importance"])
                except ValueError as exc:
                    report["errors"].append({"table": "relationships", "line": row.line, "message": "Invalid source_importance"})
                    raise ImportRejected(report) from exc
            if obj is None:
                obj = CareerSkill(career=career, skill=skill, skill_type=r["skill_type"].strip(),
                                  required_level=r["required_level"].strip(),
                                  importance=int(r["importance"]) if r["importance"] else 0,
                                  is_core=r["is_core"].casefold() == "true")
                status = "inserted"
            else:
                if not isinstance(obj.source_metadata, dict):
                    report["errors"].append({"table": "relationships", "line": row.line,
                                             "message": "Existing source metadata must be an object."})
                    report["counts"]["relationships"]["rejected"] += 1
                    raise ImportRejected(report)
                values["source_metadata"] = {**obj.source_metadata, **values["source_metadata"]}
                status = "updated" if any(getattr(obj, field) != value for field, value in values.items()) else "skipped"
            for field, value in values.items():
                setattr(obj, field, value)
            report["counts"]["relationships"][status] += 1
            if status != "skipped":
                obj.full_clean()
                obj.save()
        if any(counts["inserted"] or counts["updated"] for counts in report["counts"].values()):
            CachedRecommendation.objects.all().delete()
        if dry_run:
            transaction.set_rollback(True)
        report["warnings"] = ["Existing canonical/display/scoring fields and enrichment are preserved.",
                              "No missing-from-file records, user assessments, roadmaps, or progress are deleted.",
                              "Legacy source version and identifiers remain unknown unless explicitly supplied."]
    return report
