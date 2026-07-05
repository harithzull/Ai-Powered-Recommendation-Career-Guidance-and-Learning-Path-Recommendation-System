from django.contrib import admin
from .models import RIASECQuestion, UserResponse, RIASECAnswer, SkillRating


@admin.register(RIASECQuestion)
class RIASECQuestionAdmin(admin.ModelAdmin):
    list_display = ("order", "riasec_type", "text")
    list_filter = ("riasec_type",)
    ordering = ("order",)


class RIASECAnswerInline(admin.TabularInline):
    model = RIASECAnswer
    extra = 0
    readonly_fields = ("question", "rating")


class SkillRatingInline(admin.TabularInline):
    model = SkillRating
    extra = 0
    readonly_fields = ("skill_name", "rating")


@admin.register(UserResponse)
class UserResponseAdmin(admin.ModelAdmin):
    list_display = ("user", "submitted_at")
    inlines = [RIASECAnswerInline, SkillRatingInline]
    readonly_fields = ("submitted_at",)
