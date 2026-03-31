(() => {
  const apiUrl = (window.ACU_CHAT && window.ACU_CHAT.apiUrl) || "/api/chat/";
  const sessionsUrl = (window.ACU_CHAT && window.ACU_CHAT.sessionsUrl) || "/api/sessions/";
  const sessionUrlTemplate =
    (window.ACU_CHAT && window.ACU_CHAT.sessionUrlTemplate) || "/api/sessions/{id}/";

  const form = document.getElementById("chatForm");
  const textarea = document.getElementById("question");
  const sendBtn = document.getElementById("sendBtn");
  const messagesEl = document.getElementById("chatMessages");
  const newChatBtn = document.getElementById("newChatBtn");
  const sessionListEl = document.getElementById("sessionList");
  const INTRO_TEXT =
    "Hi! I can help answer questions about Acibadem University. What would you like to know?";

  let currentSessionId = null;

  // Required UI elements. If they're missing, don't attempt to wire listeners.
  if (!form || !textarea || !sendBtn || !messagesEl) {
    return;
  }

  function escapeText(s) {
    return (s || "").toString();
  }

  function formatWhen(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "";
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
      d.getHours()
    )}:${pad(d.getMinutes())}`;
  }

  function buildSessionTitleFromQuestion(question) {
    const text = (question || "").toString().replace(/\s+/g, " ").trim();
    if (!text) return "Untitled chat";
    const shortText = text.length > 70 ? `${text.slice(0, 70).trimEnd()}...` : text;
    return `About: ${shortText}`;
  }

  function renderSessions(items) {
    if (!sessionListEl) return;
    sessionListEl.innerHTML = "";
    if (!items || items.length === 0) {
      const empty = document.createElement("div");
      empty.className = "history__empty";
      empty.textContent = "No chats yet.";
      sessionListEl.appendChild(empty);
      return;
    }

    items.forEach((s) => {
      sessionListEl.appendChild(buildSessionItem(s));
    });
  }

  function buildSessionItem(s) {
    const item = document.createElement("div");
    item.className = "history__item";
    item.setAttribute("data-session-id", s.id);

    const openBtn = document.createElement("button");
    openBtn.className = "history__open";
    openBtn.type = "button";
    openBtn.setAttribute("data-session-id", s.id);

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "history__delete";
    deleteBtn.type = "button";
    deleteBtn.setAttribute("data-session-id", s.id);
    deleteBtn.setAttribute("aria-label", "Delete chat");
    deleteBtn.title = "Delete chat";
    deleteBtn.textContent = "🗑";

    const q = document.createElement("div");
    q.className = "history__q";
    q.textContent = escapeText(s.title || "Untitled chat");

    const meta = document.createElement("div");
    meta.className = "history__meta";
    meta.textContent = formatWhen(s.updated_at);

    openBtn.appendChild(q);
    openBtn.appendChild(meta);
    openBtn.addEventListener("click", () => loadSession(String(s.id)));
    deleteBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSession(String(s.id));
    });

    item.appendChild(openBtn);
    item.appendChild(deleteBtn);
    return item;
  }

  function upsertSessionToTop(session) {
    if (!sessionListEl || !session || !session.id) return;
    const existing = sessionListEl.querySelector(`[data-session-id="${session.id}"]`);
    if (existing) existing.remove();
    const emptyEl = sessionListEl.querySelector(".history__empty");
    if (emptyEl) emptyEl.remove();
    sessionListEl.prepend(buildSessionItem(session));
  }

  async function deleteSession(sessionId) {
    if (!sessionId) return;
    const ok = await openDeleteConfirmModal();
    if (!ok) return;

    try {
      const url = sessionUrlTemplate.replace("{id}", String(sessionId));
      const resp = await fetch(url, { method: "DELETE" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);

      if (currentSessionId === String(sessionId)) {
        resetChatUi();
      }
      await refreshSessions();
    } catch (e) {
      addMessage(
        "error",
        "Could not delete this chat.\n\n" + (e && e.message ? `Details: ${e.message}` : "")
      );
    }
  }

  async function refreshSessions() {
    if (!sessionListEl) return;
    try {
      const resp = await fetch(sessionsUrl, { method: "GET" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);
      renderSessions(data.sessions || []);
    } catch (_) {
      // keep existing server-rendered list if refresh fails
    }
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      const chat = document.getElementById("chat");
      if (chat) chat.scrollTop = chat.scrollHeight;
    });
  }

  function addMessage(kind, text) {
    const wrap = document.createElement("div");
    wrap.className = `msg msg--${kind}`;
    const bubble = document.createElement("div");
    bubble.className = "msg__bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollToBottom();
    return bubble;
  }

  function addTypingIndicator() {
    const wrap = document.createElement("div");
    wrap.className = "msg msg--bot";

    const bubble = document.createElement("div");
    bubble.className = "msg__bubble msg__bubble--typing";
    bubble.setAttribute("aria-label", "Assistant is typing");

    for (let i = 0; i < 3; i += 1) {
      const dot = document.createElement("span");
      dot.className = "typing-dot";
      bubble.appendChild(dot);
    }

    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    scrollToBottom();
    return bubble;
  }

  function ensureDeleteModal() {
    let overlay = document.getElementById("deleteConfirmOverlay");
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "deleteConfirmOverlay";
    overlay.className = "confirm-overlay";
    overlay.innerHTML = `
      <div class="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirmTitle">
        <h3 id="confirmTitle" class="confirm-title">Are you sure you want to delete this chat?</h3>
        <p class="confirm-subtitle">This action cannot be undone.</p>
        <div class="confirm-actions">
          <button type="button" class="confirm-btn confirm-btn--ghost" id="confirmCancelBtn">Cancel</button>
          <button type="button" class="confirm-btn confirm-btn--danger" id="confirmDeleteBtn">Delete</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    return overlay;
  }

  function openDeleteConfirmModal() {
    const overlay = ensureDeleteModal();
    overlay.classList.add("is-open");
    return new Promise((resolve) => {
      const cancelBtn = document.getElementById("confirmCancelBtn");
      const deleteBtn = document.getElementById("confirmDeleteBtn");

      if (!cancelBtn || !deleteBtn) {
        overlay.classList.remove("is-open");
        resolve(false);
        return;
      }

      const cleanup = (result) => {
        overlay.classList.remove("is-open");
        cancelBtn.removeEventListener("click", onCancel);
        deleteBtn.removeEventListener("click", onDelete);
        overlay.removeEventListener("click", onBackdrop);
        document.removeEventListener("keydown", onKeydown);
        resolve(result);
      };
      const onCancel = () => cleanup(false);
      const onDelete = () => cleanup(true);
      const onBackdrop = (e) => {
        if (e.target === overlay) cleanup(false);
      };
      const onKeydown = (e) => {
        if (e.key === "Escape") cleanup(false);
      };

      cancelBtn.addEventListener("click", onCancel);
      deleteBtn.addEventListener("click", onDelete);
      overlay.addEventListener("click", onBackdrop);
      document.addEventListener("keydown", onKeydown);
      deleteBtn.focus();
    });
  }

  function setBusy(busy) {
    sendBtn.disabled = busy;
    textarea.disabled = busy;
  }

  async function sendQuestion(question) {
    addMessage("user", question);
    const placeholder = addTypingIndicator();
    setBusy(true);

    try {
      const resp = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, session_id: currentSessionId }),
      });

      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.error || `Request failed (${resp.status})`);
      }

      if (data.session_id) {
        currentSessionId = String(data.session_id);
      }
      placeholder.classList.remove("msg__bubble--typing");
      placeholder.textContent = data.response || "(No response)";
      upsertSessionToTop({
        id: currentSessionId,
        title: data.session_title || buildSessionTitleFromQuestion(question),
        updated_at: new Date().toISOString(),
      });
      refreshSessions();
    } catch (err) {
      placeholder.classList.remove("msg__bubble--typing");
      const wrapEl = placeholder.parentElement;
      if (wrapEl) {
        wrapEl.classList.remove("msg--bot");
        wrapEl.classList.add("msg--error");
      }
      placeholder.textContent =
        "Sorry — the LLM service is unavailable right now. Please try again in a moment.\n\n" +
        (err && err.message ? `Details: ${err.message}` : "");
    } finally {
      setBusy(false);
    }
  }

  function autosize() {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 180) + "px";
  }

  textarea.addEventListener("input", autosize);
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      form.requestSubmit();
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = (textarea.value || "").trim();
    if (!q) return;
    textarea.value = "";
    autosize();
    await sendQuestion(q);
  });

  function resetChatUi(options = {}) {
    const { preserveSession = false } = options;
    messagesEl.innerHTML = "";
    if (!preserveSession) {
      currentSessionId = null;
    }
    addMessage("bot", INTRO_TEXT);
    textarea.value = "";
    autosize();
    textarea.focus();
  }

  async function createNewSession() {
    setBusy(true);
    try {
      const resp = await fetch(sessionsUrl, { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);
      currentSessionId = data.session && data.session.id ? String(data.session.id) : null;
      resetChatUi({ preserveSession: true });
    } catch (e) {
      resetChatUi();
      addMessage(
        "error",
        "Could not create a new chat.\n\n" + (e && e.message ? `Details: ${e.message}` : "")
      );
    } finally {
      setBusy(false);
    }
  }

  if (newChatBtn) {
    newChatBtn.addEventListener("click", createNewSession);
  }

  async function loadSession(sessionId) {
    if (!sessionId) return;
    setBusy(true);
    try {
      const url = sessionUrlTemplate.replace("{id}", String(sessionId));
      const resp = await fetch(url, { method: "GET" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) throw new Error(data.error || `Request failed (${resp.status})`);

      currentSessionId = sessionId;
      messagesEl.innerHTML = "";

      (data.messages || []).forEach((m) => {
        if (m.question) addMessage("user", m.question);
        if (m.answer) addMessage("bot", m.answer);
        if (m.error) addMessage("error", m.error);
      });
      if (!data.messages || data.messages.length === 0) {
        addMessage("bot", INTRO_TEXT);
      }

    } catch (e) {
      messagesEl.innerHTML = "";
      addMessage(
        "error",
        "Could not load this chat session.\n\n" + (e && e.message ? `Details: ${e.message}` : "")
      );
    } finally {
      setBusy(false);
    }
  }

  // keep server-rendered listeners working if JS refresh is disabled
  document.querySelectorAll(".history__open").forEach((btn) => {
    btn.addEventListener("click", () => loadSession(btn.getAttribute("data-session-id")));
  });
  document.querySelectorAll(".history__delete").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      deleteSession(btn.getAttribute("data-session-id"));
    });
  });

  autosize();
  resetChatUi();
  refreshSessions();
})();
