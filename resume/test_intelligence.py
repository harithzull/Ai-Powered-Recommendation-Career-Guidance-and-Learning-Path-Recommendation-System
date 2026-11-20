"""Synthetic extraction and private Django review workflow tests."""
from dataclasses import asdict
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.models import UserProfile
from assessment.models import SkillRating, UserResponse
from careercoach.security import user_work_lock
from recommender.models import CachedRecommendation, RecommendationRun, ReviewStatus, Skill, SkillAlias

from .constants import MAX_TEXT_CHARS
from .intelligence import schema
from .intelligence.pipeline import AnalysisUnavailable, DeterministicExtractor, UnsupportedText
from .intelligence.sections import split_sections
from .models import ResumeAnalysis, ResumeDocument, ResumeSuggestion

ESCO_TEST_URI = 'http://data.europa.eu/esco/skill/00000000-0000-0000-0000-000000000001'


class CatalogTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.python = Skill.objects.create(name='Python', esco_uri=ESCO_TEST_URI, source_taxonomy='esco',
                                          source_metadata={'source_version': 'test-catalog', 'line': 1})
        cls.postgres = Skill.objects.create(name='PostgreSQL')
        for name in ('Git', 'Django', 'SQL', 'C++', 'C#', 'Node.js', 'data analysis', 'customer service',
                     'Java (computer programming)', 'PCB Testing', 'pcb testing', 'CAD software'):
            Skill.objects.create(name=name)
        Skill.objects.create(name='project management', quality_status=ReviewStatus.REVIEWED,
                             source_metadata={'resume_variations': [
                                 {'label': 'project–management', 'evidence': 'Fixture reviewed spelling'}]})
        Skill.objects.create(name='Quality Control', quality_status=ReviewStatus.REVIEWED)
        SkillAlias.objects.create(name='Postgres', skill=cls.postgres, review_status=ReviewStatus.REVIEWED,
                                   review_metadata={'evidence': 'Fixture alias reviewed against the test catalog'})
        SkillAlias.objects.create(name='PyLang', skill=cls.python)
        SkillAlias.objects.create(name='Computer Design', skill=Skill.objects.get(name='CAD software'),
                                  kind=SkillAlias.Kind.RELATED, review_status=ReviewStatus.REVIEWED,
                                  review_metadata={'evidence': 'Fixture related term'})

    def result(self, text):
        result = DeterministicExtractor().extract(text)
        for row in result.suggestions:
            for span in row.evidence:
                self.assertLess(span.start, span.end)
                self.assertEqual(text[span.start:span.end], span.excerpt)
        return result

    def skills(self, text):
        return {(row.normalized, row.support): row for row in self.result(text).suggestions if row.category == 'skill'}

    def test_explicit_technologies_in_running_text(self):
        rows = self.skills('Developed a web application using Python, Django, PostgreSQL and Git.')
        self.assertEqual(set(rows), {(skill, 'explicit') for skill in ('python', 'django', 'postgresql', 'git')})
        self.assertEqual(rows['python', 'explicit'].canonical['source']['line'], 1)
        self.assertEqual(rows['python', 'explicit'].canonical['source']['source_version'], 'test-catalog')
        self.assertNotIn('proficiency', asdict(rows['python', 'explicit']))
        self.assertNotIn('years', asdict(rows['python', 'explicit']))

    def test_punctuation_case_whole_words_and_multiword(self):
        rows = self.skills('## Technical Skills: python / Git; C++, c# | Node.js, data   analysis\n'
                           'Java (computer programming)\nUsed digit, PostgreSQLish and github.')
        canonical = {row.canonical['name'] for row in rows.values() if row.canonical}
        self.assertEqual(canonical, {'Python', 'Git', 'C++', 'C#', 'Node.js', 'data analysis', 'Java (computer programming)'})

    def test_uri_and_bare_esco_identifier_are_evidence(self):
        rows = self.skills(f'Skills: {ESCO_TEST_URI}, {ESCO_TEST_URI.split("/")[-1]}')
        row, = rows.values()
        self.assertEqual(row.canonical['esco_uri'], ESCO_TEST_URI)
        self.assertEqual(row.method, 'exact_match')
        self.assertEqual(len(row.evidence), 2)

    def test_verified_alias_precedence_and_deduplication(self):
        row, = self.skills('Skills: Postgres, PostgreSQL, Postgres').values()
        self.assertEqual(row.canonical['id'], self.postgres.pk)
        self.assertEqual(row.method, 'exact_match')
        self.assertEqual([span.excerpt for span in row.evidence], ['Postgres', 'PostgreSQL', 'Postgres'])
        row, = self.skills('Skills: Postgres').values()
        self.assertEqual(row.method, 'verified_alias')
        self.assertEqual(row.canonical['alias'], 'Postgres')

    def test_unverified_and_related_aliases_are_review_only(self):
        rows = self.skills('Skills: PyLang, Computer Design')
        for row in rows.values():
            self.assertEqual(row.support, 'ambiguous')
            self.assertEqual(row.method, 'unverified_alias')
            self.assertTrue(row.alternatives)
            self.assertFalse(row.canonical)

    def test_canonical_label_collisions_are_ambiguous(self):
        row, = self.skills('Skills: PCB Testing').values()
        self.assertEqual(row.method, 'ambiguous')
        self.assertEqual({skill['name'] for skill in row.alternatives}, {'PCB Testing', 'pcb testing'})
        self.assertFalse(row.canonical)

    def test_colliding_reviewed_alias_is_not_created_by_catalog(self):
        with self.assertRaises(ValidationError):
            SkillAlias.objects.create(name='PYTHON', skill=self.postgres,
                                      review_status=ReviewStatus.REVIEWED, review_metadata={'evidence': 'Fixture'})

    def test_only_reviewed_punctuation_variation_can_map(self):
        rows = self.skills('Skills: project–management, quality-control')
        self.assertEqual(rows['project–management', 'explicit'].method, 'reviewed_variation')
        self.assertEqual(rows['quality-control', 'explicit'].method, 'unmatched')
        self.assertFalse(rows['quality-control', 'explicit'].canonical)

    def test_unknowns_and_no_implicit_technologies(self):
        rows = self.skills('Skills: Python, WidgetLang\nPersonal projects: Library Tool\nBuilt it using Django.')
        self.assertEqual(rows['widgetlang', 'explicit'].method, 'unmatched')
        self.assertEqual(set(key[0] for key in rows), {'python', 'widgetlang', 'django'})

    def test_negation_uncertainty_and_desired_roles_preserve_context(self):
        rows = self.skills('Summary: No experience with Python, but used Git.\nCurrently learning SQL.\n'
                           'Job Description: Django and PostgreSQL\nObjective: Seeking a Python role.')
        self.assertEqual({key for key in rows if key[1] == 'explicit'}, {('git', 'explicit')})
        self.assertIn(('sql', 'ambiguous'), rows)
        self.assertEqual(len(rows['python', 'unsupported'].evidence), 2)
        self.assertIn('No experience', rows['python', 'unsupported'].evidence[0].context)
        self.assertFalse(rows['django', 'unsupported'].canonical)

    def test_email_and_url_do_not_claim_skills(self):
        rows = self.skills('Skills: python@example.test, https://example.test/python/sql, Git')
        self.assertEqual(set(rows), {('git', 'explicit')})

    def test_unknown_tool_claims_are_not_arbitrary_narrative(self):
        rows = self.skills('Skills: Used digit counters and a postgresqlish parser.\n'
                           'Summary: Used LTspice.\nExperience with instrument handling.')
        self.assertEqual(set(rows), {('ltspice', 'explicit'), ('instrument handling', 'explicit')})

    def test_technical_token_boundaries_and_full_width_heading(self):
        rows = self.skills('• Technical Skills： c#; C++grade; PostgreSQLish')
        self.assertTrue(rows['c#', 'explicit'].canonical)
        self.assertFalse(rows['c++grade', 'explicit'].canonical)
        self.assertFalse(rows['postgresqlish', 'explicit'].canonical)

    def test_missing_headings_preserve_offsets_and_surface_uncertainty(self):
        text = '  Diploma in Information Technology, 2023\r\nExperience helps me learn.\r\n'
        result = self.result(text)
        self.assertEqual([section.kind for section in result.sections], ['unclassified'])
        self.assertIn('No reliable', result.notices[0])
        row, = [row for row in result.suggestions if row.category == 'education']
        self.assertEqual(row.support, 'inferred')
        self.assertEqual(row.fields['stated_date'], '2023')
        self.assertNotIn('graduation_date', row.fields)

    def test_local_and_inline_headings_and_offsets(self):
        text = '\n  # Kemahiran Teknikal: Python\r\n__Pendidikan__\r\nDiploma in IT\r\n' \
               'LATIHAN INDUSTRI:\r\nSoftware Intern at Atlas Sdn. Bhd. | Jun 2024 - Ogos 2024\r\n' \
               'Projek Tahun Akhir: Campus Map\r\nBuilt a map using Django.'
        result = self.result(text)
        self.assertEqual([section.kind for section in result.sections], ['skills', 'education', 'experience', 'projects'])
        self.assertEqual(split_sections(text)[0][1][0].text, 'Python')
        self.assertIn('academic', [row.fields.get('project_type') for row in result.suggestions])

    def test_education_dates_only_imply_completion_when_stated(self):
        result = self.result('Education\nBachelor of Computer Science, Universiti Reka, 2025\n'
                             'Diploma in Information Technology, Politeknik Murni\nCompleted 2022\n'
                             'Master of Data Science, University Example, expected May 2027')
        bachelor, diploma, master = [row for row in result.suggestions if row.category == 'education']
        self.assertEqual(bachelor.fields, {'qualification': 'Bachelor of Computer Science',
                                          'field_of_study': 'Computer Science', 'institution': 'Universiti Reka',
                                          'stated_date': '2025'})
        self.assertEqual(diploma.fields['graduation_date'], '2022')
        self.assertEqual(master.fields['expected_graduation_date'], 'May 2027')
        self.assertNotIn('graduation_date', master.fields)

    def test_uncertain_qualification_dates_and_misplaced_qualification(self):
        result = self.result('Education: Diploma in IT, 2024–2025 (expected 2026)\n'
                             'Bachelor of IT, 2025, not completed\n'
                             'Projects: Campus Tool\nDiploma in Business')
        diploma, bachelor, project = result.suggestions
        self.assertEqual(diploma.fields['study_status'], 'Expected graduation')
        self.assertNotIn('expected_graduation_date', diploma.fields)
        self.assertNotIn('graduation_date', bachelor.fields)
        self.assertEqual(project.fields['project_name'], 'Campus Tool')

    def test_experience_organization_dates_and_employment_type(self):
        result = self.result('Internship Experience\nSoftware Intern at Reka Sdn. Bhd. | Jun 2024 – Aug 2024\n'
                             '- Developed an inventory tool using Python and Git.\n'
                             'Part-time Assistant | Atlas Books | September 2025 to Present\n'
                             'Contract Analyst\nEmployer: Murni Labs\n2023')
        intern, part_time, contract = [row for row in result.suggestions if row.category == 'experience']
        self.assertEqual(intern.fields['organization'], 'Reka Sdn. Bhd.')
        self.assertEqual((intern.fields['start_date'], intern.fields['end_date']), ('Jun 2024', 'Aug 2024'))
        self.assertIn('Git', intern.fields['technologies_or_skills'])
        self.assertEqual(part_time.fields['current_employment'], 'Explicitly current')
        self.assertEqual(part_time.fields['employment_type'], 'Part-time')
        self.assertEqual(contract.fields['organization'], 'Murni Labs')
        self.assertNotIn('end_date', contract.fields)
        self.assertNotIn('duration', contract.fields)

    def test_project_separate_from_employment_and_no_fabricated_outcomes(self):
        result = self.result('Academic Projects\nLibrary Tool: search for loan records\n'
                             'Technologies: Python, SQL\nRole: Backend contributor\nhttps://example.test/repo\n'
                             'Work Experience\nLibrary Assistant at Atlas Books')
        project, = [row for row in result.suggestions if row.category == 'project']
        self.assertEqual(project.fields['project_name'], 'Library Tool')
        self.assertEqual(project.fields['project_url'], 'https://example.test/repo')
        self.assertEqual(project.fields['project_type'], 'academic')
        self.assertEqual(project.fields['role_or_contributions'], 'Backend contributor')
        self.assertEqual(project.fields['technologies'], 'Python, SQL')
        self.assertNotIn('impact', project.fields)
        self.assertEqual(len([row for row in result.suggestions if row.category == 'experience']), 1)

    def test_input_and_output_budgets(self):
        with self.assertRaises(UnsupportedText):
            self.result('x' * (MAX_TEXT_CHARS + 1))
        with self.assertRaises(UnsupportedText):
            self.result(' \n')
        result = self.result('Skills\n' + '\n'.join(f'Unknown{i}' for i in range(150)) + '\n' + 'x' * 2100)
        self.assertEqual(len(result.suggestions), schema.MAX_SKILLS)
        self.assertTrue(any('long lines' in message for message in result.notices))

    def test_time_budget_aborts(self):
        with patch('resume.intelligence.pipeline.monotonic', side_effect=[0, 6]):
            with self.assertRaises(AnalysisUnavailable):
                self.result('Skills: Python')


class ReviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.owner = users.create_user('resume-owner')
        cls.other = users.create_user('resume-other')
        cls.python = Skill.objects.create(name='Python')
        cls.sql = Skill.objects.create(name='SQL')
        Skill.objects.bulk_create([Skill(name='PCB Testing'), Skill(name='pcb testing')])
        cls.document = cls.create_document(cls.owner)
        cls.foreign = cls.create_document(cls.other, 'Skills: PrivateOtherSkill')

    @staticmethod
    def create_document(owner, text='Skills: Python, PCB Testing\nEducation: Diploma in IT, 2024'):
        return ResumeDocument.objects.create(owner=owner, original_filename='synthetic.pdf', file_type='pdf',
                                             file_size=30, checksum='a' * 64,
                                             status=ResumeDocument.Status.COMPLETED, extracted_text=text)

    def setUp(self):
        self.client.force_login(self.owner)

    def url(self, endpoint, document=None, *parts):
        return reverse('resume:analysis_' + endpoint, args=[(document or self.document).pk, *parts])

    def run_analysis(self, **payload):
        return self.client.post(self.url('run'), payload)

    def analysis(self):
        self.assertEqual(self.run_analysis().status_code, 302)
        return self.document.analyses.first()

    def decide(self, item, decision, **payload):
        return self.client.post(self.url('review', None, item.analysis_id, item.pk),
                                {'decision': decision, 'review_version': item.review_version, **payload})

    def test_repeat_analysis_is_idempotent_and_starts_pending(self):
        analysis = self.analysis()
        self.assertEqual(self.run_analysis().url, self.url('detail', None, analysis.pk))
        self.assertEqual(self.document.analyses.count(), 1)
        self.assertEqual(analysis.revision, 1)
        self.assertEqual(analysis.source_checksum, 'a' * 64)
        self.assertEqual(analysis.extractor_version, schema.EXTRACTOR_VERSION)
        self.assertEqual(analysis.suggestions.filter(review_state='pending').count(), 3)

    def test_confirm_reject_and_correct_keep_machine_evidence(self):
        analysis = self.analysis()
        python = analysis.suggestions.get(value='Python')
        ambiguous = analysis.suggestions.get(value='PCB Testing')
        education = analysis.suggestions.get(category='education')
        self.assertEqual(self.decide(python, 'confirmed').status_code, 302)
        self.assertEqual(self.decide(ambiguous, 'confirmed').status_code, 400)
        self.assertEqual(self.decide(ambiguous, 'corrected', value='PCB testing',
                                     catalog_identity='PCB Testing').status_code, 400)
        self.assertEqual(self.decide(ambiguous, 'corrected', value='SQL queried', catalog_identity=self.sql.pk).status_code, 302)
        self.assertEqual(self.decide(education, 'corrected', qualification='Diploma in IT', institution='Politeknik Reka').status_code, 302)
        for item in (python, ambiguous, education):
            item.refresh_from_db()
        self.assertEqual(python.review_state, 'confirmed')
        self.assertEqual(ambiguous.review_state, 'corrected')
        self.assertEqual(ambiguous.corrected_skill_id, self.sql.pk)
        self.assertEqual(ambiguous.evidence[0]['excerpt'], 'PCB Testing')
        self.assertFalse(ambiguous.canonical_snapshot)
        self.assertEqual(education.correction['fields']['institution'], 'Politeknik Reka')
        self.assertNotIn('institution', education.fields)
        self.assertEqual(self.decide(python, 'rejected').status_code, 302)
        python.refresh_from_db()
        self.assertEqual(python.review_state, 'rejected')

    def test_rerun_confirmation_and_review_history(self):
        old = self.analysis()
        item = old.suggestions.get(value='Python')
        self.assertEqual(self.decide(item, 'corrected', value='Python scripting', catalog_identity=self.python.pk).status_code, 302)
        self.assertEqual(self.run_analysis(rerun='true').status_code, 400)
        self.assertEqual(self.run_analysis(rerun='true', latest=old.pk).status_code, 302)
        self.assertEqual(self.run_analysis(rerun='true', latest=old.pk).status_code, 409)
        new = self.document.analyses.first()
        self.assertEqual(new.revision, 2)
        self.assertEqual(new.suggestions.get(value='Python').review_state, 'pending')
        old_page = self.client.get(self.url('detail', None, old.pk))
        self.assertContains(old_page, 'Python scripting')

    def test_source_text_file_and_extractor_changes_create_revisions(self):
        first = self.analysis()
        ResumeDocument.objects.filter(pk=self.document.pk).update(extracted_text='Skills: SQL')
        historical = self.client.get(self.url('detail', None, first.pk))
        self.assertContains(historical, 'read-only')
        self.assertEqual(self.decide(first.suggestions.first(), 'confirmed').status_code, 409)
        second = self.analysis()
        self.assertNotEqual(first.text_checksum, second.text_checksum)
        ResumeDocument.objects.filter(pk=self.document.pk).update(checksum='b' * 64)
        third = self.analysis()
        self.assertNotEqual(second.source_checksum, third.source_checksum)
        with patch('resume.intelligence.schema.EXTRACTOR_VERSION', 'test-new-version'):
            fourth = self.analysis()
        self.assertEqual(fourth.revision, 4)
        self.assertEqual(fourth.extractor_version, 'test-new-version')

    def test_review_version_prevents_stale_browser_resubmission(self):
        item = self.analysis().suggestions.get(value='Python')
        self.assertEqual(self.decide(item, 'confirmed').status_code, 302)
        self.assertEqual(self.decide(item, 'rejected').status_code, 409)
        item.refresh_from_db()
        self.assertEqual(item.review_state, 'confirmed')

    def test_failed_source_and_excessive_source_are_rejected(self):
        for status, text in [('failed', 'Skills: Python'), ('no_extractable_text', ''),
                             ('completed', ' '), ('completed', 'A' * (MAX_TEXT_CHARS + 1))]:
            with self.subTest(status=status, size=len(text)):
                ResumeDocument.objects.filter(pk=self.document.pk).update(status=status, extracted_text=text)
                self.assertEqual(self.run_analysis().status_code, 422)
        self.assertFalse(ResumeAnalysis.objects.exists())

    def test_history_limit_leaves_prior_revision_intact(self):
        analysis = self.analysis()
        with patch('resume.intelligence.schema.MAX_REVISIONS', 1):
            self.assertEqual(self.run_analysis(rerun='true', latest=analysis.pk).status_code, 409)
        self.assertEqual(self.document.analyses.count(), 1)

    def test_analysis_failure_and_persistence_rollback(self):
        with patch('resume.services.intelligence.DeterministicExtractor.extract', side_effect=AnalysisUnavailable):
            self.assertEqual(self.run_analysis().status_code, 503)
        bulk_create = ResumeSuggestion.objects.bulk_create

        def fail_after_insert(*args, **kwargs):
            bulk_create(*args, **kwargs)
            raise DatabaseError('do not expose backend details')

        with patch('resume.services.intelligence.models.ResumeSuggestion.objects.bulk_create', side_effect=fail_after_insert):
            response = self.run_analysis()
        self.assertNotContains(response, 'backend details', status_code=503)
        self.assertFalse(ResumeAnalysis.objects.exists())
        self.assertFalse(ResumeSuggestion.objects.exists())
        self.assertEqual(self.run_analysis().status_code, 302)

    def test_database_rejects_duplicate_revisions(self):
        analysis = self.analysis()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ResumeAnalysis.objects.create(document=self.document, revision=analysis.revision,
                source_checksum=analysis.source_checksum, text_checksum=analysis.text_checksum,
                extractor_version=analysis.extractor_version)

    def test_document_deletion_cascades_review_history(self):
        analysis = self.analysis()
        self.assertEqual(self.client.post(reverse('resume:delete', args=[self.document.pk])).status_code, 302)
        self.assertFalse(ResumeAnalysis.objects.filter(pk=analysis.pk).exists())
        self.assertFalse(ResumeSuggestion.objects.filter(analysis_id=analysis.pk).exists())

    def test_catalog_deletion_retains_snapshot(self):
        item = self.analysis().suggestions.get(value='Python')
        self.python.delete()
        item.refresh_from_db()
        self.assertIsNone(item.canonical_skill_id)
        self.assertEqual(item.canonical_snapshot['name'], 'Python')

    def test_anonymous_access_and_method_guards(self):
        analysis = self.analysis()
        item = analysis.suggestions.first()
        self.assertEqual(self.client.get(self.url('run')).status_code, 405)
        self.assertEqual(self.client.get(self.url('review', None, analysis.pk, item.pk)).status_code, 405)
        self.client.logout()
        paths = [('get', self.url('index')), ('get', self.url('detail', None, analysis.pk)),
                 ('post', self.url('run')), ('get', self.url('correct', None, analysis.pk, item.pk)),
                 ('post', self.url('review', None, analysis.pk, item.pk))]
        for method, url in paths:
            response = getattr(self.client, method)(url)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response['Cache-Control'], 'private, no-store')

    def test_owner_and_nested_resource_scope(self):
        analysis = self.analysis()
        item = analysis.suggestions.first()
        second = self.create_document(self.owner)
        self.assertEqual(self.client.get(self.url('detail', second, analysis.pk)).status_code, 404)
        self.client.force_login(self.other)
        for name, parts in (('index', ()), ('detail', (analysis.pk,)), ('correct', (analysis.pk, item.pk))):
            response = self.client.get(self.url(name, None, *parts))
            self.assertNotContains(response, 'Python', status_code=404)
        self.assertEqual(self.run_analysis().status_code, 404)
        self.assertEqual(self.decide(item, 'rejected').status_code, 404)
        self.assertEqual(self.client.get(self.url('detail', self.foreign, analysis.pk)).status_code, 404)

    def test_privacy_headers_and_csrf(self):
        analysis = self.analysis()
        item = analysis.suggestions.first()
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        for response in (browser.get(self.url('detail', None, analysis.pk)), browser.post(self.url('run')),
                         browser.post(self.url('review', None, analysis.pk, item.pk), {'decision': 'confirmed'})):
            self.assertEqual(response['Cache-Control'], 'private, no-store')
            self.assertEqual(response['Referrer-Policy'], 'no-referrer')
            self.assertIn("connect-src 'self'", response['Content-Security-Policy'])
        self.assertEqual(browser.post(self.url('run')).status_code, 403)
        self.assertEqual(browser.post(self.url('review', None, analysis.pk, item.pk)).status_code, 403)
        token = browser.cookies['csrftoken'].value
        self.assertEqual(browser.post(self.url('review', None, analysis.pk, item.pk),
            {'decision': 'confirmed', 'review_version': item.review_version, 'csrfmiddlewaretoken': token}).status_code, 302)

    @override_settings(RESUME_ANALYSES_PER_DAY=1, RESUME_REVIEWS_PER_MINUTE=1)
    def test_analysis_and_review_limits_and_retry_headers(self):
        analysis = self.analysis()
        response = self.run_analysis()
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response['Retry-After'], '86400')
        item = analysis.suggestions.get(value='Python')
        self.assertEqual(self.decide(item, 'confirmed').status_code, 302)
        self.assertEqual(self.decide(item, 'rejected').status_code, 429)

    def test_existing_work_lease_rejects_overlapping_analysis_and_review(self):
        item = self.analysis().suggestions.get(value='Python')
        with user_work_lock(self.owner):
            self.assertEqual(self.run_analysis().status_code, 409)
            self.assertEqual(self.decide(item, 'confirmed').status_code, 409)
        self.assertEqual(self.decide(item, 'confirmed').status_code, 302)

    def test_source_change_during_extraction_aborts_write(self):
        original = DeterministicExtractor.extract

        def change_source(extractor, text):
            output = original(extractor, text)
            ResumeDocument.objects.filter(pk=self.document.pk).update(extracted_text='Skills: SQL')
            return output

        with patch.object(DeterministicExtractor, 'extract', change_source):
            self.assertEqual(self.run_analysis().status_code, 409)
        self.assertFalse(ResumeAnalysis.objects.exists())

    def test_escaped_evidence_and_correction_and_no_auto_integration(self):
        response_record = UserResponse.objects.create(user=self.owner)
        rating = SkillRating.objects.create(response=response_record, skill_name='SQL', rating=2)
        UserProfile.objects.create(user=self.owner, field_of_study='Computing/IT', experience_level='No experience')
        mark = '<script>example()</script>'
        ResumeDocument.objects.filter(pk=self.document.pk).update(extracted_text=f'Skills: Python {mark}')
        with patch('socket.socket.connect', side_effect=AssertionError('network forbidden')), \
                patch('recommender.cache.compute_and_cache', side_effect=AssertionError('compute forbidden')):
            analysis = self.analysis()
            item = analysis.suggestions.get(value='Python')
            self.assertEqual(self.decide(item, 'corrected', value=mark).status_code, 302)
            page = self.client.get(self.url('detail', None, analysis.pk))
        self.assertContains(page, '&lt;script&gt;example()&lt;/script&gt;')
        self.assertNotContains(page, mark)
        self.assertEqual(list(SkillRating.objects.values_list('pk', 'rating')), [(rating.pk, 2)])
        self.assertEqual(UserProfile.objects.get(user=self.owner).experience_level, 'No experience')
        self.assertFalse(RecommendationRun.objects.exists())
        self.assertFalse(CachedRecommendation.objects.exists())
