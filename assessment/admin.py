from django.contrib import admin
from .models import (RIASECQuestion, UserResponse, RIASECAnswer, SkillRating,
                     QuestionBank, InterestItem, AssessmentSession, SessionItem)


@admin.register(RIASECQuestion)
class RIASECQuestionAdmin(admin.ModelAdmin):
    list_display = ("order", "riasec_type", "text")
    list_filter = ("riasec_type",)
    ordering = ("order",)
    readonly_fields = ("order", "riasec_type", "text")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class RIASECAnswerInline(admin.TabularInline):
    model = RIASECAnswer
    extra = 0
    readonly_fields = ("question", "rating")
    can_delete = False
    max_num = 0


class SkillRatingInline(admin.TabularInline):
    model = SkillRating
    extra = 0
    readonly_fields = ("skill_name", "rating")


@admin.register(UserResponse)
class UserResponseAdmin(admin.ModelAdmin):
    list_display = ("user", "submitted_at")
    inlines = [RIASECAnswerInline, SkillRatingInline]
    readonly_fields = ("user", "submitted_at", "completed_at", "active_session", "free_text_skills")

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(QuestionBank)
class QuestionBankAdmin(admin.ModelAdmin):
    list_display = ("version", "status", "created_at")
    readonly_fields = ("status", "created_at")

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (("version",) if obj and obj.status != "draft" else ())

    def has_delete_permission(self, request, obj=None):
        return bool(obj and obj.status == "draft" and not obj.sessions.exists())


@admin.register(InterestItem)
class InterestItemAdmin(admin.ModelAdmin):
    list_display = ("code", "bank", "dimension", "facet", "status", "quick_core")
    list_filter = ("bank", "dimension", "status", "quick_core")
    search_fields = ("code", "text", "facet")

    def has_delete_permission(self, request, obj=None):
        return bool(obj and obj.bank.status == "draft" and not obj.session_items.exists())


@admin.register(AssessmentSession)
class AssessmentSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "mode", "status", "bank", "completed_at")
    list_filter = ("mode", "status", "bank")
    readonly_fields = tuple(field.name for field in AssessmentSession._meta.fields)
    actions = None

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
