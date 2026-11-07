"""Small explicit examples reviewed against exported descriptions, never keyword rules."""
from django.db import transaction

from .models import Career, CareerEnrichment, CareerFamily, ReviewStatus, Skill, SkillAlias
from .normalization import normalize_label

FAMILIES = {
    "software-it": "Software & IT",
    "cybersecurity": "Cybersecurity",
    "data-analytics": "Data & Analytics",
    "engineering": "Engineering",
    "healthcare": "Healthcare",
    "business-management": "Business & Management",
    "finance-accounting": "Finance & Accounting",
    "education": "Education",
    "creative-media": "Creative & Media",
    "sales-marketing": "Sales & Marketing",
    "science-research": "Science & Research",
    "law-public-services": "Law & Public Services",
    "skilled-trades": "Skilled Trades",
    "hospitality-tourism": "Hospitality & Tourism",
    "agriculture-environment": "Agriculture & Environment",
    "social-community": "Social & Community Services",
}
# A curated subset, not an automatic map from the 12 legacy industries. Every
# other career remains explicitly unclassified until separately reviewed.
CLASSIFICATIONS = {
    "software developer": ("software-it", "Implements software from specifications using programming languages."),
    "cloud engineer": ("software-it", "Designs and maintains cloud systems and applications."),
    "ICT security administrator": ("cybersecurity", "Plans security measures protecting information and data."),
    "ICT security engineer": ("cybersecurity", "Designs and implements system security architecture."),
    "digital forensics expert": ("cybersecurity", "Examines digital evidence and recovers protected or damaged information."),
    "data scientist": ("data-analytics", "Interprets data sources and develops mathematical models and insights."),
    "data analyst": ("data-analytics", "Cleans, models, interprets and communicates data for business goals."),
    "automation engineer": ("engineering", "Designs production automation systems and industrial robotics."),
    "physiotherapist": ("healthcare", "Supports motor function, movement and physical rehabilitation."),
    "pharmacist": ("healthcare", "Prepares medicines and provides clinical information about medication."),
    "branch manager": ("business-management", "Manages employees, operations and strategy of a business branch."),
    "warehouse manager": ("business-management", "Manages storage facilities, operations and staff."),
    "accountant": ("finance-accounting", "Analyses financial statements and supports financial reporting."),
    "financial auditor": ("finance-accounting", "Examines financial data and governance for accuracy."),
    "computer science lecturer": ("education", "Teaches computer science and conducts academic research."),
    "performance lighting designer": ("creative-media", "Develops artistic lighting concepts for performances."),
    "sound designer": ("creative-media", "Develops and supervises artistic performance sound concepts."),
    "hardware and paint specialised seller": ("sales-marketing", "Sells hardware and paint in specialised shops, rather than designing creative work."),
    "hardware and paint shop manager": ("sales-marketing", "Manages a specialist retail shop; separate from the preserved Creative & Design legacy tag."),
    "clothing specialised seller": ("sales-marketing", "Sells clothing in specialised shops."),
    "chemist": ("science-research", "Performs laboratory research and chemical analysis."),
    "food analyst": ("science-research", "Performs chemical, physical and microbiological food tests, rather than financial analysis."),
    "lawyer": ("law-public-services", "Provides legal advice and represents clients in legal proceedings."),
    "landscape gardener": ("agriculture-environment", "Constructs and maintains gardens, parks and public green spaces."),
    "environmental scientist": ("agriculture-environment", "Analyses environmental samples and advises on environmental hazards and policy."),
    "spa manager": ("hospitality-tourism", "Manages a guest-facing spa establishment and its day-to-day operations."),
    "consultant social worker": ("social-community", "Develops social work practice, policy and training."),
    "clinical social worker": ("social-community", "Provides counselling and intervention in a social-care context."),
}
LOCAL_EXAMPLES = {
    "software developer": {
        "titles": {"en-MY": ["Software Developer", "Application Developer"]},
        "evidence": "https://myjobprofile.dosm.gov.my/bda-myjobprofile/job/2512/software-developers",
        "note": "Titles listed in Malaysia's MyJobProfile software-developers group; local labels, not one-to-one ESCO crosswalks or eligibility claims.",
    },
}
ALIAS_EXAMPLES = [
    ("JavaScript", "JS", "https://developer.mozilla.org/en-US/docs/Web/JavaScript"),
    ("PostgreSQL", "Postgres", "https://wiki.postgresql.org/wiki/FAQ"),
]


def seed_examples(*, dry_run=False):
    counts = {"families_created": 0, "enrichments_created": 0, "aliases_created": 0, "skipped": 0}
    warnings = []
    with transaction.atomic():
        families = {}
        for slug, name in FAMILIES.items():
            family, created = CareerFamily.objects.get_or_create(slug=slug, defaults={"name": name})
            families[slug] = family
            counts["families_created"] += created
        careers = {}
        for career in Career.objects.all():
            careers.setdefault(normalize_label(career.title), []).append(career)
        for title, (family, rationale) in CLASSIFICATIONS.items():
            matches = careers.get(normalize_label(title), [])
            if len(matches) != 1:
                warnings.append(f"Skipped missing or ambiguous career: {title}")
                continue
            career = matches[0]
            local = LOCAL_EXAMPLES.get(title)
            metadata = {"review_scope": "CareerCoach family only, not an ESCO reclassification or Malaysian licensing claim",
                        "reviewer": "Phase 2A implementation review", "rationale": rationale,
                        "evidence": [{"type": "legacy_export_description", "title": title, "file": "careers_clean (1).csv"}]}
            if local:
                metadata["localization"] = local
            _, created = CareerEnrichment.objects.get_or_create(career=career, defaults={
                "family": families[family], "review_status": ReviewStatus.REVIEWED,
                "review_metadata": metadata, "localized_titles": local["titles"] if local else {},
            })
            counts["enrichments_created"] += created
            counts["skipped"] += not created
        for canonical, name, evidence in ALIAS_EXAMPLES:
            matches = list(Skill.objects.filter(name=canonical))
            if len(matches) != 1:
                warnings.append(f"Skipped missing canonical skill: {canonical}")
                continue
            alias = SkillAlias.objects.filter(normalized_name=normalize_label(name)).first()
            if alias:
                counts["skipped"] += 1
                if alias.skill_id != matches[0].pk:
                    warnings.append(f"Existing alias belongs to another concept; not overwritten: {name}")
                continue
            SkillAlias.objects.create(skill=matches[0], name=name, kind=SkillAlias.Kind.EXACT,
                                      review_status=ReviewStatus.REVIEWED,
                                      review_metadata={"evidence": [evidence], "review_scope": "exact name abbreviation only"})
            counts["aliases_created"] += 1
        if dry_run:
            transaction.set_rollback(True)
    return {"dry_run": dry_run, "counts": counts, "warnings": warnings}
