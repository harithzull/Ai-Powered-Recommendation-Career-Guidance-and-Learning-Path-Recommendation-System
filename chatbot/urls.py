from django.urls import path
from . import views

app_name = "chatbot"

urlpatterns = [
    path("",        views.chat_page,    name="chat"),
    path("message/", views.send_message, name="send_message"),
    path("clear/",   views.clear_chat,   name="clear"),
]
