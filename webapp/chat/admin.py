from django.contrib import admin
from .models import ChatMessage, ChatSession

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "created_at", "updated_at")
    search_fields = ("title",)
    readonly_fields = ("created_at", "updated_at")

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "session", "question", "has_answer", "has_error")
    list_filter = ("created_at", "session")
    search_fields = ("question", "answer", "error", "session__title")
    readonly_fields = ("created_at",)

    @admin.display(boolean=True)
    def has_answer(self, obj: ChatMessage) -> bool:
        return bool(obj.answer)

    @admin.display(boolean=True)
    def has_error(self, obj: ChatMessage) -> bool:
        return bool(obj.error)
