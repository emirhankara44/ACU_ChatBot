from django.db import models

class ChatSession(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    title = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Chat {self.pk}"

class ChatMessage(models.Model):
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name="messages", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    question = models.TextField()
    answer = models.TextField(blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        q = (self.question or "").strip()
        return q[:60] + ("…" if len(q) > 60 else "")


class ScrapedPage(models.Model):
    url = models.URLField(unique=True)
    category = models.CharField(max_length=64, blank=True)
    title = models.CharField(max_length=255, blank=True)
    headings = models.TextField(blank=True)
    content = models.TextField()
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-fetched_at"]

    def __str__(self) -> str:
        return self.title or self.url
