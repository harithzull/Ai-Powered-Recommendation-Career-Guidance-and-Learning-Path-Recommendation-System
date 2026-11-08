"""Reproducible data-quality checks; heuristics are review suggestions, not facts."""
from collections import Counter, defaultdict
import re

from .normalization import normalize_label

CATEGORIES = {"skill/competence", "knowledge", ""}
LEVELS = {"basic", "intermediate", "advanced", ""}
INDUSTRIES = {"Technology", "Data & AI", "Engineering", "Healthcare", "Business", "Finance", "Education",
              "Creative & Design", "Marketing", "Research", "Law", "Communication"}
# Explicit analyst review cases, checked against both title and description by the
# curator; these are warnings, never an automatic reassignment or ground truth.
CLASSIFICATION_REVIEW = {
    "hardware and paint specialised seller": "Retail sales is questionable under Creative & Design.",
    "hardware and paint shop manager": "Retail management is questionable under Creative & Design.",
    "landscape gardener": "Horticultural work needs review under Creative & Design.",
    "food analyst": "Laboratory/food analysis needs review under Finance.",
    "aviation inspector": "Aviation inspection needs review under Finance.",
    "industrial quality manager": "Industrial quality management needs review under Finance.",
    "office clerk": "General clerical work is not intrinsically Law.",
    "billing clerk": "Billing is not intrinsically Law.",
    "meteorologist": "Scientific occupation needs review under Data & AI.",
    "data protection officer": "Governance/legal responsibilities span several families.",
}


