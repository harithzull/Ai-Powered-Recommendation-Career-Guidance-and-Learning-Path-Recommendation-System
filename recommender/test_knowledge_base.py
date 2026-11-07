import csv
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase

from careercoach.test_utils import UserDataTestCase
from recommender.aliases import resolve_skill_name
from recommender.curation import seed_examples
from recommender.data_audit import audit_tables
from recommender.data_import import ImportRejected, import_tables
from recommender.datasets import FILES, Row, Table, read_tables
from recommender.models import Career, CareerEnrichment, CareerFamily, CareerSkill, CachedRecommendation, Skill, SkillAlias
from recommender.normalization import normalize_label
from roadmap.models import RoadmapProgress, SavedRoadmap


def small_tables():
    records = {
        "careers": [{"title": "Software developer", "industry": "Technology", "summary": "Build software",
                     "description": "Develop and maintain software applications using programming languages and tools.", "work_environment": "hybrid"}],
        "skills": [{"name": "JavaScript", "description": "A programming language used in web applications.", "category": "knowledge"}],
        "relationships": [{"career": "Software developer", "skill": "JavaScript", "skill_type": "knowledge",
                           "required_level": "intermediate", "importance": "5", "is_core": "True"}],
    }
    return {kind: Table(FILES[kind][0], "test-file-hash", list(rows[0]), [Row(row, i + 2) for i, row in enumerate(rows)])
            for kind, rows in records.items()}


def write_fixture(directory, tables):
    for table in tables.values():
        with (Path(directory) / table.filename).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=table.columns)
            writer.writeheader()
            writer.writerows(row.values for row in table.rows)


class DatasetAuditTests(TestCase):
    def test_clean_small_dataset_counts_and_unknown_source(self):
        report = audit_tables(small_tables())
        self.assertEqual(report["counts"], {"careers": 1, "skills": 1, "relationships": 1})
        self.assertEqual(report["finding_counts"]["error"], 0)
        self.assertIsNone(report["source_version"])
        self.assertTrue(any(f["code"] == "missing_source_identifier" for f in report["findings"]))

    def test_duplicate_and_case_whitespace_duplicate_detection(self):
        tables = small_tables()
        original = tables["careers"].rows[0].values
        tables["careers"].rows.extend([Row(dict(original), 3), Row({**original, "title": " SOFTWARE  developer "}, 4)])
        report = audit_tables(tables)
        codes = {f["code"] for f in report["findings"]}
        self.assertIn("duplicate_labels", codes)
        self.assertIn("normalized_duplicate_labels", codes)
        self.assertIn("inconsistent_whitespace", codes)

    def test_invalid_references_and_metadata_are_confirmed_errors(self):
        tables = small_tables()
        tables["relationships"].rows[0].values.update(career="Missing", skill="Missing", importance="many", required_level="expert")
        codes = {f["code"] for f in audit_tables(tables)["findings"]}
        self.assertTrue({"invalid_career_reference", "invalid_skill_reference", "invalid_relationship_values"} <= codes)

    def test_missing_description_and_optional_metadata_are_not_fabricated(self):
        tables = small_tables()
        tables["skills"].rows[0].values.update(description="", category="")
        tables["relationships"].rows[0].values.update(importance="", required_level="", skill_type="", is_core="")
        report = audit_tables(tables)
        self.assertEqual(report["finding_counts"]["error"], 0)
        self.assertTrue(any(f["code"] == "missing_description" and f["category"] == "review" for f in report["findings"]))
        self.assertTrue(any(f["code"] == "missing_relationship_metadata" and f["category"] == "unknown" for f in report["findings"]))

    def test_suspicious_classification_is_review_only(self):
        tables = small_tables()
        tables["careers"].rows[0].values.update(title="food analyst", industry="Finance")
        findings = audit_tables(tables)["findings"]
        classification = next(f for f in findings if f["code"] == "classification_review")
        self.assertEqual(classification["category"], "review")
        self.assertEqual(tables["careers"].rows[0].values["industry"], "Finance")

    def test_significant_programming_language_punctuation_is_preserved(self):
        tables = small_tables()
        for i, name in enumerate(["C++", "C#", "C"]):
            tables["skills"].rows.append(Row({"name": name, "description": "A distinct programming language.", "category": "knowledge"}, i + 3))
        self.assertFalse(any(f["code"] == "potential_skill_synonyms" for f in audit_tables(tables)["findings"]))

    def test_bad_csv_headers_and_row_width(self):
        with TemporaryDirectory() as directory:
            write_fixture(directory, small_tables())
            path = Path(directory) / FILES["skills"][0]
            path.write_text("name,wrong\nJavaScript,data\n", encoding="utf-8")
            self.assertTrue(read_tables(directory)["skills"].errors)
            path.write_text("name,description,category\nJavaScript,description\n", encoding="utf-8")
            self.assertTrue(read_tables(directory)["skills"].errors)

    def test_json_command_reports_errors_and_can_fail_ci(self):
        with TemporaryDirectory() as directory:
            tables = small_tables()
            tables["skills"].rows[0].values["category"] = "invalid"
            write_fixture(directory, tables)
            target = Path(directory) / "report.json"
            with self.assertRaises(CommandError):
                call_command("audit_career_data", data_dir=Path(directory), format="json", output=target, fail_on_errors=True)
            report = json.loads(target.read_text())
            self.assertGreater(report["finding_counts"]["error"], 0)
            self.assertEqual(Career.objects.count(), 0)


