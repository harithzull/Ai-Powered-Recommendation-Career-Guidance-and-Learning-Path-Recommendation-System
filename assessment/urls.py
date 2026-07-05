from django.urls import path
from . import views

app_name = "assessment"

urlpatterns = [
    path("background/",       views.background,    name="background"),
    path("interests/",        views.interests,     name="interests"),
    path("interests/next/",   views.next_question, name="next_question"),
    path("skills/",           views.skills,        name="skills"),
    path("skill-search/",     views.skill_search,  name="skill_search"),
    # Backward-compat: /assessment/ and reverse("assessment:quiz") → interests
    path("",              views.quiz,         name="quiz"),
]
