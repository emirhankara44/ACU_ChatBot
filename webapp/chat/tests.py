import json
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse

from .models import ChatMessage, ChatSession, ScrapedPage
from .views import (
    NO_DATA_MESSAGE,
    OUT_OF_SCOPE_MESSAGE,
    build_language_instruction,
    build_scraped_context,
    build_session_title,
    detect_question_language,
    find_relevant_scraped_pages,
    is_acibadem_related,
)

# Type hints for ChatSession
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from django.db.models import Model


class ChatViewTests(TestCase):
    def test_detect_question_language_handles_turkish_characters(self):
        self.assertEqual(detect_question_language("Acibadem'de bölüm var mı?"), "tr")
        self.assertEqual(detect_question_language("What programs are available?"), "en")

    def test_detect_question_language_handles_turkish_without_special_characters(self):
        self.assertEqual(detect_question_language("hangi bolumler var"), "tr")
        self.assertEqual(detect_question_language("merhaba nasilsin"), "tr")

    def test_build_session_title_is_localized(self):
        self.assertEqual(build_session_title("Merhaba dünya", "tr"), "Hakkında: Merhaba dünya")
        self.assertEqual(build_session_title("Hello world", "en"), "About: Hello world")

    def test_build_language_instruction_is_localized(self):
        self.assertIn("tamamen Turkce", build_language_instruction("tr"))
        self.assertIn("fully in English", build_language_instruction("en"))

    def test_is_acibadem_related_identifies_supported_scope(self):
        self.assertTrue(is_acibadem_related("Acibadem Universitesi nerede?"))
        self.assertTrue(is_acibadem_related("hangi bolumler var"))
        self.assertFalse(is_acibadem_related("Bugun hava nasil?"))

    def test_find_relevant_scraped_pages_prefers_matching_category(self):
        ScrapedPage.objects.create(
            url="https://www.acibadem.edu.tr/ucretler",
            category="tuition",
            title="2026-2027 Ucret ve Burs Bilgileri",
            headings="Ucretler\nBurslar",
            content="Lisans ucretleri ve burs oranlari burada yer alir.",
        )
        ScrapedPage.objects.create(
            url="https://www.acibadem.edu.tr/haberler",
            category="news",
            title="Duyurular",
            headings="Haberler",
            content="Universite haberleri burada yer alir.",
        )

        pages = find_relevant_scraped_pages("Acibadem ucretleri ne kadar?")

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0].category, "tuition")

    def test_build_scraped_context_returns_empty_when_no_match_exists(self):
        ScrapedPage.objects.create(
            url="https://www.acibadem.edu.tr/haberler",
            category="news",
            title="Duyurular",
            headings="Haberler",
            content="Universite haberleri burada yer alir.",
        )

        self.assertEqual(build_scraped_context("Acibadem ucretleri ne kadar?"), "")

    def test_sessions_post_reuses_existing_empty_session(self):
        session: ChatSession = ChatSession.objects.create(title="")

        response = self.client.post(reverse("chat-sessions"))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["created"])
        self.assertEqual(payload["session"]["id"], session.pk)

    @patch("chat.views.requests.post")
    def test_chat_post_creates_message_and_returns_session_title(self, mock_post):
        ScrapedPage.objects.create(
            url="https://www.acibadem.edu.tr/programlar",
            category="departments",
            title="Programs",
            headings="Programs",
            content="Acibadem University offers medicine, engineering, and health sciences programs.",
        )
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
        request_payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(request_payload["messages"][1]["role"], "system")
        self.assertIn("fully in English", request_payload["messages"][1]["content"])
        self.assertIn("Use only the following scraped Acibadem University pages", request_payload["messages"][2]["content"])

    @patch("chat.views.requests.post")
    def test_chat_post_sends_turkish_language_instruction(self, mock_post):
        ScrapedPage.objects.create(
            url="https://www.acibadem.edu.tr/bolumler",
            category="departments",
            title="Bolumler",
            headings="Bolumler",
            content="Tip, eczacilik ve muhendislik bolumleri bulunur.",
        )
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"message": {"content": "Merhaba"}}
        mock_post.return_value = mock_response

        response = self.client.post(
            reverse("chat-api"),
            data=json.dumps({"question": "hangi bolumler var"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        request_payload = mock_post.call_args.kwargs["json"]
        self.assertIn("tamamen Turkce", request_payload["messages"][1]["content"])
        self.assertTrue(response.json()["session_title"].startswith("Hakkında: "))

    @patch("chat.views.requests.post")
    def test_chat_post_returns_no_data_message_without_scraped_pages(self, mock_post):
        response = self.client.post(
            reverse("chat-api"),
            data=json.dumps({"question": "Acibadem ucretleri ne kadar?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["response"], NO_DATA_MESSAGE["tr"])
        self.assertFalse(mock_post.called)

    @patch("chat.views.requests.post")
    def test_chat_post_refuses_out_of_scope_turkish_question(self, mock_post):
        response = self.client.post(
            reverse("chat-api"),
            data=json.dumps({"question": "Bugün hava nasıl?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["response"], OUT_OF_SCOPE_MESSAGE["tr"])
        self.assertFalse(mock_post.called)

    @patch("chat.views.requests.post")
    def test_chat_post_refuses_out_of_scope_english_question(self, mock_post):
        response = self.client.post(
            reverse("chat-api"),
            data=json.dumps({"question": "What is the capital of France?"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["response"], OUT_OF_SCOPE_MESSAGE["en"])
        self.assertFalse(mock_post.called)

    def test_chat_requires_question(self):
        response = self.client.post(
            reverse("chat-api"),
            data=json.dumps({}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Missing 'question' parameter")
