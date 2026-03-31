import json
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from .models import ChatMessage, ChatSession
from .views import build_session_title, detect_question_language


class ChatViewTests(TestCase):
    def test_detect_question_language_handles_turkish_characters(self):
        self.assertEqual(detect_question_language("Acibadem'de bölüm var mı?"), "tr")
        self.assertEqual(detect_question_language("What programs are available?"), "en")

    def test_build_session_title_is_localized(self):
        self.assertEqual(build_session_title("Merhaba dünya", "tr"), "Hakkında: Merhaba dünya")
        self.assertEqual(build_session_title("Hello world", "en"), "About: Hello world")

    def test_sessions_post_reuses_existing_empty_session(self):
        session = ChatSession.objects.create(title="")

        response = self.client.post(reverse("chat-sessions"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["created"])
        self.assertEqual(payload["session"]["id"], session.id)

    @patch("chat.views.requests.post")
    def test_chat_post_creates_message_and_returns_session_title(self, mock_post):
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"message": {"content": "Hello from model"}}
        mock_post.return_value = mock_response

        response = self.client.post(
            reverse("chat-api"),
            data=json.dumps({"question": "What is Acibadem University?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["response"], "Hello from model")
        self.assertTrue(payload["session_title"].startswith("About: "))
        self.assertEqual(ChatSession.objects.count(), 1)
        self.assertEqual(ChatMessage.objects.count(), 1)

    def test_chat_requires_question(self):
        response = self.client.post(
            reverse("chat-api"),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Missing 'question' parameter")
