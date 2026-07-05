import csv
from pathlib import Path
from django.core.management.base import BaseCommand
from django.db import transaction
from recommender.models import Career, Skill, CareerSkill

DATA_DIR = Path(__file__).resolve().parents[3] / "data"

CAREERS_CSV = DATA_DIR / "careers_clean (1).csv"
SKILLS_CSV = DATA_DIR / "skills_clean (1).csv"
CAREER_SKILLS_CSV = DATA_DIR / "career_skills_clean (1).csv"


class Command(BaseCommand):
    help = "Import career, skill, and career-skill mapping data from CSV files."

    def handle(self, *args, **options):
        self.stdout.write("Clearing existing data...")
        CareerSkill.objects.all().delete()
        Career.objects.all().delete()
        Skill.objects.all().delete()

        skills_imported = self._import_skills()
        careers_imported = self._import_careers()
        mappings_imported, unmatched = self._import_career_skills()

        self.stdout.write(self.style.SUCCESS(
            f"\n=== Import complete ===\n"
            f"  Careers  : {careers_imported}\n"
            f"  Skills   : {skills_imported}\n"
            f"  Mappings : {mappings_imported}\n"
        ))

        if unmatched:
            self.stdout.write(self.style.WARNING(
                f"  WARNING: {len(unmatched)} career_skills rows had unresolved references:"
            ))
            for row in unmatched[:20]:
                self.stdout.write(f"    career='{row['career']}' skill='{row['skill']}'")
            if len(unmatched) > 20:
                self.stdout.write(f"    ... and {len(unmatched) - 20} more")
        else:
            self.stdout.write(self.style.SUCCESS("  Unmatched: 0"))

    @transaction.atomic
    def _import_skills(self):
        self.stdout.write("Importing skills...")
        skills = []
        with open(SKILLS_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                skills.append(Skill(
                    name=row["name"].strip(),
                    description=row["description"].strip(),
                    category=row["category"].strip(),
                ))
        Skill.objects.bulk_create(skills, ignore_conflicts=True)
        count = Skill.objects.count()
        self.stdout.write(f"  {count} skills loaded.")
        return count

    @transaction.atomic
    def _import_careers(self):
        self.stdout.write("Importing careers...")
        careers = []
        with open(CAREERS_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                careers.append(Career(
                    title=row["title"].strip(),
                    industry=row["industry"].strip(),
                    summary=row["summary"].strip(),
                    description=row["description"].strip(),
                    work_environment=row["work_environment"].strip(),
                ))
        Career.objects.bulk_create(careers, ignore_conflicts=True)
        count = Career.objects.count()
        self.stdout.write(f"  {count} careers loaded.")
        return count

    @transaction.atomic
    def _import_career_skills(self):
        self.stdout.write("Importing career-skill mappings...")

        career_map = {c.title: c for c in Career.objects.all()}
        skill_map = {s.name: s for s in Skill.objects.all()}

        mappings = []
        unmatched = []

        with open(CAREER_SKILLS_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                career_title = row["career"].strip()
                skill_name = row["skill"].strip()

                career = career_map.get(career_title)
                skill = skill_map.get(skill_name)

                if career is None or skill is None:
                    unmatched.append(row)
                    continue

                mappings.append(CareerSkill(
                    career=career,
                    skill=skill,
                    skill_type=row["skill_type"].strip(),
                    required_level=row["required_level"].strip(),
                    importance=int(row["importance"]) if row["importance"].strip() else 0,
                    is_core=row["is_core"].strip().lower() == "true",
                ))

        CareerSkill.objects.bulk_create(mappings, ignore_conflicts=True)
        count = CareerSkill.objects.count()
        self.stdout.write(f"  {count} mappings loaded.")
        return count, unmatched
