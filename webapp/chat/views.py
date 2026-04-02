import json
import os
from typing import Any

import requests
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import ChatMessage, ChatSession, ScrapedPage

DEFAULT_MODEL = os.environ.get("LLM_MODEL", "llama3.2:3b")
DEFAULT_LLM_URL = "http://localhost:11434"
SYSTEM_PROMPT = (
    "You are ACU AI Chatbot for Acibadem University. "
    "Answer only questions that are about Acibadem University. "
    "If the question is outside that scope, refuse it briefly. "
    "For Acibadem University questions, answer carefully and do not invent facts. "
    "If you are unsure or the information is not available, clearly say that you do not know. "
    "Always reply fully in the same language as the user's question. "
    "Do not mix Turkish and English in the same answer unless the user explicitly asks for translation "
    "or bilingual output."
)

TURKISH_HINT_WORDS = {
    "hangi",
    "neden",
    "nasıl",
    "nedir",
    "nerede",
    "ne",
    "kim",
    "kaç",
    "var",
    "yok",
    "mı",
    "mi",
    "mu",
    "mü",
    "için",
    "bölüm",
    "bölümler",
    "üniversite",
    "fakülte",
    "ders",
    "okul",
    "merhaba",
}

ACIBADEM_HINT_WORDS = {
    "acibadem",
    "acıbadem",
    "acu",
    "universite",
    "üniversite",
    "universitesi",
    "üniversitesi",
    "kampus",
    "kampüs",
    "fakulte",
    "fakülte",
    "bolum",
    "bölüm",
    "bolumler",
    "bölümler",
    "program",
    "programlar",
    "lisans",
    "yuksek",
    "yüksek",
    "master",
    "doktora",
    "akademik",
    "egitim",
    "eğitim",
    "kayit",
    "kayıt",
    "ucret",
    "ücret",
    "burs",
    "yurt",
    "erasmus",
    "ogrenci",
    "öğrenci",
    "admission",
    "tuition",
    "scholarship",
    "faculty",
    "department",
    "departments",
    "programs",
    "campus",
}

OUT_OF_SCOPE_MESSAGE = {
    "tr": "Üzgünüm, ben sadece Acıbadem Üniversitesi hakkındaki soruları cevaplıyorum.",
    "en": "Sorry, I can only answer questions about Acibadem University.",
}

NO_DATA_MESSAGE = {
    "tr": (
        "Bu konuda elimde yeterli Acıbadem Üniversitesi verisi yok. "
        "Yalnızca veri tabanımdaki scrape edilmiş sayfalara dayanarak cevap verebiliyorum."
    ),
    "en": (
        "I do not have enough Acibadem University data for this question yet. "
        "I can answer only from the scraped pages in my database."
    ),
}

QUESTION_STOP_WORDS = {
    "acibadem",
    "acıbadem",
    "universite",
    "üniversite",
    "universitesi",
    "üniversitesi",
    "nedir",
    "nasil",
    "nasıl",
    "hangi",
    "var",
    "mı",
    "mi",
    "mu",
    "mü",
    "what",
    "where",
    "when",
    "how",
    "is",
    "are",
    "the",
    "of",
    "for",
    "about",
}

CATEGORY_HINTS = {
    "departments": {"bolum", "bölüm", "bolumler", "bölümler", "department", "departments", "program", "programs"},
    "tuition": {"ucret", "ücret", "fee", "fees", "tuition", "burs", "scholarship"},
    "admissions": {"aday", "admission", "apply", "application", "basvuru", "başvuru", "kayit", "kayıt"},
    "academics": {"akademik", "academic", "ders", "course", "curriculum", "egitim", "eğitim"},
    "faculty": {"kadro", "staff", "faculty", "academician", "hoca"},
    "news": {"duyuru", "announcement", "news", "haber", "event", "etkinlik"},
    "campus": {"kampus", "kampüs", "campus", "ulasim", "ulaşım", "adres", "address", "nerde", "nerede", "where", "location"},
}


def normalize_words(text: str) -> set[str]:
    return {
        word.strip(".,!?;:()[]{}\"'").lower()
        for word in text.split()
        if word.strip(".,!?;:()[]{}\"'")
    }


def detect_question_language(question: str) -> str:
    text = " ".join(question.split()).strip()
    if not text:
        return "en"

    if any(character in "çğıöşüÇĞİÖŞÜ" for character in text):
        return "tr"

    normalized_words = normalize_words(text)
    if normalized_words & TURKISH_HINT_WORDS:
        return "tr"
    return "en"