def audit_tables(tables, max_examples=20):
    findings = []

    def issue(code, category, table, records, message, action):
        if not records:
            return
        examples = records if max_examples == 0 else records[:max_examples]
        findings.append({"code": code, "category": category, "table": table,
                         "count": len(records), "records": examples,
                         "examples_truncated": len(examples) < len(records),
                         "message": message, "suggested_action": action})

    def identity(kind, row):
        values = row.values
        result = {"line": row.line}
        for name in (["title"] if kind == "careers" else ["name"] if kind == "skills" else ["career", "skill"]):
            result[name] = values.get(name, "")
        return result

    counts = {}
    indexes = {}
    for kind, table in tables.items():
        counts[kind] = len(table.rows)
        issue("csv_structure", "error", kind, table.errors, "Unreadable or malformed CSV.", "Correct the CSV before importing.")
        if kind == "relationships":
            continue
        label = "title" if kind == "careers" else "name"
        grouped = defaultdict(list)
        exact = defaultdict(list)
        for row in table.rows:
            grouped[normalize_label(row.values[label])].append(row)
            exact[row.values[label]].append(row)
        indexes[kind] = grouped
        for code, groups in [("duplicate_labels", exact), ("normalized_duplicate_labels", grouped)]:
            issue(code, "error", kind,
                  [{"key": key, "rows": [identity(kind, r) for r in group]} for key, group in groups.items() if len(group) > 1],
                  "More than one row has the same matching key.", "Resolve duplicates manually; do not merge automatically.")
        for code, category, predicate, message, action in [
            ("missing_label", "error", lambda r: not normalize_label(r[label]), "Required label is empty.", "Supply a source label."),
            ("missing_description", "review", lambda r: not r["description"].strip(), "Description is missing.", "Recover original text from a verified source."),
            ("low_information_description", "review", lambda r: bool(r["description"].strip()) and len(r["description"].split()) < 8,
             "Fewer than eight words: a review heuristic, not proof of poor quality.", "Review the full description in context."),
            ("inconsistent_whitespace", "review", lambda r: r[label] != " ".join(r[label].split()),
             "Label contains leading, trailing, or repeated whitespace.", "Normalize the lookup key; preserve exported text in provenance."),
            ("capitalization_review", "review", lambda r: len(r[label]) > 6 and r[label].isupper(),
             "All-uppercase label may be an acronym or inconsistent capitalization.", "Review; do not title-case acronyms automatically."),
            ("missing_source_identifier", "unknown", lambda r: not r.get("esco_uri", "").strip(),
             "The export does not provide an ESCO URI.", "Leave unknown; recover only from an authoritative, reviewed mapping."),
        ]:
            issue(code, category, kind, [identity(kind, row) for row in table.rows if predicate(row.values)], message, action)

    careers, skills = tables["careers"].rows, tables["skills"].rows
    issue("classification_review", "review", "careers",
          [{**identity("careers", r), "industry": r.values["industry"], "reason": CLASSIFICATION_REVIEW[normalize_label(r.values["title"])]}
           for r in careers if normalize_label(r.values["title"]) in CLASSIFICATION_REVIEW],
          "Explicit legacy classification review list; no source classification is overwritten.", "Review activities and descriptions; curate a separate CareerCoach family.")
    issue("unknown_legacy_industry", "review", "careers", [identity("careers", r) for r in careers if r.values["industry"] not in INDUSTRIES],
          "Industry is outside the legacy scoring map.", "Review without changing scoring in Phase 2A.")
    issue("potentially_outdated_label", "review", "careers", [identity("careers", r) for r in careers
          if any(word in normalize_label(r.values["title"]) for word in ["switchboard operator", "typist", "telegraph"])],
          "Possibly dated terminology; heuristic only.", "Verify current terminology and retain historical labels as aliases.")
    issue("invalid_category", "error", "skills", [identity("skills", r) for r in skills if r.values["category"] not in CATEGORIES],
          "Unknown skill category.", "Use knowledge, skill/competence, or an explicitly unknown category.")
    issue("unknown_category", "unknown", "skills", [identity("skills", r) for r in skills if not r.values["category"]],
          "Skill/knowledge category is not provided.", "Recover category; do not infer a practical skill from knowledge.")

    # Token overlap only creates a review queue. No fuzzy matching is used by imports.
    overlaps = []
    for i, first in enumerate(careers):
        left = set(normalize_label(first.values["title"]).split())
        for second in careers[i + 1:]:
            right = set(normalize_label(second.values["title"]).split())
            if left and right and left != right and len(left & right) / len(left | right) >= 0.6:
                overlaps.append({"first": identity("careers", first), "second": identity("careers", second)})
    issue("overlapping_titles", "review", "careers", overlaps, "Title-token overlap >= 0.6; specializations may be legitimately distinct.",
          "Review descriptions; never auto-merge.")
    punctuation_keys = defaultdict(list)
    for row in skills:
        # Preserve semantic punctuation: C++, C#, .NET, and C are distinct.
        punctuation_keys[re.sub(r"[\s_-]", "", normalize_label(row.values["name"]))].append(row)
    issue("potential_skill_synonyms", "review", "skills",
          [{"key": key, "rows": [identity("skills", r) for r in group]} for key, group in punctuation_keys.items() if len(group) > 1],
          "Names differ only by hyphens, underscores or spacing; equivalence is unverified.", "Use reviewed aliases; never merge distinct competencies by this heuristic.")
    issue("unverified_work_environment", "unknown", "careers", [identity("careers", r) for r in careers if r.values["work_environment"]],
          "Work-environment labels have no identified original source; all current records use hybrid.",
          "Preserve legacy display behavior but do not present this as verified Malaysian market evidence.")

    linked_careers, linked_skills = set(), set()
    relations = defaultdict(list)
    invalid_careers, invalid_skills, invalid_values, missing_meta = [], [], [], []
    for row in tables["relationships"].rows:
        r = row.values
        career, skill = normalize_label(r["career"]), normalize_label(r["skill"])
        relations[(career, skill)].append(row)
        ref = identity("relationships", row)
        if career not in indexes.get("careers", {}):
            invalid_careers.append(ref)
        else:
            linked_careers.add(career)
        if skill not in indexes.get("skills", {}):
            invalid_skills.append(ref)
        else:
            linked_skills.add(skill)
        try:
            importance = int(r["importance"]) if r["importance"] else None
            valid = importance is None or 0 <= importance <= 32767
        except ValueError:
            valid = False
        if not valid or r["required_level"] not in LEVELS or r["is_core"].casefold() not in {"true", "false", ""} or r["skill_type"] not in CATEGORIES:
            invalid_values.append(ref)
        if any(not r[field].strip() for field in ["skill_type", "required_level", "importance", "is_core"]):
            missing_meta.append(ref)
    for code, records, message in [
        ("invalid_career_reference", invalid_careers, "Relationship points to an absent career."),
        ("invalid_skill_reference", invalid_skills, "Relationship points to an absent skill."),
        ("invalid_relationship_values", invalid_values, "Relationship values fail validation."),
        ("duplicate_relationship", [{"key": list(key), "rows": [identity("relationships", r) for r in group]}
                                    for key, group in relations.items() if len(group) > 1], "Duplicate career/skill pair."),
    ]:
        issue(code, "error", "relationships", records, message, "Correct the source interchange file before importing.")
    issue("missing_relationship_metadata", "unknown", "relationships", missing_meta,
          "Some legacy relationship metadata is missing.", "Leave authoritative metadata unknown; recover evidence rather than inventing values.")
    issue("unlinked_careers", "review", "careers", [identity("careers", r) for r in careers if normalize_label(r.values["title"]) not in linked_careers],
          "Career has no linked skill in this export.", "Review relationship extraction coverage.")
    issue("unlinked_skills", "review", "skills", [identity("skills", r) for r in skills if normalize_label(r.values["name"]) not in linked_skills],
          "Skill has no linked career in this export.", "Retain; verify whether the subset intentionally includes it.")
    patterns = Counter((r.values["importance"], r.values["required_level"], r.values["is_core"]) for r in tables["relationships"].rows)
    issue("unverified_legacy_estimates", "unknown", "relationships",
          [{"pattern": list(pattern), "relationship_count": count} for pattern, count in sorted(patterns.items())],
          "Numeric weights and proficiency values have no documented original ESCO provenance.",
          "Keep legacy behavior; leave authoritative importance/proficiency null.")
    summary = {category: sum(f["count"] for f in findings if f["category"] == category) for category in ["error", "review", "optional", "unknown"]}
    return {"schema_version": 1, "input_kind": "legacy_csv", "source_taxonomy": "esco",
            "source_version": None, "counts": counts, "finding_counts": summary,
            "statistics": {"industries": dict(Counter(r.values["industry"] for r in careers)),
                           "skill_categories": dict(Counter(r.values["category"] for r in skills)),
                           "shortened_summary_prefixes": sum(r.values["description"].startswith(r.values["summary"]) and r.values["description"] != r.values["summary"] for r in careers)},
            "files": {kind: {"filename": table.filename, "sha256": table.sha256, "columns": table.columns} for kind, table in tables.items()},
            "findings": findings,
            "limitations": ["Heuristics flag review candidates, not confirmed classification errors.",
                            "Original ESCO version, URIs, extraction process, and transformation scripts are unknown.",
                            "Counts are finding instances, not unique affected records."]}
