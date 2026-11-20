"""Run deterministic extraction with explicit work and output budgets."""
from time import monotonic

from django.views.decorators.debug import sensitive_variables

from resume.constants import MAX_TEXT_CHARS

from .matching import Catalog, CatalogLimit
from .records import structured_suggestions
from .schema import MAX_SECTIONS, MAX_SKILLS, MAX_STRUCTURED_PER_SECTION, MAX_SUGGESTIONS, Extraction
from .sections import bounded_lines, split_sections
from .skills import extract_skills


class AnalysisUnavailable(Exception):
    pass


class UnsupportedText(Exception):
    pass


ANALYSIS_SECONDS = 5


@sensitive_variables()
def validate_text(text):
    if len(text) > MAX_TEXT_CHARS or not text.strip():
        raise UnsupportedText


class DeterministicExtractor:
    """Accepts only Phase 3A text. No external clients or model dependencies."""

    @sensitive_variables()
    def extract(self, text):
        validate_text(text)
        deadline = monotonic() + ANALYSIS_SECONDS

        def check_budget():
            if monotonic() >= deadline:
                raise AnalysisUnavailable

        detected = split_sections(text)
        notices = []
        if len(detected) > MAX_SECTIONS:
            detected = detected[:MAX_SECTIONS]
            notices.append('Later sections were skipped because the document reached the section limit.')
        sections = bounded_lines(detected)
        if not any(section.kind in ('skills', 'education', 'experience', 'projects') for section, _ in sections):
            notices.append('No reliable skills, education, work, or project headings were found. Review the detected evidence.')
        if any(len(original) != len(bounded) for (_, original), (_, bounded) in zip(detected, sections)):
            notices.append('Some long lines were skipped. Refer to the original text preview.')
        try:
            skills, references = extract_skills(sections, Catalog(check_budget), check_budget)
        except CatalogLimit:
            raise AnalysisUnavailable from None
        structured = list(structured_suggestions(sections, references, check_budget))
        check_budget()
        suggestions = [*skills, *structured]
        if (len(suggestions) >= MAX_SUGGESTIONS or len(skills) >= MAX_SKILLS
                or any(sum(row.category == category for row in structured) >= MAX_STRUCTURED_PER_SECTION
                       for category in ('education', 'experience', 'project'))):
            notices.append('A suggestion limit was reached. Later mentions may be omitted.')
        return Extraction([section for section, _ in detected], suggestions[:MAX_SUGGESTIONS], tuple(notices))