def is_acibadem_related(question: str) -> bool:
    text = " ".join(question.split()).strip().lower()
    if not text:
        return False

    normalized_words = normalize_words(text)
    if "acibadem" in text or "acıbadem" in text or "acu" in normalized_words:
        return True

    return bool(normalized_words & ACIBADEM_HINT_WORDS)


def build_language_instruction(lang: str) -> str:
    if lang == "tr":
        return (
            "Kullanici Turkce yazdi. Cevabini tamamen Turkce ver. "
            "Ingilizce kelime karistirma. Gerekirse bilmedigini Turkce soyle."
        )
    return (
        "The user wrote in English. Reply fully in English. "
        "Do not mix Turkish into the answer unless the user asks for it."
    )


def build_session_title(question: str, lang: str) -> str:
    text = " ".join(question.split()).strip()
    if not text:
        return "Untitled chat" if lang == "en" else "Başlıksız sohbet"
    if len(text) > 70:
        text = text[:70].rstrip() + "..."
    return f"About: {text}" if lang == "en" else f"Hakkında: {text}"


def get_llm_url() -> str:
    return os.environ.get("LLM_URL") or os.environ.get("OLLAMA_URL") or DEFAULT_LLM_URL


def parse_request_data(request: HttpRequest) -> dict[str, Any]:
    try:
        body = request.body.decode("utf-8") if isinstance(request.body, bytes) else request.body
        payload = json.loads(body or "{}")
    except (UnicodeDecodeError, TypeError, json.JSONDecodeError):
        payload = {}

    if isinstance(payload, dict):
        return payload
    return {}


def get_or_create_session(session_id: Any) -> Any:
    if session_id:
        try:
            return ChatSession.objects.get(pk=session_id)
        except ChatSession.DoesNotExist:
            pass
    return ChatSession.objects.create(title="")


def extract_answer(response: Any) -> str:
    payload = response.json()
    message = payload.get("message", {})
    if isinstance(message, dict):
        content = message.get("content", "")
        return content if isinstance(content, str) else str(content)
    return ""


def serialize_session(session: Any) -> dict[str, Any]:
    return {
        "id": session.id,
        "title": session.title or "Untitled chat",
        "updated_at": session.updated_at.isoformat(),
    }


def serialize_message(message: Any) -> dict[str, Any]:
    return {
        "id": message.id,
        "created_at": message.created_at.isoformat(),
        "question": message.question,
        "answer": message.answer,
        "error": message.error,
    }


def index(request: HttpRequest) -> HttpResponse:
    session_items: Any = (
        ChatSession.objects.annotate(message_count=Count("messages"))
        .filter(message_count__gt=0)[:30]
    )
    return render(request, "chat/index.html", {"sessions": session_items})


def build_page_text(page: ScrapedPage, max_content_chars: int = 2500) -> str:
    content = page.content[:max_content_chars].strip()
    headings = page.headings.strip()
    parts = [
        f"URL: {page.url}",
        f"Category: {page.category or 'general'}",
        f"Title: {page.title or '(untitled)'}",
    ]
    if headings:
        parts.append(f"Headings:\n{headings}")
    if content:
        parts.append(f"Content:\n{content}")
    return "\n".join(parts)


def score_page_for_question(page: ScrapedPage, question_terms: set[str]) -> int:
    searchable_title = normalize_words(page.title)
    searchable_headings = normalize_words(page.headings)
    searchable_url = normalize_words(page.url.replace("/", " ").replace("-", " "))
    searchable_content = normalize_words(page.content[:6000])

    score = 0
    score += len(question_terms & searchable_title) * 8
    score += len(question_terms & searchable_headings) * 6
    score += len(question_terms & searchable_url) * 5
    score += len(question_terms & searchable_content) * 2

    for category, hints in CATEGORY_HINTS.items():
        if question_terms & hints and page.category == category:
            score += 10
    return score


def get_fallback_scraped_pages(limit: int = 5) -> list[ScrapedPage]:
    preferred_urls = [
        "https://www.acibadem.edu.tr/",
        "https://www.acibadem.edu.tr/universite",
        "https://www.acibadem.edu.tr/akademik",
        "https://www.acibadem.edu.tr/aday/ogrenci",
        "https://www.acibadem.edu.tr/programlar",
    ]
    pages_by_url = {page.url: page for page in ScrapedPage.objects.filter(url__in=preferred_urls)}
    selected = [pages_by_url[url] for url in preferred_urls if url in pages_by_url]
    if len(selected) >= limit:
        return selected[:limit]

    extra_pages = list(
        ScrapedPage.objects.exclude(url__in=preferred_urls).order_by("-fetched_at")[: max(0, limit - len(selected))]
    )
    return selected + extra_pages


