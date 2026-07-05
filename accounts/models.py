from django.contrib.auth.models import User
from django.db import models


FIELD_OF_STUDY_CHOICES = [
    ("Computing/IT",     "Computing / IT"),
    ("Business",         "Business"),
    ("Engineering",      "Engineering"),
    ("Health Sciences",  "Health Sciences"),
    ("Arts & Design",    "Arts & Design"),
    ("Social Sciences",  "Social Sciences"),
    ("Science/Research", "Science / Research"),
    ("Other",            "Other"),
]

EXPERIENCE_CHOICES = [
    ("No experience", "No experience"),
    ("Internship",    "Internship / part-time"),
    ("1-2 years",     "1–2 years"),
    ("3+ years",      "3+ years"),
]


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    field_of_study   = models.CharField(max_length=30, choices=FIELD_OF_STUDY_CHOICES, blank=True)
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_CHOICES,     blank=True)

    def is_complete(self) -> bool:
        return bool(self.field_of_study and self.experience_level)

    def __str__(self):
        return f"Profile({self.user.username})"
