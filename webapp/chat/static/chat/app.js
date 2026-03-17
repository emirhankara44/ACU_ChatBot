(() => {
  const apiUrl = (window.ACU_CHAT && window.ACU_CHAT.apiUrl) || "/api/chat/";
  const sessionsUrl = (window.ACU_CHAT && window.ACU_CHAT.sessionsUrl) || "/api/sessions/";
  const sessionUrlTemplate =
    (window.ACU_CHAT && window.ACU_CHAT.sessionUrlTemplate) || "/api/sessions/{id}/";

  const form = document.getElementById("chatForm");
  const textarea = document.getElementById("question");
  const sendBtn = document.getElementById("sendBtn");
  const messagesEl = document.getElementById("chatMessages");
  const statusHint = document.getElementById("statusHint");
  const newChatBtn = document.getElementById("newChatBtn");
  const sessionListEl = document.getElementById("sessionList");

  let currentSessionId = null;

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
      const btn = document.createElement("button");
      btn.className = "history__item";
      btn.type = "button";
      btn.setAttribute("data-session-id", s.id);

      const q = document.createElement("div");
      q.className = "history__q";
      q.textContent = escapeText(s.title || "New chat");

      const meta = document.createElement("div");
      meta.className = "history__meta";
      meta.textContent = formatWhen(s.updated_at);

      btn.appendChild(q);
      btn.appendChild(meta);
      btn.addEventListener("click", () => loadSession(String(s.id)));

      sessionListEl.appendChild(btn);
    });
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

  function setBusy(busy) {
    sendBtn.disabled = busy;
    textarea.disabled = busy;
    if (busy) {
      statusHint.textContent = "Thinking…";
    } else {
      statusHint.textContent =
        "Running locally. If the LLM container is still starting, answers may take a moment.";
    }
  }

  async function sendQuestion(question) {
    addMessage("user", question);
    const placeholder = addMessage("bot", "…");
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
        currentSessionId = data.session_id;
      }
      placeholder.textContent = data.response || "(No response)";
      await refreshSessions();
    } catch (err) {
      placeholder.parentElement.classList.remove("msg--bot");
      placeholder.parentElement.classList.add("msg--error");
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

  function resetChatUi() {
    messagesEl.innerHTML = "";
    currentSessionId = null;
    addMessage(
      "bot",
      "Hi! I can help answer questions about Acıbadem University. What would you like to know?"
    );
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
      resetChatUi();
      await refreshSessions();
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

      if ((data.messages || []).length === 0) {
        addMessage("bot", "This chat is empty.");
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
  document.querySelectorAll(".history__item").forEach((btn) => {
    btn.addEventListener("click", () => loadSession(btn.getAttribute("data-session-id")));
  });

  autosize();
  scrollToBottom();
  refreshSessions();
})();