def find_relevant_scraped_pages(question: str, limit: int = 5) -> list[ScrapedPage]:
    pages = list(ScrapedPage.objects.all()[:300])
    if not pages:
        return []

    question_terms = normalize_words(question) - QUESTION_STOP_WORDS
    if not question_terms:
        return pages[:limit]

    scored_pages = [
        (score_page_for_question(page, question_terms), page.fetched_at, page)
        for page in pages
    ]
    scored_pages.sort(key=lambda item: (item[0], item[1]), reverse=True)
    relevant = [page for score, _, page in scored_pages if score > 0]
    if relevant:
        return relevant[:limit]
    return get_fallback_scraped_pages(limit=limit)


def build_scraped_context(question: str, limit: int = 5) -> str:
    pages = find_relevant_scraped_pages(question, limit=limit)
    if not pages:
        return ""

    context_blocks = [build_page_text(page) for page in pages]
    joined_context = "\n\n---\n\n".join(context_blocks)
    return (
        "Use only the following scraped Acibadem University pages as your source.\n"
        "Do not rely on general knowledge or make up missing details.\n"
        "If the answer is not clearly supported by these pages, say you do not know.\n\n"
        f"{joined_context}\n\n"
        f"Question: {question}"
    )

@csrf_exempt
@require_http_methods(["GET", "POST"])
def sessions(request: HttpRequest) -> JsonResponse:
    if request.method == "POST":
        empty_session: Any = (
            ChatSession.objects.annotate(message_count=Count("messages"))
            .filter(message_count=0)
            .first()
        )
        if empty_session is not None:
            return JsonResponse({"created": False, "session": serialize_session(empty_session)})

        session = ChatSession.objects.create(title="")
        return JsonResponse({"created": True, "session": serialize_session(session)}, status=201)

    session_items: Any = (
        ChatSession.objects.annotate(message_count=Count("messages"))
        .filter(message_count__gt=0)[:30]
    )
    return JsonResponse({"sessions": [serialize_session(session) for session in session_items]})


@csrf_exempt
@require_http_methods(["GET", "DELETE"])
def session_messages(request: HttpRequest, session_id: int) -> JsonResponse:
    try:
        session: Any = ChatSession.objects.get(pk=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Session not found"}, status=404)

    if request.method == "DELETE":
        session.delete()
        return JsonResponse({"ok": True})

    return JsonResponse(
        {
            "session": serialize_session(session),
            "messages": [serialize_message(message) for message in session.messages.all()],
        }
    )


@csrf_exempt
@require_http_methods(["GET", "POST"])
def chat(request: HttpRequest) -> JsonResponse:
    if request.method == "GET":
        return JsonResponse({"message": 'Chat API is ready. Send a POST request with {"question": "..."}.'})

    data = parse_request_data(request)
    question_value = data.get("question") or request.POST.get("question") or ""
    question = str(question_value).strip()
    session_id = data.get("session_id") or request.POST.get("session_id")

    if not question:
        return JsonResponse({"error": "Missing 'question' parameter"}, status=400)

    session: Any = get_or_create_session(session_id)
    language = detect_question_language(question)

    if not session.title:
        session.title = build_session_title(question, lang=language)
        session.save(update_fields=["title"])

    if not is_acibadem_related(question):
        refusal_message = OUT_OF_SCOPE_MESSAGE[language]
        ChatMessage.objects.create(session=session, question=question, answer=refusal_message)
        return JsonResponse(
            {
                "session_id": session.id,
                "session_title": session.title,
                "question": question,
                "response": refusal_message,
            }
        )

    user_content = build_scraped_context(question)
    if not user_content:
        no_data_message = NO_DATA_MESSAGE[language]
        ChatMessage.objects.create(session=session, question=question, answer=no_data_message)
        return JsonResponse(
            {
                "session_id": session.id,
                "session_title": session.title,
                "question": question,
                "response": no_data_message,
            }
        )

    payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": build_language_instruction(language)},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": 260,
        },
    }

    try:
        response = requests.post(f"{get_llm_url()}/api/chat", json=payload, timeout=60)
        response.raise_for_status()
        answer = extract_answer(response)

        ChatMessage.objects.create(session=session, question=question, answer=answer)
        return JsonResponse(
            {
                "session_id": session.id,
                "session_title": session.title,
                "question": question,
                "response": answer,
            }
        )
    except requests.RequestException as exc:
        ChatMessage.objects.create(session=session, question=question, error=str(exc))
        return JsonResponse({"error": f"LLM Service Unavailable: {exc}"}, status=503)
