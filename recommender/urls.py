from django.urls import path
from . import views

app_name = "recommender"

urlpatterns = [
    path('history/', views.history, name='history'),
    path("", views.results, name="results"),
]
