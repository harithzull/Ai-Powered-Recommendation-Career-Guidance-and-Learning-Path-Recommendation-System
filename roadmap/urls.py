from django.urls import path
from . import views

app_name = "roadmap"

urlpatterns = [
    path("<int:career_id>/", views.roadmap, name="roadmap"),
]
