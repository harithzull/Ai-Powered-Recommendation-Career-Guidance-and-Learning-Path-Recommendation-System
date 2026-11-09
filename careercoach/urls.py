from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("assessment/", include("assessment.urls")),
    path("recommendations/", include("recommender.urls")),
    path("roadmap/", include("roadmap.urls")),
    path("chat/",    include("chatbot.urls")),
    path("", RedirectView.as_view(url="/dashboard/", permanent=False)),
]
