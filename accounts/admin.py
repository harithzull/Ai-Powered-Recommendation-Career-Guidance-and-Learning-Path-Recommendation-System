from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "field_of_study", "experience_level")
    list_filter  = ("field_of_study", "experience_level")
    search_fields = ("user__username",)