class ImportTests(UserDataTestCase):
    def test_idempotent_import_preserves_existing_id_and_legacy_scoring(self):
        tables = small_tables()
        tables["careers"].rows[0].values["industry"] = "Business"
        first = import_tables(tables)
        self.assertEqual(first["counts"]["careers"]["updated"], 1)
        self.career.refresh_from_db()
        self.assertEqual(self.career.industry, "Technology")
        self.assertEqual(Career.objects.get(source_title="Software developer").pk, self.career.pk)
        skill_pk = Skill.objects.get(name="JavaScript").pk
        relation_pk = CareerSkill.objects.get(career=self.career).pk
        second = import_tables(tables)
        self.assertEqual(second["counts"], {kind: {"inserted": 0, "updated": 0, "skipped": 1, "rejected": 0} for kind in tables})
        self.assertEqual(Skill.objects.get(name="JavaScript").pk, skill_pk)
        self.assertEqual(CareerSkill.objects.get(career=self.career).pk, relation_pk)

    def test_dry_run_rolls_back_every_write_and_cache_invalidation(self):
        CachedRecommendation.objects.create(user=self.user, results_json="[]")
        report = import_tables(small_tables(), dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertFalse(Skill.objects.exists())
        self.career.refresh_from_db()
        self.assertEqual(self.career.source_title, "")
        self.assertTrue(CachedRecommendation.objects.filter(user=self.user).exists())

    def test_preserves_enrichment_user_responses_roadmap_and_progress(self):
        family = CareerFamily.objects.create(slug="custom", name="Custom family")
        CareerEnrichment.objects.create(career=self.career, family=family, student_summary="Do not overwrite", localized_titles={"en-MY": ["Local title"]})
        SavedRoadmap.objects.create(user=self.user, career=self.career, title="My plan", steps_json="[]")
        RoadmapProgress.objects.create(user=self.user, career=self.career, step_index=0)
        response_pk = self.user.assessment_response.pk
        import_tables(small_tables())
        self.assertEqual(self.career.enrichment.student_summary, "Do not overwrite")
        self.assertEqual(CareerEnrichment.objects.get(career=self.career).localized_titles, {"en-MY": ["Local title"]})
        self.assertEqual(self.user.assessment_response.pk, response_pk)
        self.assertTrue(SavedRoadmap.objects.filter(user=self.user, title="My plan").exists())
        self.assertTrue(RoadmapProgress.objects.filter(user=self.user).exists())

    def test_missing_from_file_records_are_not_pruned(self):
        extra = Career.objects.create(title="Retain me")
        skill = Skill.objects.create(name="Retain this skill")
        link = CareerSkill.objects.create(career=extra, skill=skill)
        import_tables(small_tables())
        self.assertTrue(Career.objects.filter(pk=extra.pk).exists())
        self.assertTrue(CareerSkill.objects.filter(pk=link.pk).exists())

    def test_transaction_rolls_back_after_later_failure(self):
        with patch("recommender.data_import.Skill.save", side_effect=RuntimeError("simulated write failure")):
            with self.assertRaises(RuntimeError):
                import_tables(small_tables())
        self.career.refresh_from_db()
        self.assertEqual(self.career.source_taxonomy, "unknown")
        self.assertFalse(Skill.objects.exists())

    def test_invalid_references_reject_entire_bundle(self):
        tables = small_tables()
        tables["relationships"].rows[0].values["skill"] = "Does not exist"
        with self.assertRaises(ImportRejected):
            import_tables(tables)
        self.assertFalse(Skill.objects.exists())

    def test_duplicate_input_is_rejected_without_merging(self):
        tables = small_tables()
        tables["skills"].rows.append(Row({**tables["skills"].rows[0].values, "name": " javascript "}, 3))
        with self.assertRaises(ImportRejected):
            import_tables(tables)
        self.assertFalse(Skill.objects.exists())

    def test_ambiguous_database_names_require_manual_review(self):
        Career.objects.create(title=" SOFTWARE developer ")
        with self.assertRaises(ImportRejected):
            import_tables(small_tables())
        self.assertEqual(Career.objects.count(), 2)

    def test_uri_matching_keeps_id_when_source_label_changes(self):
        uri = "http://data.europa.eu/esco/occupation/00000000-0000-0000-0000-000000000001"  # Synthetic test URI only.
        self.career.esco_uri = uri
        self.career.source_taxonomy = "esco"
        self.career.save()
        tables = small_tables()
        tables["careers"].rows[0].values.update(title="Renamed source concept", esco_uri=uri)
        tables["relationships"].rows[0].values["career"] = "Renamed source concept"
        import_tables(tables)
        self.career.refresh_from_db()
        self.assertEqual(self.career.source_title, "Renamed source concept")
        self.assertEqual(self.career.title, "Software developer")
        self.assertEqual(Career.objects.count(), 1)

    def test_uri_conflict_is_not_silently_reassigned(self):
        self.career.esco_uri = "http://data.europa.eu/esco/occupation/00000000-0000-0000-0000-000000000001"
        self.career.save()
        tables = small_tables()
        tables["careers"].rows[0].values["esco_uri"] = "http://data.europa.eu/esco/occupation/00000000-0000-0000-0000-000000000002"
        with self.assertRaises(ImportRejected):
            import_tables(tables)

    def test_curated_concept_is_not_claimed_as_esco(self):
        self.career.source_taxonomy = "careercoach"
        self.career.save()
        with self.assertRaises(ImportRejected):
            import_tables(small_tables())

    def test_source_snapshot_is_distinct_and_unknowns_stay_unknown(self):
        import_tables(small_tables())
        self.career.refresh_from_db()
        skill, relation = Skill.objects.get(), CareerSkill.objects.get()
        self.assertEqual(skill.category, "knowledge")
        self.assertEqual(skill.source_name, "JavaScript")
        self.assertIsNone(skill.esco_uri)
        self.assertIsNone(self.career.source_metadata["source_version"])
        self.assertIsNone(relation.source_importance)
        self.assertEqual(relation.source_proficiency, "")
        self.assertEqual(relation.source_relation_type, "")
        self.assertEqual(relation.importance, 5)

    def test_existing_relationship_estimates_are_never_replaced(self):
        import_tables(small_tables())
        tables = small_tables()
        tables["relationships"].rows[0].values.update(importance="2", is_core="False", required_level="basic")
        import_tables(tables)
        relation = CareerSkill.objects.get()
        self.assertEqual(relation.importance, 5)
        self.assertTrue(relation.is_core)
        self.assertEqual(relation.required_level, "intermediate")
        self.assertEqual(relation.source_metadata["exported_record"]["importance"], "2")

    def test_recommendation_results_unchanged_by_source_refresh(self):
        from recommender.recommendations import get_recommendations
        with patch("recommender.recommendations.encode_user_skills", return_value=[[1, 0]]), patch(
            "recommender.recommendations.semantic_skill_match_from_vectors", return_value=(0.5, ["SQL"]),
        ):
            before = get_recommendations(self.user)
            tables = small_tables()
            tables["careers"].rows[0].values["industry"] = "Business"
            import_tables(tables)
            after = get_recommendations(self.user)
        for key in ["final_score", "interest_pct", "skill_pct", "background_pct", "missing_skills"]:
            self.assertEqual(before[0][key], after[0][key])

    def test_new_unknown_relationship_values_are_explicitly_unknown(self):
        tables = small_tables()
        tables["relationships"].rows[0].values.update(importance="", required_level="", is_core="")
        import_tables(tables)
        relationship = CareerSkill.objects.get()
        self.assertIsNone(relationship.source_importance)
        self.assertEqual(relationship.source_proficiency, "")
        self.assertEqual(relationship.importance, 0)  # Existing engine's documented compatibility sentinel, not an ESCO estimate.

    def test_source_uri_is_validated_not_generated(self):
        tables = small_tables()
        tables["careers"].rows[0].values["esco_uri"] = "http://example.com/invented/software-developer"
        with self.assertRaises(ImportRejected):
            import_tables(tables)

    def test_invalid_existing_metadata_is_rejected_without_overwrite(self):
        Career.objects.filter(pk=self.career.pk).update(source_metadata=[])
        with self.assertRaises(ImportRejected):
            import_tables(small_tables())
        self.assertEqual(Career.objects.get(pk=self.career.pk).source_metadata, [])
        self.assertFalse(Skill.objects.exists())

    def test_invalid_relationship_metadata_rolls_back_earlier_source_updates(self):
        import_tables(small_tables())
        CareerSkill.objects.update(source_metadata=[])
        tables = small_tables()
        tables["careers"].rows[0].values["description"] = "A changed description"
        with self.assertRaises(ImportRejected):
            import_tables(tables)
        self.career.refresh_from_db()
        self.assertNotEqual(self.career.source_description, "A changed description")

    def test_relationship_foreign_keys_are_validated(self):
        skill = Skill.objects.create(name="Example")
        relationship = CareerSkill(career_id=999999, skill=skill)
        with self.assertRaises(ValidationError):
            relationship.full_clean()

    def test_command_repeat_and_dry_run_use_small_csvs(self):
        with TemporaryDirectory() as directory:
            write_fixture(directory, small_tables())
            for dry_run in [True, False, False]:
                output = StringIO()
                call_command("import_data", data_dir=Path(directory), dry_run=dry_run, format="json", stdout=output)
                report = json.loads(output.getvalue())
            self.assertEqual(report["counts"]["relationships"]["skipped"], 1)
        self.assertEqual(Career.objects.count(), 1)
        self.assertEqual(Skill.objects.count(), 1)
        self.assertEqual(CareerSkill.objects.count(), 1)


class AliasAndEnrichmentTests(UserDataTestCase):
    def setUp(self):
        super().setUp()
        self.skill = Skill.objects.create(name="JavaScript", category="knowledge")

    def alias(self, **overrides):
        values = {"skill": self.skill, "name": "JS", "review_status": "reviewed", "review_metadata": {"evidence": ["test evidence"]}}
        values.update(overrides)
        return SkillAlias.objects.create(**values)

    def test_unicode_case_whitespace_equality(self):
        self.assertEqual(normalize_label("  ＪＳ\t"), "js")
        self.assertEqual(resolve_skill_name(" javascript ")["skill"], self.skill)

    def test_exact_reviewed_alias_resolves_and_search_returns_canonical(self):
        self.alias()
        self.assertEqual(resolve_skill_name(" JS ")["skill"], self.skill)
        self.assertEqual(self.client.get("/assessment/skill-search/", {"q": "JS"}).json()["results"], ["JavaScript"])
        self.assertEqual(Skill.objects.get(pk=self.skill.pk).category, "knowledge")

    def test_related_and_unreviewed_aliases_never_resolve_as_exact(self):
        self.alias(name="Web scripting", kind="related")
        self.alias(name="JS", review_status="needs_review")
        self.assertIsNone(resolve_skill_name("Web scripting"))
        self.assertIsNone(resolve_skill_name("JS"))

    def test_exact_alias_is_not_hidden_by_many_substring_results(self):
        self.alias()
        Skill.objects.bulk_create([Skill(name=f"JS toolkit {i}") for i in range(12)])
        results = self.client.get("/assessment/skill-search/", {"q": "JS"}).json()["results"]
        self.assertEqual(results[0], "JavaScript")
        self.assertEqual(len(results), 10)

    def test_import_cannot_create_a_canonical_name_that_shadows_an_alias(self):
        self.alias()
        tables = small_tables()
        tables["skills"].rows[0].values["name"] = "JS"
        tables["relationships"].rows[0].values["skill"] = "JS"
        with self.assertRaises(ImportRejected):
            import_tables(tables)
        self.assertFalse(Skill.objects.filter(name="JS").exists())

    def test_duplicate_alias_case_and_spacing_rejected(self):
        self.alias()
        with self.assertRaises(ValidationError):
            self.alias(name=" js ")

    def test_alias_cannot_shadow_another_canonical_concept(self):
        Skill.objects.create(name="JS")
        with self.assertRaises(ValidationError):
            self.alias()

    def test_reviewed_alias_requires_evidence(self):
        with self.assertRaises(ValidationError):
            self.alias(review_metadata={})

    def test_enrichment_fields_validate_and_family_is_independent_of_industry(self):
        family = CareerFamily.objects.create(slug="software", name="Software & IT")
        enrichment = CareerEnrichment(career=self.career, family=family, localized_titles={"en-MY": ["Application Developer"]})
        enrichment.full_clean()
        enrichment.save()
        self.assertEqual(Career.objects.get(pk=self.career.pk).industry, "Technology")
        self.assertIsNone(enrichment.entry_level_suitable)
        self.assertIsNone(enrichment.riasec_profile)
        enrichment.localized_titles = {"en-MY": ["Developer", " developer "]}
        with self.assertRaises(ValidationError):
            enrichment.full_clean()

    def test_families_can_be_removed_without_deleting_careers(self):
        family = CareerFamily.objects.create(slug="software", name="Software & IT")
        enrichment = CareerEnrichment.objects.create(career=self.career, family=family)
        family.delete()
        enrichment.refresh_from_db()
        self.assertIsNone(enrichment.family_id)
        self.assertTrue(Career.objects.filter(pk=self.career.pk).exists())

    def test_example_seed_is_idempotent_and_preserves_manual_curation(self):
        family = CareerFamily.objects.create(slug="manual", name="Manual family")
        CareerEnrichment.objects.create(career=self.career, family=family, student_summary="Preserve me")
        Skill.objects.create(name="PostgreSQL", category="knowledge")
        seed_examples()
        counts = (CareerFamily.objects.count(), CareerEnrichment.objects.count(), SkillAlias.objects.count())
        seed_examples()
        self.assertEqual(counts, (CareerFamily.objects.count(), CareerEnrichment.objects.count(), SkillAlias.objects.count()))
        self.assertEqual(CareerEnrichment.objects.get(career=self.career).family, family)
        self.assertEqual(SkillAlias.objects.count(), 2)

    def test_dry_run_examples_leave_no_changes(self):
        seed_examples(dry_run=True)
        self.assertFalse(CareerFamily.objects.exists())
        self.assertFalse(SkillAlias.objects.exists())

    def test_database_audit_reports_unclassified_and_does_not_mutate(self):
        from recommender.knowledge_audit import audit_database
        report = audit_database()
        self.assertEqual(report["finding_counts"]["error"], 0)
        self.assertTrue(any(f["code"] == "unclassified_careers" for f in report["findings"]))
        self.assertFalse(CareerEnrichment.objects.exists())

    def test_source_metadata_must_be_an_object(self):
        for invalid in [[], "text", 3]:
            self.skill.source_metadata = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.skill.full_clean()
