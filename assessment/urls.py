from django.urls import path
from . import views
from . import v2_views

app_name = "assessment"

urlpatterns = [
    path("start/", v2_views.start, name="start"),
    path("history/", v2_views.history, name="history"),
    path("sessions/<uuid:session_id>/", v2_views.session_page, name="session"),
    path("sessions/<uuid:session_id>/review/", v2_views.review, name="review"),
    path("sessions/<uuid:session_id>/result/", v2_views.result, name="result"),
    path("sessions/<uuid:session_id>/abandon/", v2_views.abandon, name="abandon"),
    path("retake/", views.retake, name="retake"),
    path("background/",       views.background,    name="background"),
    path("interests/",        views.interests,     name="interests"),
    path("interests/next/",   views.next_question, name="next_question"),
    path("skills/",           views.skills,        name="skills"),
    path("skill-search/",     views.skill_search,  name="skill_search"),
    # Backward-compat: /assessment/ and reverse("assessment:quiz") → interests
    path("",              views.quiz,         name="quiz"),
]
