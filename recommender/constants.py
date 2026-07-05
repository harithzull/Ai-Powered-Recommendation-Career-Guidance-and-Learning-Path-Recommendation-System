# RIASEC types that best describe each industry.
# Used to derive a career's interest profile from the user's RIASEC answers.
INDUSTRY_RIASEC: dict[str, list[str]] = {
    "Data & AI":          ["I", "C"],
    "Technology":         ["I", "R"],
    "Healthcare":         ["S", "I"],
    "Education":          ["S"],
    "Creative & Design":  ["A"],
    "Business":           ["E", "C"],
    "Finance":            ["C", "E"],
    "Marketing":          ["E", "A"],
    "Engineering":        ["R", "I"],
    "Law":                ["E", "C"],
    "Communication":      ["A", "S"],
    "Research":           ["I"],
}

# Max raw RIASEC score per type (2 questions × max rating 5)
RIASEC_MAX_PER_TYPE = 10

# Industries aligned with each field of study (used in background_score)
FIELD_TO_INDUSTRIES: dict[str, list[str]] = {
    "Computing/IT":     ["Technology", "Data & AI"],
    "Business":         ["Business", "Finance", "Marketing"],
    "Engineering":      ["Engineering", "Technology"],
    "Health Sciences":  ["Healthcare", "Research"],
    "Arts & Design":    ["Creative & Design", "Communication"],
    "Social Sciences":  ["Education", "Communication", "Law"],
    "Science/Research": ["Research", "Data & AI", "Healthcare"],
    "Other":            [],
}

# Multiplier reflecting how much prior experience boosts background alignment
EXPERIENCE_WEIGHT: dict[str, float] = {
    "No experience": 0.7,
    "Internship":    0.8,
    "1-2 years":     0.9,
    "3+ years":      1.0,
}
