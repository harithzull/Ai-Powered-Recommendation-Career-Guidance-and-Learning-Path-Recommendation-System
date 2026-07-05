from django.contrib import admin
from .models import Career, Skill, CareerSkill


class CareerSkillInline(admin.TabularInline):
    model = CareerSkill
    extra = 0
    fields = ("skill", "skill_type", "required_level", "importance", "is_core")
    autocomplete_fields = ["skill"]


@admin.register(Career)
class CareerAdmin(admin.ModelAdmin):
    list_display = ("title", "industry", "work_environment")
    list_filter = ("industry", "work_environment")
    search_fields = ("title", "industry")
    inlines = [CareerSkillInline]


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(CareerSkill)
class CareerSkillAdmin(admin.ModelAdmin):
    list_display = ("career", "skill", "skill_type", "required_level", "importance", "is_core")
    list_filter = ("skill_type", "required_level", "is_core")
    search_fields = ("career__title", "skill__name")
    autocomplete_fields = ["career", "skill"]
