from django.contrib import admin
from recommender.models import RecommendationRun


@admin.register(RecommendationRun)
class RecommendationRunAdmin(admin.ModelAdmin):
    list_display = ('user', 'algorithm_version', 'created_at')
    readonly_fields = ('user', 'algorithm_version', 'input_signature', 'configuration', 'results_json', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
from .models import Career, Skill, CareerSkill, CachedRecommendation, CareerFamily, CareerEnrichment, SkillAlias


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
    list_display = ("title", "industry", "source_taxonomy", "quality_status")
    list_filter = ("industry", "source_taxonomy", "quality_status")
    search_fields = ("title", "source_title", "esco_uri")
    readonly_fields = ("source_metadata",)
    inlines = [CareerSkillInline]


@admin.register(Skill)
class SkillAdmin(CatalogCacheInvalidationMixin, admin.ModelAdmin):
    list_display = ("name", "category", "source_taxonomy", "quality_status")
    list_filter = ("category", "source_taxonomy", "quality_status")
    search_fields = ("name", "source_name", "esco_uri")
    readonly_fields = ("source_metadata",)


@admin.register(CareerSkill)
class CareerSkillAdmin(CatalogCacheInvalidationMixin, admin.ModelAdmin):
    list_display = ("career", "skill", "skill_type", "required_level", "importance", "is_core")
    list_filter = ("skill_type", "required_level", "is_core")
    search_fields = ("career__title", "skill__name")
    autocomplete_fields = ["career", "skill"]
    readonly_fields = ("source_metadata",)


@admin.register(CareerFamily)
class CareerFamilyAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CareerEnrichment)
class CareerEnrichmentAdmin(admin.ModelAdmin):
    list_display = ("career", "family", "review_status")
    list_filter = ("family", "review_status")
    search_fields = ("career__title", "specialization")
    autocomplete_fields = ("career", "family")


@admin.register(SkillAlias)
class SkillAliasAdmin(CatalogCacheInvalidationMixin, admin.ModelAdmin):
    list_display = ("name", "skill", "kind", "review_status")
    list_filter = ("kind", "review_status")
    search_fields = ("name", "skill__name")
    autocomplete_fields = ("skill",)
