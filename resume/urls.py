from django.urls import path
from . import analysis_views, views

app_name = 'resume'
urlpatterns = [
    path('', views.index, name='index'), path('upload/', views.upload, name='upload'),
    path('<uuid:pk>/', views.detail, name='detail'),
    path('<uuid:pk>/delete-confirmation/', views.confirm_delete, name='confirm_delete'),
    path('<uuid:pk>/delete/', views.delete, name='delete'),
    path('<uuid:pk>/download/', views.download, name='download'),
    path('<uuid:pk>/analysis/', analysis_views.overview, name='analysis_index'),
    path('<uuid:pk>/analysis/run/', analysis_views.run, name='analysis_run'),
    path('<uuid:pk>/analysis/<uuid:analysis_id>/', analysis_views.overview, name='analysis_detail'),
    path('<uuid:pk>/analysis/<uuid:analysis_id>/<uuid:suggestion_id>/correct/',
         analysis_views.correct, name='analysis_correct'),
    path('<uuid:pk>/analysis/<uuid:analysis_id>/<uuid:suggestion_id>/review/',
         analysis_views.save_review, name='analysis_review'),
]
