from django.contrib import admin
from .models import RoadmapProgress


@admin.register(RoadmapProgress)
class RoadmapProgressAdmin(admin.ModelAdmin):
    list_display = ("user", "career", "step_index")
    list_filter = ("career",)
    search_fields = ("user__username", "career__title")
