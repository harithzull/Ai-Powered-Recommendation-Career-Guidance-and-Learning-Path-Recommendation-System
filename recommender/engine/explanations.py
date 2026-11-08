def explain(components, interests, skills):
    supporting, uncertain, unavailable = [], [], []
    if interests['available']:
        supporting.append(f"Interest alignment uses {interests['method']} across {', '.join(interests['dimensions'])}.")
        if interests['method'] == 'industry_fallback':
            uncertain.append('Industry mapping is a broad proxy, not occupation-specific RIASEC evidence.')
    else:
        unavailable.append('Usable interest alignment evidence')
    if skills['matched_skills']:
        supporting.append('Reported canonical skills: ' + ', '.join(r['name'] for r in skills['matched_skills']) + '.')
    if not skills['available']:
        unavailable.append('Skill coverage evidence (no reports or no catalog relations)')
    if components['background']['available']:
        supporting.append('Education industry proxy: ' + ('aligned.' if components['background']['education_aligned'] else 'different field.'))
    else:
        unavailable.append('Comparable education industry context')
    unavailable.append('Verified comparable skill proficiency and career-specific experience requirements')
    if skills['potential_matches']:
        uncertain.append('Semantic proposals require confirmation and do not contribute to the ranking score.')
    if skills['reports_truncated']:
        uncertain.append('The report exceeded the 30 unique-skill budget; only the deterministic first 30 were considered.')
    uncertain.append('Unreported related skills are opportunities to explore, not proven deficiencies.')
    return {'summary': ' '.join(supporting) or 'Insufficient comparable evidence; a neutral ranking score is shown.',
            'supporting_evidence': supporting, 'uncertain_suggestions': uncertain, 'unavailable_evidence': unavailable,
            'score_meaning': 'Ranking points from available evidence; not a probability of career success.'}
