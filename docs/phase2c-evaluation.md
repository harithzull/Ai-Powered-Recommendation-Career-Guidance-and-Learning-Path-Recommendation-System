# Offline evaluation

Run from the repository root, including on Windows:

```powershell
.venv\Scripts\python.exe -B scripts/evaluate_recommendations.py --output .cache/phase2c-comparison.json
```

The script forces test settings and SQLite `:memory:`, migrates only that database,
uses synthetic accounts/careers/relations, blocks socket connections and injects
four orthonormal skill vectors into the **actual legacy matching pipeline**.
It downloads no models, reads no `.env`, uses no real API keys and never writes
student or source data. V2 semantic proposals are disabled in this comparison;
threshold behavior is separately tested using deterministic vectors.

The [legacy baseline](evaluation/phase2c-legacy-baseline.json) was captured before
changing the scoring dispatcher. The runner asserts its actual legacy outputs
still match that baseline. Do not regenerate the baseline just to hide a regression.
The [full comparison](evaluation/phase2c-comparison.json) records rankings,
per-component contributions/effective weights, method/evidence availability,
structured explanations, missing data and potential anomalies. CI executes the
same command and uploads the JSON per Python version.

| Synthetic profile | Legacy first choice/points | V2 first choice/points |
| --- | --- | --- |
| Analytical, Python/SQL | Software / 89.7 | Software / 88.8 |
| Creative, Writing | Design / 70.1 | Design / 80.0 |
| Flat interests, no skills/context | Data / 34.4 | Data / 50.0 |
| Analytical, Python plus duplicate alias | Software / 78.2 | Software / 68.8 |

All three candidate positions happen to remain unchanged for these four profiles;
the report records rank deltas of zero rather than implying an improvement.
Scores change because of interest origin, identity-only coverage, equal relation
weighting and education-only context. With no skills/context, only the neutral
interest component remains: all candidates tie at 50. Data comes first only
because of the deterministic title tie-break.

All 12 v2 recommendations have complete explanation structures. Interest evidence
is an industry proxy for all 12; none has a real occupation profile. Skills and
education evidence are available for 9/12 each. Flat/missing reports have no
usable skills/context. There are no verified proficiency gaps in these fixtures.
These are coverage/completeness observations, **not prediction quality metrics**.

Known anomalies/limits: sparse reports undercount identity coverage; equal weights
ignore genuine but currently undocumented requirement differences; education can
favor familiar industries; self-reports cannot verify possession; flat profiles
cannot meaningfully distinguish occupations; semantic threshold behavior on real
phrasing is unevaluated. Numeric score changes are not calibrated improvements.

For future validation, collect consented student relevance/clarity feedback and
career-center expert judgments, document representative cohorts and split
development/evaluation sets. Review occupation profiles and exact aliases with
traceable evidence. Evaluate ranked relevance (for example NDCG/precision at k),
coverage, explanation usefulness and subgroup differences; report sample size,
uncertainty and disagreements. Tune weights only on development data and evaluate
held-out results before changing the default. Do not interpret employment outcomes
as causal effects of recommendations without an appropriate study.
