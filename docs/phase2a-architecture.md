# Phase 2A: dependency analysis and design

Base: local main `ea4397e` (merged Phase 1, `07c0ea0`). Local main was
fast-forwarded with approval before creating `phase2a/career-knowledge-base`.
No separate local CI fix existed to carry forward. The last remote Phase 1/main
workflow runs reported failure; that is not treated as successful CI validation.

## Existing data flow and compatibility contract

```
legacy CSV files -> import_data -> Career / Skill / CareerSkill
                                   |          |
                                   |          +-> build_skill_vectors -> name-indexed .npy store
                                   +-> industry -> RIASEC/background scores
assessment -> UserResponse / SkillRating -> encoder -> semantic skill matching
                                                 -> recommendations -> per-user cache
                                                 -> saved roadmap / progress / chatbot
```

| Existing fields | Consumers | Phase 2A rule |
| --- | --- | --- |
| Career PK | CareerSkill, SavedRoadmap, RoadmapProgress, cached JSON, URL paths | Never recreate existing rows |
| title, summary, description | Results, roadmap prompts, cache, templates, admin | Preserve display fields on source refresh |
| industry | recommender/scoring.py, constants.py, assessment/suggested_skills.py, cache, templates, roadmap prompt | Preserve legacy classification; new families are separate and do not feed scoring |
| work_environment | Results, cache, roadmap template | Preserve; source authenticity unknown |
| Skill PK, name | CareerSkill, skill search, suggested pills, vector name index | Preserve canonical names and IDs; resolve aliases separately |
| Skill description/category | Vector generation, admin | Source snapshots separate from existing canonical embedding inputs |
| CareerSkill importance/is_core | Weighted cosine matching, missing-core gaps, adaptive skill suggestions, roadmap | Preserve existing legacy values; never claim verified ESCO importance |
| CareerSkill required_level/skill_type | Admin and roadmap prompt | Preserve legacy values; new authoritative fields remain unknown unless supplied |
| User skill names | assessment models/views, recommendations, roadmap | Do not rewrite past user selections |
| CachedRecommendation | dashboard, context processor, results, chatbot | Invalidate on catalog/alias changes, never delete saved user roadmaps during import |

The existing importer deletes and recreates the entire catalog. Phase 2A replaces
that behavior with atomic upserts and a dry run. Existing .npy vectors remain
byte-for-byte unchanged: Phase 2A does not change encoder inputs or scoring.

## Smallest schema extension

Keep the three existing core models and compatibility fields. Add optional source
taxonomy/URI, exported source labels/descriptions, source metadata, and quality state
to Career and Skill. Legacy export snapshots are explicitly **not** verified original
ESCO records. Keep missing version, URI, source relation type, and authoritative
importance/proficiency unknown.

Add CareerFamily (editable taxonomy), CareerEnrichment (one-to-one custom family,
specialization, locale titles, friendly explanation, nullable entry-level suitability,
reserved nullable RIASEC profile, review/provenance metadata), and SkillAlias
(normalized alias, relation kind, review/provenance metadata). No salaries, demand,
licensing claims, or occupation RIASEC scores are seeded.

Legacy numeric weights remain compatibility estimates, labeled through provenance.
Separate nullable source relationship fields prevent them being mistaken for ESCO
facts. Source refreshes update source snapshots only on existing rows. Explicit
curation updates custom metadata, never industry, scores, or saved user records.

CSV matching uses a supplied URI first; without URIs it uses unique Unicode/case/
whitespace-normalized exported labels with exact normalized equality only. Ambiguous
matches, URI conflicts, and duplicates are rejected for review, never fuzzy-merged.
Unknown source URIs are not inferred from names or newly downloaded taxonomies.

Detailed provenance, audit results, import policy, and operational instructions are
documented with the completed implementation in phase2a-knowledge-base.md.
