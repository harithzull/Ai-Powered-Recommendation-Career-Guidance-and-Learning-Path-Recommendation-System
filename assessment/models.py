from django.db import models
from django.contrib.auth.models import User
import uuid
from django.core.exceptions import ValidationError
from django.db.models import Q

RIASEC_TYPES = [
    ("R", "Realistic"),
    ("I", "Investigative"),
    ("A", "Artistic"),
    ("S", "Social"),
    ("E", "Enterprising"),
    ("C", "Conventional"),
]

RATING_CHOICES = [(i, str(i)) for i in range(1, 6)]

FIXED_SKILLS = [
    "Programming",
    "Data Analysis",
    "Statistics",
    "Writing",
    "Communication",
    "Design",
    "Project Management",
    "Problem Solving",
    "Research",
    "Teamwork",
    "Marketing",
    "Financial Literacy",
]


class RIASECQuestion(models.Model):
    text = models.TextField()
    riasec_type = models.CharField(max_length=1, choices=RIASEC_TYPES)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return f"[{self.riasec_type}] {self.text[:60]}"


class UserResponse(models.Model):
    active_session = models.ForeignKey("AssessmentSession", null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name="+")
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="assessment_response")
    submitted_at = models.DateTimeField(auto_now=True)
    free_text_skills = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Response for {self.user.username} ({self.submitted_at:%Y-%m-%d})"


class RIASECAnswer(models.Model):
    response = models.ForeignKey(UserResponse, on_delete=models.CASCADE, related_name="riasec_answers")
    question = models.ForeignKey(RIASECQuestion, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)

    class Meta:
        unique_together = ("response", "question")

    def __str__(self):
        return f"{self.response.user.username} — Q{self.question.id}: {self.rating}"


class SkillRating(models.Model):
    response = models.ForeignKey(UserResponse, on_delete=models.CASCADE, related_name="skill_ratings")
    skill_name = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField(choices=RATING_CHOICES)

    class Meta:
        unique_together = ("response", "skill_name")

    def __str__(self):
        return f"{self.response.user.username} — {self.skill_name}: {self.rating}"


class QuestionBank(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        RETIRED = "retired", "Retired"

    version = models.CharField(max_length=60, unique=True)
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["status"], condition=Q(status="active"), name="one_active_interest_bank")]

    def clean(self):
        if self.pk:
            previous = QuestionBank.objects.get(pk=self.pk)
            if previous.status != self.Status.DRAFT and self.status == self.Status.DRAFT:
                raise ValidationError("Published banks cannot be reopened as drafts; create a new version.")
            if previous.version != self.version and (previous.status != self.Status.DRAFT or self.sessions.exists()):
                raise ValidationError("Publish a new bank version instead of renaming a published or used bank.")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.version


class InterestItem(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DRAFT = "draft", "Draft"
        RETIRED = "retired", "Retired"

    bank = models.ForeignKey(QuestionBank, on_delete=models.PROTECT, related_name="items")
    code = models.CharField(max_length=20)
    dimension = models.CharField(max_length=1, choices=RIASEC_TYPES)
    facet = models.CharField(max_length=100)
    purpose = models.TextField()
    text = models.TextField()
    status = models.CharField(max_length=10, choices=Status, default=Status.DRAFT)
    quick_core = models.BooleanField(default=False)

    class Meta:
        ordering = ["code"]
        constraints = [models.UniqueConstraint(fields=["bank", "code"], name="interest_item_bank_code")]

    def clean(self):
        if self.pk:
            previous = InterestItem.objects.select_related("bank").get(pk=self.pk)
            fields = ["bank_id", "code", "dimension", "facet", "purpose", "text", "quick_core"]
            if (previous.bank.status != QuestionBank.Status.DRAFT or previous.session_items.exists()) and any(
                getattr(previous, field) != getattr(self, field) for field in fields
            ):
                raise ValidationError("Published/used item content is frozen. Create a new bank version.")
        elif self.bank_id and self.bank.status != QuestionBank.Status.DRAFT:
            raise ValidationError("Add new questions to a draft bank, then publish a new version.")

    def __str__(self):
        return f"{self.bank.version}: {self.code}"

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class AssessmentSession(models.Model):
    class Mode(models.TextChoices):
        QUICK = "quick", "Quick"
        DETAILED = "detailed", "Detailed"
        LEGACY = "legacy", "Legacy"

    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        ABANDONED = "abandoned", "Abandoned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="interest_sessions")
    bank = models.ForeignKey(QuestionBank, on_delete=models.PROTECT, null=True, blank=True, related_name="sessions")
    mode = models.CharField(max_length=10, choices=Mode)
    status = models.CharField(max_length=15, choices=Status, default=Status.IN_PROGRESS)
    selection_seed = models.CharField(max_length=32, blank=True)
    current_position = models.PositiveSmallIntegerField(default=0)
    revision = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    scoring_version = models.CharField(max_length=60)
    result = models.JSONField(default=dict, blank=True)
    context_snapshot = models.JSONField(default=dict, blank=True)
    legacy_response = models.OneToOneField(UserResponse, null=True, blank=True, on_delete=models.SET_NULL, related_name="legacy_history")

    class Meta:
        ordering = ["-started_at", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["user"], condition=Q(status="in_progress"), name="one_open_interest_session_per_user"),
            models.CheckConstraint(condition=(Q(mode="legacy") | Q(bank__isnull=False)), name="new_interest_session_has_bank"),
        ]

    def clean(self):
        if self.pk:
            previous = AssessmentSession.objects.filter(pk=self.pk).first()
            if previous and previous.status != self.Status.IN_PROGRESS:
                fields = [f.attname for f in self._meta.fields]
                if any(getattr(previous, name) != getattr(self, name) for name in fields):
                    raise ValidationError("Completed or abandoned assessment sessions are immutable.")

    def __str__(self):
        return f"{self.mode}: {self.status} ({self.pk})"

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class SessionItem(models.Model):
    session = models.ForeignKey(AssessmentSession, on_delete=models.CASCADE, related_name="items")
    item = models.ForeignKey(InterestItem, on_delete=models.PROTECT, related_name="session_items")
    position = models.PositiveSmallIntegerField()
    code = models.CharField(max_length=20)
    dimension = models.CharField(max_length=1, choices=RIASEC_TYPES)
    text = models.TextField()
    facet = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField(null=True, blank=True, choices=RATING_CHOICES)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(fields=["session", "item"], name="one_selected_item_per_session"),
            models.UniqueConstraint(fields=["session", "position"], name="one_item_per_session_position"),
            models.CheckConstraint(condition=Q(rating__isnull=True) | Q(rating__gte=1, rating__lte=5), name="session_interest_rating_1_to_5"),
        ]

    def clean(self):
        if self.session_id and not AssessmentSession.objects.filter(pk=self.session_id, status="in_progress").exists():
            raise ValidationError("Responses to closed sessions cannot be changed.")
        if self.pk:
            previous = SessionItem.objects.get(pk=self.pk)
            if any(getattr(previous, key) != getattr(self, key) for key in ["session_id", "item_id", "position", "code", "dimension", "text", "facet"]):
                raise ValidationError("Selected question snapshots cannot be changed.")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)
