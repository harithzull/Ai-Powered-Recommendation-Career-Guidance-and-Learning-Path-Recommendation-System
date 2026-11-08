"""Weighted evidence with missing components removed from the denominator."""
def combine(components, weights):
    denominator = sum(weights[k] for k, c in components.items() if c['available'])
    for key, component in components.items():
        effective = weights[key]/denominator if denominator and component['available'] else 0
        component['configured_weight'] = weights[key]
        component['effective_weight'] = effective
        component['contribution_points'] = 100*effective*component['score'] if effective else 0
    return sum(c['contribution_points'] for c in components.values()) if denominator else 50.0


def stable_order(rows):
    return sorted(rows, key=lambda r: (-r['_unrounded_score'], r['career'].title.casefold(), r['career_id']))
