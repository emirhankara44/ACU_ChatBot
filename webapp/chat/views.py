import json
import os
import requests
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import ChatMessage, ChatSession

def index(request):
    sessions = ChatSession.objects.all()[:30]
    return render(request, "chat/index.html", {"sessions": sessions})

@csrf_exempt
@require_http_methods(["GET", "POST"])
def sessions(request):
    if request.method == "POST":
        s = ChatSession.objects.create(title="New chat")
        return JsonResponse({"session": {"id": s.id, "title": s.title, "updated_at": s.updated_at.isoformat()}}, status=201)

    items = ChatSession.objects.all()[:30]
    return JsonResponse(
        {
            "sessions": [
                {"id": s.id, "title": s.title or "New chat", "updated_at": s.updated_at.isoformat()}
                for s in items
            ]
        }
    )

@require_http_methods(["GET"])
def session_messages(request, session_id: int):
    try:
        session = ChatSession.objects.get(pk=session_id)
    except ChatSession.DoesNotExist:
        return JsonResponse({"error": "Session not found"}, status=404)

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
            session = ChatSession.objects.create(title="New chat")
        
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
                session.title = (question.strip()[:60] + ("…" if len(question.strip()) > 60 else ""))
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