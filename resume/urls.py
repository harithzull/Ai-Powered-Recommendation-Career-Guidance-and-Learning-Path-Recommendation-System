from django.urls import path
from . import views

app_name = 'resume'
urlpatterns = [
    path('', views.index, name='index'), path('upload/', views.upload, name='upload'),
    path('<uuid:pk>/', views.detail, name='detail'),
    path('<uuid:pk>/delete-confirmation/', views.confirm_delete, name='confirm_delete'),
    path('<uuid:pk>/delete/', views.delete, name='delete'),
    path('<uuid:pk>/download/', views.download, name='download'),
]
