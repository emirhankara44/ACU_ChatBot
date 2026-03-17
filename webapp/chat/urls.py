from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="chat-index"),
    path("api/chat/", views.chat, name="chat-api"),
    path("api/sessions/", views.sessions, name="chat-sessions"),
    path("api/sessions/<int:session_id>/", views.session_messages, name="chat-session-messages"),
]
