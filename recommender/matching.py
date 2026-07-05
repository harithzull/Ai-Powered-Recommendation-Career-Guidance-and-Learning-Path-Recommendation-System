"""
Semantic skill matching between a user's skills and a career's required skills.

All career-skill vectors are precomputed; only the user's small skill list is
encoded at call time.
"""
import json
from pathlib import Path
from typing import Union

import numpy as np
from django.conf import settings
from sentence_transformers.util import cos_sim

from recommender.embeddings import get_model
from recommender.models import Career, CareerSkill

_DATA_DIR = Path(__file__).resolve().parent / ".." / "data"
_VECTORS_PATH = (_DATA_DIR / "skill_vectors.npy").resolve()
_NAMES_PATH = (_DATA_DIR / "skill_names.json").resolve()

# Loaded once per process
_skill_vectors: np.ndarray | None = None
_skill_index: dict[str, int] | None = None   # name -> row index


def _load_store() -> tuple[np.ndarray, dict[str, int]]:
    global _skill_vectors, _skill_index
    if _skill_vectors is None:
        try:
            _skill_vectors = np.load(_VECTORS_PATH)
            with open(_NAMES_PATH, encoding="utf-8") as f:
                names = json.load(f)
            _skill_index = {name: i for i, name in enumerate(names)}
        except FileNotFoundError as e:
            raise RuntimeError(
                "Skill vectors not found. Run: python manage.py build_skill_vectors"
            ) from e
    return _skill_vectors, _skill_index


def encode_user_skills(user_skill_texts: list[str]) -> np.ndarray:
    """
    Encode a user's skill list once so the vectors can be reused across
    many career comparisons without re-running the transformer each time.
    """
    vectors, _ = _load_store()
    if not user_skill_texts:
        return np.zeros((1, vectors.shape[1]), dtype=np.float32)
    return get_model().encode(user_skill_texts, convert_to_numpy=True)


def semantic_skill_match_from_vectors(
    user_vecs: np.ndarray,
    career: Union[Career, str],
) -> tuple[float, list[str]]:
    """
    Returns (coverage_score, missing_core_skills) using pre-encoded user vectors.
    Call encode_user_skills() once before the career loop, then pass the result here.
    """
    threshold: float = getattr(settings, "SIMILARITY_THRESHOLD", 0.5)

    if isinstance(career, str):
        career = Career.objects.get(title=career)

    career_skills = list(
        CareerSkill.objects.filter(career=career).select_related("skill")
    )
    if not career_skills:
        return 0.0, []

    vectors, index = _load_store()

    total_weight = 0.0
    weighted_sim_sum = 0.0
    missing_skills: list[str] = []

    for cs in career_skills:
        skill_name = cs.skill.name
        row = index.get(skill_name)
        if row is None:
            continue

        career_vec = vectors[row : row + 1]
        sims = cos_sim(career_vec, user_vecs)
        best_sim = float(sims.max())

        weight = max(cs.importance, 1)
        weighted_sim_sum += best_sim * weight
        total_weight += weight

        if cs.is_core and best_sim < threshold:
            missing_skills.append(skill_name)

    coverage_score = weighted_sim_sum / total_weight if total_weight > 0 else 0.0
    return round(coverage_score, 4), missing_skills


def semantic_skill_match(
    user_skill_texts: list[str],
    career: Union[Career, str],
) -> tuple[float, list[str]]:
    """Convenience wrapper — encodes then matches. Use semantic_skill_match_from_vectors
    directly when scoring multiple careers to avoid re-encoding each time."""
    user_vecs = encode_user_skills(user_skill_texts)
    return semantic_skill_match_from_vectors(user_vecs, career)
