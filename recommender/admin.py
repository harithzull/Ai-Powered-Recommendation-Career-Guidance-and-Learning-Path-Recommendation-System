from django.contrib import admin
from .models import Career, Skill, CareerSkill, CachedRecommendation


class CatalogCacheInvalidationMixin:
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        CachedRecommendation.objects.all().delete()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        CachedRecommendation.objects.all().delete()

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        CachedRecommendation.objects.all().delete()

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        CachedRecommendation.objects.all().delete()


class CareerSkillInline(admin.TabularInline):
    model = CareerSkill
    extra = 0
    fields = ("skill", "skill_type", "required_level", "importance", "is_core")
    autocomplete_fields = ["skill"]


@admin.register(Career)
class CareerAdmin(CatalogCacheInvalidationMixin, admin.ModelAdmin):
    list_display = ("title", "industry", "work_environment")
    list_filter = ("industry", "work_environment")
    search_fields = ("title", "industry")
    inlines = [CareerSkillInline]


@admin.register(Skill)
class SkillAdmin(CatalogCacheInvalidationMixin, admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(CareerSkill)
class CareerSkillAdmin(CatalogCacheInvalidationMixin, admin.ModelAdmin):
    list_display = ("career", "skill", "skill_type", "required_level", "importance", "is_core")
    list_filter = ("skill_type", "required_level", "is_core")
    search_fields = ("career__title", "skill__name")
    autocomplete_fields = ["career", "skill"]
