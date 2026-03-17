import json
import os
import requests
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt
def chat(request):
    if request.method == "POST":
        question = None
        try:
            # Try parsing JSON body first
            data = json.loads(request.body)
            question = data.get("question")
        except json.JSONDecodeError:
            # Fallback to form data (request.POST) if JSON fails
            question = request.POST.get("question")
        
        if not question:
            return JsonResponse({"error": "Missing 'question' parameter"}, status=400)

        # Allow configuration via environment variable, default to localhost
        ollama_url = os.environ.get("OLLAMA_URL", "http://localhost:11434")
        
        payload = {
            "model": "llama3.2:1b",
            "messages": [
                {"role": "system", "content": "You are an assistant that answers questions about Acıbadem University."},
                {"role": "user", "content": question}
            ],
            "stream": False
        }
        
        try:
            response = requests.post(f"{ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            return JsonResponse({
                "question": question,
                "response": response.json().get("message", {}).get("content", "")
            })
        except requests.RequestException as e:
            return JsonResponse({"error": f"LLM Service Unavailable: {str(e)}"}, status=503)
    
    return JsonResponse({"message": "Sohbet API'si hazır. Lütfen POST isteği gönderin."})