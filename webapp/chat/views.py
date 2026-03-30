import json
import os
import requests
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import ChatMessage, ChatSession

def build_session_title(question: str) -> str:
    text = " ".join((question or "").split()).strip()
    if not text:
        return "Untitled chat"
    if len(text) > 70:
        text = text[:70].rstrip() + "..."
    return f"About: {text}"

def index(request):
    sessions = (
        ChatSession.objects.annotate(message_count=Count("messages"))
        .filter(message_count__gt=0)[:30]
    )
    return render(request, "chat/index.html", {"sessions": sessions})

@csrf_exempt
@require_http_methods(["GET", "POST"])
def sessions(request):
    if request.method == "POST":
        empty_session = (
            ChatSession.objects.annotate(message_count=Count("messages"))
            .filter(message_count=0)
            .first()
        )
        if empty_session is not None:
            return JsonResponse(
                {
                    "created": False,
                    "session": {
                        "id": empty_session.id,
                        "title": empty_session.title,
                        "updated_at": empty_session.updated_at.isoformat(),
                    },
                },
                status=200,
            )

        s = ChatSession.objects.create(title="")
        return JsonResponse(
            {
                "created": True,
                "session": {"id": s.id, "title": s.title, "updated_at": s.updated_at.isoformat()},
            },
            status=201,
        )

    items = (
        ChatSession.objects.annotate(message_count=Count("messages"))
        .filter(message_count__gt=0)[:30]
    )
    return JsonResponse(
        {
            "sessions": [
                {"id": s.id, "title": s.title or "Untitled chat", "updated_at": s.updated_at.isoformat()}
                for s in items
            ]
        }
    )

@csrf_exempt
@require_http_methods(["GET", "DELETE"])
def session_messages(request, session_id: int):
    try:
        session = ChatSession.objects.get(pk=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Session not found"}, status=404)

    if request.method == "DELETE":
        session.delete()
        return JsonResponse({"ok": True})

    msgs = session.messages.all()
    return JsonResponse(
        {
            "session": {"id": session.id, "title": session.title, "updated_at": session.updated_at.isoformat()},
            "messages": [
                {
                    "id": m.id,
                    "created_at": m.created_at.isoformat(),
                    "question": m.question,
                    "answer": m.answer,
                    "error": m.error,
                }
                for m in msgs
            ],
        }
    )

@csrf_exempt
def chat(request):
    if request.method == "POST":
        question = None
        session_id = None
        try:
            # Try parsing JSON body first
            data = json.loads(request.body)
            question = data.get("question")
            session_id = data.get("session_id")
        except json.JSONDecodeError:
            # Fallback to form data (request.POST) if JSON fails
            question = request.POST.get("question")
            session_id = request.POST.get("session_id")
        
        if not question:
            return JsonResponse({"error": "Missing 'question' parameter"}, status=400)

        llm_url = os.environ.get("LLM_URL") or os.environ.get("OLLAMA_URL") or "http://localhost:11434"

        session = None
        if session_id:
            try:
                session = ChatSession.objects.get(pk=session_id)
            except ChatSession.DoesNotExist:
                session = None
        if session is None:
            session = ChatSession.objects.create(title="")
        
        payload = {
            "model": "llama3.2:1b",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are ACU AI Chatbot, an assistant for Acıbadem University (ACU). "
                        "Answer in English. Be concise and helpful. "
                        "If you are not sure, say what you do and do not know."
                    ),
                },
                {"role": "user", "content": question}
            ],
            "stream": False
        }
        
        try:
            response = requests.post(f"{llm_url}/api/chat", json=payload, timeout=60)
            response.raise_for_status()
            answer = response.json().get("message", {}).get("content", "")
            if not session.title:
                session.title = build_session_title(question)
                session.save(update_fields=["title"])
            ChatMessage.objects.create(session=session, question=question, answer=answer)
            return JsonResponse({
                "session_id": session.id,
                "question": question,
                "response": answer
            })
        except requests.RequestException as e:
            ChatMessage.objects.create(session=session, question=question, error=str(e))
            return JsonResponse({"error": f"LLM Service Unavailable: {str(e)}"}, status=503)
    
    return JsonResponse({"message": "Chat API is ready. Send a POST request with {\"question\": \"...\"}."})