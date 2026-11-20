"""Validate review actions while keeping user edits apart from extraction."""
from django import forms
from django.views.decorators.debug import sensitive_variables

from recommender.models import Skill
from recommender.normalization import normalize_label
from resume.models import ResumeSuggestion

from .matching import skill_snapshot
from .schema import MAX_VALUE_CHARS


FIELDS = {
    'education': {
        'qualification': 'Qualification', 'field_of_study': 'Field of study', 'institution': 'Institution',
        'stated_date': 'Stated date', 'graduation_date': 'Graduation date',
        'expected_graduation_date': 'Expected graduation date', 'study_status': 'Study status',
    },
    'experience': {
        'job_title': 'Job title', 'organization': 'Organization', 'start_date': 'Start date',
        'end_date': 'End date', 'stated_date': 'Stated date', 'current_employment': 'Current employment',
        'employment_type': 'Employment type', 'description': 'Description',
        'technologies_or_skills': 'Technologies or skills',
    },
    'project': {
        'project_name': 'Project name', 'project_type': 'Project type', 'description': 'Description',
        'technologies': 'Technologies', 'role_or_contributions': 'Role or contributions', 'project_url': 'Project URL',
    },
}


class AnalyzeForm(forms.Form):
    rerun = forms.BooleanField(required=False)
    latest = forms.UUIDField(required=False)

    def clean(self):
        values = super().clean()
        if bool(values.get('rerun')) != bool(values.get('latest')):
            raise forms.ValidationError('Reload the analysis and submit the form again.')
        return values


class ReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=ResumeSuggestion.ReviewState.choices[1:], widget=forms.HiddenInput)
    review_version = forms.IntegerField(min_value=0, max_value=2_147_483_646, widget=forms.HiddenInput)


class CorrectionForm(ReviewForm):
    def __init__(self, suggestion, data=None):
        self.suggestion = suggestion
        correction = suggestion.correction
        super().__init__(data, initial={
            'decision': ResumeSuggestion.ReviewState.CORRECTED, 'review_version': suggestion.review_version,
        })
        if suggestion.category == ResumeSuggestion.Category.SKILL:
            self.fields['value'] = forms.CharField(max_length=500, label='Skill as you describe it',
                                                  initial=correction.get('value', suggestion.value))
            self.fields['catalog_identity'] = forms.CharField(
                required=False, max_length=500, label='Catalog ID, exact name, or ESCO URI',
                initial=correction.get('canonical', suggestion.canonical_snapshot).get('id'),
                help_text='Leave blank to record your wording without a catalog mapping.',
            )
        else:
            values = correction.get('fields', suggestion.fields)
            for index, (key, label) in enumerate(FIELDS[suggestion.category].items()):
                self.fields[key] = forms.CharField(label=label, max_length=MAX_VALUE_CHARS,
                                                    required=index == 0, initial=values.get(key, ''))

    @sensitive_variables()
    def clean(self):
        values = super().clean()
        if self.suggestion.category != ResumeSuggestion.Category.SKILL:
            values['correction'] = {'fields': {key: values[key] for key in FIELDS[self.suggestion.category]
                                               if values.get(key)}}
            return values
        identity = values.get('catalog_identity')
        canonical = {}
        if identity:
            matches = self._catalog_matches(identity)
            if len(matches) != 1:
                self.add_error('catalog_identity', 'Enter a single catalog identity. Use the numeric catalog ID when a label is ambiguous.')
            else:
                canonical = skill_snapshot(matches[0])
        if values.get('value'):
            values['correction'] = {'value': values['value'], 'normalized': normalize_label(values['value']),
                                    'canonical': canonical}
        return values

    @staticmethod
    @sensitive_variables()
    def _catalog_matches(value):
        skills = Skill.objects.order_by('pk')
        if value.isascii() and value.isdecimal() and len(value) <= 18:
            return list(skills.filter(pk=int(value))[:1])
        if value.startswith(('http://', 'https://')):
            return list(skills.filter(esco_uri__iexact=value)[:2])
        return list(skills.filter(name__iexact=value)[:2])
