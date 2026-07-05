import json
from pathlib import Path

import numpy as np
from django.core.management.base import BaseCommand

from recommender.embeddings import get_model
from recommender.models import Skill

OUTPUT_DIR = Path(__file__).resolve().parents[3] / "data"
VECTORS_PATH = OUTPUT_DIR / "skill_vectors.npy"
NAMES_PATH = OUTPUT_DIR / "skill_names.json"
BATCH_SIZE = 64


class Command(BaseCommand):
    help = "Encode all Skill records with all-MiniLM-L6-v2 and save vectors to disk."

    def handle(self, *args, **options):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        skills = list(Skill.objects.all().order_by("id"))
        total = len(skills)
        self.stdout.write(f"Encoding {total} skills with all-MiniLM-L6-v2 ...")

        model = get_model()

        texts = []
        names = []
        for skill in skills:
            desc = skill.description.strip()
            text = f"{skill.name}. {desc}" if desc else skill.name
            texts.append(text)
            names.append(skill.name)

        all_vectors = []
        for start in range(0, total, BATCH_SIZE):
            batch = texts[start : start + BATCH_SIZE]
            vecs = model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
            all_vectors.append(vecs)
            done = min(start + BATCH_SIZE, total)
            if done % 200 == 0 or done == total:
                self.stdout.write(f"  {done}/{total} skills encoded")

        matrix = np.vstack(all_vectors)
        np.save(VECTORS_PATH, matrix)
        with open(NAMES_PATH, "w", encoding="utf-8") as f:
            json.dump(names, f, ensure_ascii=False)

        self.stdout.write(self.style.SUCCESS(
            f"\nSaved {matrix.shape[0]} vectors (dim={matrix.shape[1]}) to:\n"
            f"  {VECTORS_PATH}\n"
            f"  {NAMES_PATH}"
        ))
