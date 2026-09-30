(() => {
  "use strict";

  const TAG_NAME = "agent-chat-widget";
  const STORAGE_KEY = "agent-chat-widget:session";
  const PERSONA_STORAGE_KEY = "agent-chat-widget:personas";
  const LEGACY_STORAGE_KEYS = ["agent-chat-widget:v2", "agent-chat-session"];
  const STATE_VERSION = 3;
  const PERSONA_STATE_VERSION = 1;
  const MAX_MESSAGES = 40;
  const MAX_MESSAGE_CHARS = 2000;

  const COPY = {
    zh: {
      launcher: "和我的 AI 分身聊聊",
      launcherHint: "通常几秒内回复",
      aiTwin: "AI 数字分身",
      online: "已就绪",
      offline: "网络已断开",
      loadingProfile: "正在载入公开资料",
      profileUnavailable: "公开资料暂时无法载入",
      introFallback: "可以问我关于项目、技术栈和求职方向的问题。",
      placeholder: "问我点什么…",
      send: "发送",
      stop: "停止生成",
      retry: "重试",
      reset: "重置本地会话",
      minimize: "最小化聊天",
      restore: "恢复聊天",
      close: "关闭聊天",
      language: "界面语言",
      theme: "切换主题，当前：{value}",
      themes: { auto: "跟随系统", light: "浅色", dark: "深色" },
      emptyTitle: "嗨，我是 Example Candidate 的 AI 数字分身。",
      quickTitle: "可以从这些问题开始",
      conversation: "对话",
      fullDisclaimer: "我是基于 Example Candidate 已确认公开资料构建的 AI 数字分身。回答由 AI 生成，可能存在错误；重要事项请向本人确认。",
      disclaimerShort: "AI 生成 · 重要信息请向本人核实",
      stopped: "已停止生成。",
      resetDone: "本地会话已重置。",
      responseReady: "新回复已完成。",
      sources: "资料来源",
      chars: "{count}/2000",
      errors: {
        OFFLINE: "当前没有网络连接。恢复网络后可以重试。",
        RATE_LIMITED: "请求太频繁了，请稍后再试。",
        UPSTREAM_RATE_LIMITED: "当前请求较多，请稍后再试。",
        SERVICE_NOT_READY: "AI 服务尚未就绪，请稍后再试。",
        REQUEST_TOO_LARGE: "消息太长了，请缩短后再试。",
        REQUEST_INVALID: "消息格式不正确，请检查后重试。",
        STREAM_INVALID: "流式响应不完整，请重试。",
        NETWORK_ERROR: "连接失败，请检查网络后重试。",
        DEFAULT: "暂时没有成功回复，请稍后重试。",
      },
    },
    en: {
      launcher: "Chat with my AI twin",
      launcherHint: "Usually replies in seconds",
      aiTwin: "AI DIGITAL TWIN",
      online: "Ready",
      offline: "You are offline",
      loadingProfile: "Loading public profile",
      profileUnavailable: "Public profile is temporarily unavailable",
      introFallback: "Ask me about my projects, technical work, or career direction.",
      placeholder: "Ask me anything…",
      send: "Send",
      stop: "Stop generating",
      retry: "Retry",
      reset: "Reset local session",
      minimize: "Minimize chat",
      restore: "Restore chat",
      close: "Close chat",
      language: "Interface language",
      theme: "Change theme, current: {value}",
      themes: { auto: "System", light: "Light", dark: "Dark" },
      emptyTitle: "Hi, I’m the owner’s AI twin.",
      quickTitle: "Try one of these",
      conversation: "Conversation",
      fullDisclaimer: "I am an AI twin built from the owner’s approved public information. AI responses may be wrong; verify important details with him.",
      disclaimerShort: "AI-generated · Verify important details with me",
      stopped: "Generation stopped.",
      resetDone: "Local session reset.",
      responseReady: "New response complete.",
      sources: "Sources",
      chars: "{count}/2000",
      errors: {
        OFFLINE: "You appear to be offline. Reconnect and try again.",
        RATE_LIMITED: "Too many requests. Please wait and try again.",
        UPSTREAM_RATE_LIMITED: "The AI service is busy. Please try again shortly.",
        SERVICE_NOT_READY: "The AI service is not ready yet. Please try again later.",
        REQUEST_TOO_LARGE: "That message is too long. Shorten it and try again.",
        REQUEST_INVALID: "That message could not be sent. Please check it and retry.",
        STREAM_INVALID: "The streamed response was incomplete. Please retry.",
        NETWORK_ERROR: "The connection failed. Check your network and retry.",
        DEFAULT: "I couldn’t complete that reply. Please try again.",
      },
    },
    de: {
      launcher: "Mit meinem KI-Zwilling chatten",
      launcherHint: "Antwortet meist in wenigen Sekunden",
      aiTwin: "KI-ZWILLING",
      online: "Bereit",
      offline: "Du bist offline",
      loadingProfile: "Öffentliches Profil wird geladen",
      profileUnavailable: "Das öffentliche Profil ist vorübergehend nicht verfügbar",
      introFallback: "Frag mich nach Projekten, Technik oder meiner beruflichen Ausrichtung.",
      placeholder: "Frag mich etwas…",
      send: "Senden",
      stop: "Generierung stoppen",
      retry: "Erneut versuchen",
      reset: "Lokale Sitzung zurücksetzen",
      minimize: "Chat minimieren",
      restore: "Chat wiederherstellen",
      close: "Chat schließen",
      language: "Oberflächensprache",
      theme: "Farbschema wechseln, aktuell: {value}",
      themes: { auto: "System", light: "Hell", dark: "Dunkel" },
      emptyTitle: "Hi, ich bin Example Candidates KI-Zwilling.",
      quickTitle: "Starte mit einer dieser Fragen",
      conversation: "Unterhaltung",
      fullDisclaimer: "Ich bin ein KI-Zwilling auf Basis von Example Candidates bestätigten öffentlichen Informationen. KI-Antworten können falsch sein; wichtige Angaben bitte persönlich prüfen.",
      disclaimerShort: "KI-generiert · Wichtige Angaben bitte persönlich prüfen",
      stopped: "Generierung gestoppt.",
      resetDone: "Lokale Sitzung zurückgesetzt.",
      responseReady: "Neue Antwort ist vollständig.",
      sources: "Quellen",
      chars: "{count}/2000",
      errors: {
        OFFLINE: "Du bist offenbar offline. Verbinde dich erneut und versuche es noch einmal.",
        RATE_LIMITED: "Zu viele Anfragen. Bitte warte kurz und versuche es erneut.",
        UPSTREAM_RATE_LIMITED: "Der KI-Dienst ist ausgelastet. Bitte versuche es gleich erneut.",
        SERVICE_NOT_READY: "Der KI-Dienst ist noch nicht bereit. Bitte versuche es später erneut.",
        REQUEST_TOO_LARGE: "Die Nachricht ist zu lang. Bitte kürze sie.",
        REQUEST_INVALID: "Die Nachricht konnte nicht gesendet werden. Bitte prüfe sie.",
        STREAM_INVALID: "Die gestreamte Antwort war unvollständig. Bitte versuche es erneut.",
        NETWORK_ERROR: "Die Verbindung ist fehlgeschlagen. Bitte prüfe dein Netzwerk.",
        DEFAULT: "Die Antwort konnte nicht abgeschlossen werden. Bitte versuche es erneut.",
      },
    },
  };

  const FALLBACK_QUESTIONS = {
    zh: ["简单介绍一下你自己", "哪个项目最能代表你？", "你目前在寻找什么机会？"],
    en: [
      "Could you introduce yourself?",
      "Which project represents you best?",
      "What opportunities are you looking for?",
    ],
    de: [
      "Kannst du dich kurz vorstellen?",
      "Welches Projekt repräsentiert dich am besten?",
      "Nach welchen Möglichkeiten suchst du?",
    ],
  };

  const PERSONA_COPY = {
    zh: {
      pickerTitle: "选择人格",
      pickerStatus: "2 个独立会话",
      pickerHeading: "聊天",
      pickerHint: "选择一个人格，进入独立对话",
      back: "返回人格列表",
      independent: "两个会话分别保存，不会互相混入聊天记录。",
      professional: {
        name: "专业人格",
        avatar: "专",
        description: "项目、技术、工作与求职",
        greeting: "你好，我是 Example Candidate 的专业人格。",
        intro: "可以问我教育背景、技术方向、项目经历、能力边界和求职计划。",
        questions: ["哪个项目最能代表你？", "你现在主要在学什么？", "你想找什么样的工作？"],
      },
      casual: {
        name: "闲聊人格",
        avatar: "闲",
        description: "日常、爱好、性格与生活",
        greeting: "嗨，我是 Example Candidate 的闲聊人格。",
        intro: "可以聊足球、咖啡、音乐、游戏和公开的性格特点。没有确认过的私人信息我不会编。",
        questions: ["你平时有什么爱好？", "你是什么样的性格？", "你为什么喜欢咖啡？"],
      },
    },
    en: {
      pickerTitle: "Choose a persona",
      pickerStatus: "2 separate chats",
      pickerHeading: "Chats",
      pickerHint: "Choose a persona to open its own conversation",
      back: "Back to persona list",
      independent: "Each persona keeps a separate local conversation.",
      professional: {
        name: "Professional",
        avatar: "PRO",
        description: "Projects, technology, work, and career",
        greeting: "Hi, I’m the owner’s professional persona.",
        intro: "Ask about my education, technical direction, projects, capabilities, or career plans.",
        questions: ["Which project represents you best?", "What are you learning now?", "What kind of role are you looking for?"],
      },
      casual: {
        name: "Casual",
        avatar: "HI",
        description: "Daily life, interests, and personality",
        greeting: "Hi, I’m the owner’s casual persona.",
        intro: "We can chat about football, coffee, music, games, and my approved public personality traits.",
        questions: ["What do you enjoy outside work?", "How would you describe your personality?", "Why do you like coffee?"],
      },
    },
    de: {
      pickerTitle: "Persona auswählen",
      pickerStatus: "2 getrennte Chats",
      pickerHeading: "Chats",
      pickerHint: "Wähle eine Persona für eine eigene Unterhaltung",
      back: "Zurück zur Persona-Liste",
      independent: "Beide Personas speichern getrennte lokale Unterhaltungen.",
      professional: {
        name: "Beruflich",
        avatar: "PRO",
        description: "Projekte, Technik, Arbeit und Karriere",
        greeting: "Hi, ich bin Example Candidates berufliche Persona.",
        intro: "Frag mich nach Studium, Technik, Projekten, Fähigkeiten oder beruflichen Plänen.",
        questions: ["Welches Projekt repräsentiert dich am besten?", "Was lernst du gerade?", "Welche Stelle suchst du?"],
      },
      casual: {
        name: "Locker",
        avatar: "HI",
        description: "Alltag, Interessen und Persönlichkeit",
        greeting: "Hi, ich bin Example Candidates lockere Persona.",
        intro: "Wir können über Fußball, Kaffee, Musik, Spiele und bestätigte Persönlichkeitseigenschaften sprechen.",
        questions: ["Welche Hobbys hast du?", "Wie würdest du deine Persönlichkeit beschreiben?", "Warum magst du Kaffee?"],
      },
    },
  };

  class WidgetError extends Error {
    constructor(code, message = "", retryable = true) {
      super(message || code);
      this.name = "WidgetError";
      this.code = code;
      this.retryable = retryable;
    }
  }

  function normalizeLocale(value, navigatorLanguage = "en") {
    const candidate = String(value || "auto").trim().toLowerCase();
    const resolved = candidate === "auto" ? String(navigatorLanguage).toLowerCase() : candidate;
    if (resolved.startsWith("zh")) return "zh";
    if (resolved.startsWith("de")) return "de";
    return "en";
  }

  function normalizeLocalePreference(value) {
    const candidate = String(value || "auto").trim().toLowerCase();
    if (candidate === "auto") return "auto";
    return normalizeLocale(candidate);
  }

  function normalizeTheme(value) {
    const candidate = String(value || "auto").trim().toLowerCase();
    return ["auto", "light", "dark"].includes(candidate) ? candidate : "auto";
  }

  function safeText(value, limit = 12000) {
    return typeof value === "string" ? value.slice(0, limit) : "";
  }

  function sourceCitation(value) {
    if (!value || typeof value !== "object") return null;
    const id = safeText(value.source_id, 16);
    const url = safeText(value.url, 200);
    if (!/^S[1-9][0-9]*$/.test(id) || !/^\/api\/v1\/knowledge\/sources\/[a-zA-Z0-9_-]+$/.test(url)) {
      return null;
    }
    const locations = Array.isArray(value.locations)
      ? value.locations.slice(0, 4).map((part) => {
        if (!part || typeof part !== "object" || Array.isArray(part)) return {};
        return Object.fromEntries(Object.entries(part).filter(([, item]) =>
          typeof item === "string" || typeof item === "number"));
      })
      : [];
    return {
      source_id: id,
      title: safeText(value.title, 160),
      url,
      locations,
      snippet: safeText(value.snippet, 500),
    };
  }

  function randomId() {
    if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
    const bytes = new Uint8Array(16);
    globalThis.crypto?.getRandomValues?.(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  function isUuid(value) {
    return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
      String(value || ""),
    );
  }

  function migrateSession(raw, uuidFactory = randomId) {
    if (!raw || typeof raw !== "object") return null;
    const version = Number(raw.version || 1);
    const sourceMessages = Array.isArray(raw.messages) ? raw.messages : [];
    const messages = sourceMessages
      .filter((item) => item && ["user", "assistant"].includes(item.role))
      .map((item) => {
        const status = ["complete", "stopped", "error"].includes(item.status)
          ? item.status
          : item.status === "streaming" || item.status === "pending"
            ? "stopped"
            : "complete";
        return {
          id: safeText(item.id, 80) || uuidFactory(),
          role: item.role,
          content: safeText(item.content),
          status,
          sources: item.role === "assistant" && Array.isArray(item.sources)
            ? item.sources.map(sourceCitation).filter(Boolean).slice(0, 5)
            : [],
        };
      })
      .filter((item) => item.content)
      .slice(-MAX_MESSAGES);
    const legacySessionId = version === 2 ? raw.session_id : raw.sessionId || raw.session_id;
    return {
      version: STATE_VERSION,
      sessionId: isUuid(legacySessionId) ? legacySessionId : uuidFactory(),
      messages,
      locale: normalizeLocalePreference(raw.locale),
      theme: normalizeTheme(raw.theme),
    };
  }

  function createPersonaConversation(uuidFactory = randomId) {
    return { sessionId: uuidFactory(), messages: [] };
  }

  function migratePersonaSession(raw, legacySession = null, uuidFactory = randomId) {
    const source = raw && typeof raw === "object" ? raw : {};
    const conversations = {};
    for (const id of ["professional", "casual"]) {
      const value = source.conversations?.[id];
      const migrated = migrateSession(
        value && typeof value === "object"
          ? { version: STATE_VERSION, sessionId: value.sessionId, messages: value.messages }
          : id === "professional" && legacySession
            ? legacySession
            : { version: STATE_VERSION },
        uuidFactory,
      );
      conversations[id] = {
        sessionId: migrated?.sessionId || uuidFactory(),
        messages: migrated?.messages || [],
      };
    }
    return {
      version: PERSONA_STATE_VERSION,
      activePersona: ["professional", "casual"].includes(source.activePersona)
        ? source.activePersona
        : null,
      conversations,
      locale: normalizeLocalePreference(source.locale || legacySession?.locale),
      theme: normalizeTheme(source.theme || legacySession?.theme),
    };
  }

  function parseSSERecord(record) {
    let event = "message";
    const data = [];
    for (const line of record.split(/\r?\n/)) {
      if (!line || line.startsWith(":")) continue;
      const separator = line.indexOf(":");
      const field = separator === -1 ? line : line.slice(0, separator);
      let value = separator === -1 ? "" : line.slice(separator + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value || "message";
      if (field === "data") data.push(value);
    }
    if (!data.length) return null;
    return { event, data: data.join("\n") };
  }

  async function* parseSSEStream(stream) {
    if (!stream?.getReader) throw new WidgetError("STREAM_INVALID");
    const reader = stream.getReader();
    const decoder = new TextDecoder("utf-8", { fatal: false });
    let buffer = "";
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
        let boundary = buffer.search(/\r?\n\r?\n/);
        while (boundary !== -1) {
          const record = buffer.slice(0, boundary);
          const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)?.[0] || "\n\n";
          buffer = buffer.slice(boundary + separator.length);
          const parsed = parseSSERecord(record);
          if (parsed) yield parsed;
          boundary = buffer.search(/\r?\n\r?\n/);
        }
        if (done) break;
      }
      if (buffer.trim()) {
        const parsed = parseSSERecord(buffer);
        if (parsed) yield parsed;
      }
    } finally {
      reader.releaseLock();
    }
  }

  function createElement(documentRef, tag, className, text) {
    const element = documentRef.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  class ZachChatWidget extends HTMLElement {
    static get observedAttributes() {
      return ["theme", "locale", "position", "title", "layout"];
    }

    static parseSSEStream(stream) {
      return parseSSEStream(stream);
    }

    static migrateSession(value, uuidFactory) {
      return migrateSession(value, uuidFactory);
    }

    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this.messages = [];
      this.activePersona = null;
      this.personaConversations = {
        professional: createPersonaConversation(),
        casual: createPersonaConversation(),
      };
      this.profile = null;
      this.sessionId = randomId();
      this.localePreference = "auto";
      this.themePreference = "auto";
      this.view = "closed";
      this.requestState = "idle";
      this.currentRequest = null;
      this.lastFailed = null;
      this.profileController = null;
      this._connected = false;
      this._previousFocus = null;
      this._onNetworkChange = () => this.updatePresence();
      this._onSchemeChange = () => this.applyTheme();
    }

    connectedCallback() {
      if (this._connected) return;
      this._connected = true;
      this.renderShell();
      this.cacheElements();
      this.configureLayout();
      if (this.hasAttribute("start-open")) this.view = "open";
      this.loadSession();
      this.bindEvents();
      this.applyLocale();
      this.applyTheme();
      this.renderMessages();
      this.updateView();
      this.updateComposer();
      this.fetchProfile();
      this.ownerDocument.defaultView?.addEventListener("online", this._onNetworkChange);
      this.ownerDocument.defaultView?.addEventListener("offline", this._onNetworkChange);
      this.updatePresence();
    }

    disconnectedCallback() {
      this._connected = false;
      this.abortRequest("close");
      this.profileController?.abort();
      const windowRef = this.ownerDocument.defaultView;
      windowRef?.removeEventListener("online", this._onNetworkChange);
      windowRef?.removeEventListener("offline", this._onNetworkChange);
      windowRef?.matchMedia("(prefers-color-scheme: dark)").removeEventListener(
        "change",
        this._onSchemeChange,
      );
    }

    attributeChangedCallback(name, oldValue, newValue) {
      if (!this._connected || oldValue === newValue) return;
      if (name === "theme") {
        this.themePreference = normalizeTheme(newValue);
        this.applyTheme();
      } else if (name === "locale") {
        this.localePreference = normalizeLocalePreference(newValue);
        this.applyLocale();
      } else if (name === "position") {
        this.elements.widget.dataset.position = newValue === "bottom-left" ? "bottom-left" : "bottom-right";
      } else if (name === "title") {
        this.renderProfile();
      } else if (name === "layout") {
        this.configureLayout();
        this.updateView();
      }
    }

    get locale() {
      return normalizeLocale(
        this.localePreference,
        this.ownerDocument.defaultView?.navigator.language || "en",
      );
    }

    get copy() {
      return COPY[this.locale];
    }

    get busy() {
      return ["sending", "streaming"].includes(this.requestState);
    }

    get stageLayout() {
      return this.getAttribute("layout") === "stage";
    }

    get personaMode() {
      return this.hasAttribute("persona-mode");
    }

    get personaCopy() {
      return PERSONA_COPY[this.locale];
    }

    personaDefinition(id = this.activePersona) {
      return id ? this.personaCopy[id] : null;
    }

    renderShell() {
      this.shadowRoot.innerHTML = `
        <style>
          :host {
            --zach-accent: #0a84ff;
            --zach-accent-strong: #0071e3;
            --zach-wechat: #95ec69;
            --zach-wechat-strong: #79d64e;
            --zach-bg: rgb(239 245 251 / .84);
            --zach-surface: rgb(255 255 255 / .78);
            --zach-surface-strong: #ffffff;
            --zach-surface-muted: rgb(236 242 248 / .82);
            --zach-glass: rgb(250 253 255 / .66);
            --zach-glass-line: rgb(255 255 255 / .82);
            --zach-ink: #17202c;
            --zach-muted: #617083;
            --zach-line: rgb(125 145 168 / .24);
            --zach-danger: #b42318;
            --zach-focus: #006fe6;
            --zach-panel-shadow: 0 32px 80px rgb(34 57 87 / .24), 0 8px 24px rgb(34 57 87 / .14);
            position: fixed;
            right: 0;
            bottom: 0;
            z-index: 2147483000;
            color-scheme: light;
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            font-size: 16px;
            line-height: 1.45;
            text-rendering: optimizeLegibility;
          }
          *, *::before, *::after { box-sizing: border-box; }
          [hidden] { display: none !important; }
          button, textarea, select { font: inherit; }
          button, select { touch-action: manipulation; }
          button { cursor: pointer; }
          button:disabled { cursor: not-allowed; opacity: .55; }
          button:focus-visible, textarea:focus-visible, select:focus-visible, a:focus-visible {
            outline: 3px solid var(--zach-focus);
            outline-offset: 2px;
          }
          .widget {
            position: fixed;
            right: 20px;
            bottom: 20px;
            display: grid;
            justify-items: end;
            color: var(--zach-ink);
          }
          .widget[data-position="bottom-left"] { right: auto; left: 20px; justify-items: start; }
          .widget[data-theme="dark"] {
            --zach-accent: #64d2ff;
            --zach-accent-strong: #36a9ff;
            --zach-wechat: #5dba43;
            --zach-wechat-strong: #4aa534;
            --zach-bg: rgb(19 27 38 / .86);
            --zach-surface: rgb(34 44 58 / .78);
            --zach-surface-strong: #263244;
            --zach-surface-muted: rgb(44 57 73 / .82);
            --zach-glass: rgb(25 35 49 / .68);
            --zach-glass-line: rgb(255 255 255 / .18);
            --zach-ink: #f4f7fb;
            --zach-muted: #b3bdc9;
            --zach-line: rgb(208 225 242 / .16);
            --zach-danger: #ff8a80;
            --zach-focus: #64d2ff;
            --zach-panel-shadow: 0 34px 90px rgb(0 0 0 / .5), 0 8px 24px rgb(0 0 0 / .32);
            color-scheme: dark;
          }
          .panel {
            position: relative;
            isolation: isolate;
            width: min(400px, calc(100vw - 32px));
            height: min(620px, calc(100dvh - 92px));
            display: grid;
            grid-template-rows: auto minmax(0, 1fr) auto auto;
            margin-bottom: 12px;
            overflow: hidden;
            border: 1px solid var(--zach-glass-line);
            border-radius: 30px;
            background:
              linear-gradient(145deg, rgb(255 255 255 / .42), transparent 35%),
              var(--zach-glass);
            box-shadow: var(--zach-panel-shadow), inset 0 1px 0 rgb(255 255 255 / .7);
            -webkit-backdrop-filter: blur(30px) saturate(180%);
            backdrop-filter: blur(30px) saturate(180%);
            transform-origin: bottom right;
            animation: panel-in 320ms cubic-bezier(.2, .9, .2, 1);
          }
          .panel::before {
            content: "";
            position: absolute;
            z-index: -1;
            inset: 0;
            border-radius: inherit;
            background:
              radial-gradient(circle at 12% 0%, rgb(100 210 255 / .22), transparent 34%),
              radial-gradient(circle at 96% 12%, rgb(149 236 105 / .18), transparent 30%);
            pointer-events: none;
          }
          .panel::after {
            content: "";
            position: absolute;
            z-index: 5;
            inset: 1px;
            border-radius: calc(30px - 1px);
            box-shadow: inset 0 0 0 1px rgb(255 255 255 / .16);
            pointer-events: none;
          }
          .widget[data-position="bottom-left"] .panel { transform-origin: bottom left; }
          @keyframes panel-in { from { opacity: 0; transform: scale(.94); } }
          .header {
            display: grid;
            grid-template-columns: auto minmax(0, 1fr) auto;
            align-items: center;
            gap: 10px;
            min-height: 76px;
            padding: 13px 13px 12px 16px;
            border-bottom: 1px solid var(--zach-line);
            background: linear-gradient(180deg, rgb(255 255 255 / .34), rgb(255 255 255 / .08));
            -webkit-backdrop-filter: blur(18px) saturate(150%);
            backdrop-filter: blur(18px) saturate(150%);
          }
          .header-leading { display: flex; align-items: center; gap: 7px; }
          .back-button { width: 34px; min-width: 34px; font-size: 24px; }
          .avatar {
            position: relative;
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            overflow: hidden;
            border: 1px solid rgb(255 255 255 / .74);
            border-radius: 14px;
            color: white;
            background: linear-gradient(145deg, #7ee1ff 0%, #0a84ff 48%, #7065ff 100%);
            box-shadow: 0 8px 18px rgb(10 132 255 / .24), inset 0 1px 1px rgb(255 255 255 / .65);
            font-size: 13px;
            font-weight: 800;
            letter-spacing: .04em;
          }
          .widget[data-persona="professional"] .avatar,
          .widget[data-persona="professional"] .message-avatar.assistant-avatar {
            background: linear-gradient(145deg, #7ee1ff, #0a84ff 48%, #7065ff);
          }
          .widget[data-persona="casual"] .avatar,
          .widget[data-persona="casual"] .message-avatar.assistant-avatar {
            color: #173511;
            background: linear-gradient(145deg, #c7f9a7, #79d64e 52%, #44b87a);
          }
          .avatar::after, .launcher-mark::after {
            content: "";
            position: absolute;
            inset: 2px 4px 52% 4px;
            border-radius: 999px;
            background: linear-gradient(180deg, rgb(255 255 255 / .78), transparent);
            opacity: .58;
            pointer-events: none;
          }
          .identity { min-width: 0; }
          .eyebrow {
            display: block;
            margin-bottom: 1px;
            color: var(--zach-accent-strong);
            font-size: 9px;
            font-weight: 800;
            letter-spacing: .1em;
          }
          .name {
            display: block;
            overflow: hidden;
            font-size: 15px;
            font-weight: 760;
            text-overflow: ellipsis;
            white-space: nowrap;
          }
          .presence { display: flex; align-items: center; gap: 6px; color: var(--zach-muted); font-size: 11px; }
          .presence-dot { width: 7px; height: 7px; border-radius: 50%; background: #32d74b; box-shadow: 0 0 0 3px rgb(50 215 75 / .13); }
          .presence[data-offline="true"] .presence-dot { background: var(--zach-danger); }
          .controls { display: flex; align-items: center; gap: 3px; }
          .icon-button, .locale-select {
            min-width: 34px;
            height: 34px;
            border: 1px solid rgb(255 255 255 / .44);
            border-radius: 999px;
            color: var(--zach-muted);
            background: rgb(255 255 255 / .24);
            box-shadow: inset 0 1px 0 rgb(255 255 255 / .32);
            -webkit-backdrop-filter: blur(14px) saturate(140%);
            backdrop-filter: blur(14px) saturate(140%);
          }
          .icon-button:hover, .locale-select:hover { color: var(--zach-ink); background: rgb(255 255 255 / .52); transform: translateY(-1px); }
          .icon-button { display: grid; place-items: center; padding: 0; font-size: 18px; }
          .locale-select { width: 57px; padding: 0 7px; font-size: 10px; font-weight: 750; }
          .conversation {
            min-height: 0;
            overflow: hidden;
            display: grid;
          }
          .messages {
            min-height: 0;
            overflow: auto;
            padding: 20px 15px 24px;
            overscroll-behavior: contain;
            scrollbar-color: var(--zach-line) transparent;
            background:
              radial-gradient(circle at 100% 0%, rgb(100 210 255 / .11), transparent 34%),
              radial-gradient(circle at 0% 82%, rgb(149 236 105 / .1), transparent 32%);
          }
          .empty { display: grid; gap: 18px; align-content: start; }
          .intro-card {
            position: relative;
            overflow: hidden;
            padding: 20px;
            border: 1px solid var(--zach-line);
            border-radius: 22px;
            background: color-mix(in srgb, var(--zach-surface-strong) 76%, transparent);
            box-shadow: 0 10px 28px rgb(38 61 89 / .08), inset 0 1px 0 rgb(255 255 255 / .58);
          }
          .intro-card::before {
            content: "";
            position: absolute;
            inset: 0 auto 0 0;
            width: 5px;
            background: linear-gradient(180deg, var(--zach-accent), #7065ff, var(--zach-wechat-strong));
          }
          .intro-title { margin: 0 0 8px; font-size: 18px; line-height: 1.25; letter-spacing: -.02em; }
          .profile-title { margin: -2px 0 8px; color: var(--zach-accent-strong); font-size: 11px; font-weight: 700; }
          .intro-text { margin: 0; color: var(--zach-muted); font-size: 13px; }
          .contact-list { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
          .contact-link {
            color: var(--zach-accent-strong);
            font-size: 12px;
            font-weight: 700;
            text-decoration: none;
          }
          .contact-link:hover { text-decoration: underline; }
          .quick-title {
            margin: 0 0 9px;
            color: var(--zach-muted);
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: .08em;
            text-transform: uppercase;
          }
          .quick-list { display: grid; gap: 8px; }
          .quick-button {
            width: 100%;
            padding: 11px 13px;
            border: 1px solid var(--zach-line);
            border-radius: 16px;
            color: var(--zach-ink);
            background: color-mix(in srgb, var(--zach-surface-strong) 64%, transparent);
            box-shadow: inset 0 1px 0 rgb(255 255 255 / .46);
            -webkit-backdrop-filter: blur(12px) saturate(130%);
            backdrop-filter: blur(12px) saturate(130%);
            text-align: left;
            font-size: 13px;
            transition: border-color 180ms ease, transform 180ms cubic-bezier(.2, .8, .2, 1), background 180ms ease;
          }
          .quick-button:hover { border-color: color-mix(in srgb, var(--zach-accent) 56%, white); background: var(--zach-surface); transform: translateY(-2px); }
          .disclaimer-full {
            margin: 0;
            padding-top: 14px;
            border-top: 1px solid var(--zach-line);
            color: var(--zach-muted);
            font-size: 10px;
            line-height: 1.55;
          }
          .persona-picker { min-height: 100%; display: grid; align-content: start; gap: 16px; }
          .persona-picker-heading { padding: 2px 4px 0; }
          .persona-picker-title { margin: 0 0 4px; font-size: 20px; letter-spacing: -.025em; }
          .persona-picker-hint { margin: 0; color: var(--zach-muted); font-size: 12px; }
          .persona-list {
            overflow: hidden;
            border: 1px solid var(--zach-line);
            border-radius: 22px;
            background: color-mix(in srgb, var(--zach-surface-strong) 72%, transparent);
            box-shadow: 0 12px 30px rgb(38 61 89 / .09), inset 0 1px 0 rgb(255 255 255 / .58);
          }
          .persona-contact {
            width: 100%;
            display: grid;
            grid-template-columns: 48px minmax(0, 1fr) auto;
            align-items: center;
            gap: 12px;
            padding: 15px;
            border: 0;
            color: var(--zach-ink);
            background: transparent;
            text-align: left;
            transition: background 160ms ease;
          }
          .persona-contact + .persona-contact { border-top: 1px solid var(--zach-line); }
          .persona-contact:hover { background: color-mix(in srgb, var(--zach-accent) 8%, transparent); }
          .persona-avatar {
            width: 48px;
            height: 48px;
            display: grid;
            place-items: center;
            border: 1px solid rgb(255 255 255 / .66);
            border-radius: 14px;
            color: white;
            background: linear-gradient(145deg, #7ee1ff, #0a84ff 50%, #7065ff);
            box-shadow: 0 7px 16px rgb(30 75 120 / .2), inset 0 1px 0 rgb(255 255 255 / .62);
            font-size: 11px;
            font-weight: 850;
          }
          .persona-contact[data-persona="casual"] .persona-avatar { color: #173511; background: linear-gradient(145deg, #c7f9a7, #79d64e 52%, #44b87a); }
          .persona-contact-copy { min-width: 0; display: grid; gap: 3px; }
          .persona-contact-name { font-size: 15px; font-weight: 780; }
          .persona-contact-description { overflow: hidden; color: var(--zach-muted); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
          .persona-contact-arrow { color: var(--zach-muted); font-size: 20px; }
          .persona-independent { margin: 0; padding: 0 5px; color: var(--zach-muted); font-size: 10px; line-height: 1.55; }
          .message-row {
            display: grid;
            grid-template-columns: 32px minmax(0, 1fr) 32px;
            align-items: start;
            gap: 8px;
            margin: 0 0 17px;
          }
          .message-avatar {
            width: 32px;
            height: 32px;
            display: grid;
            place-items: center;
            border: 1px solid rgb(255 255 255 / .62);
            border-radius: 10px;
            color: white;
            background: linear-gradient(145deg, #6edcff, #0a84ff 55%, #6f66ff);
            box-shadow: 0 5px 12px rgb(30 75 120 / .18), inset 0 1px 0 rgb(255 255 255 / .62);
            font-size: 9px;
            font-weight: 850;
            letter-spacing: .03em;
          }
          .user .message-avatar {
            grid-column: 3;
            background: linear-gradient(145deg, #b8f593, var(--zach-wechat-strong));
            color: #173511;
          }
          .assistant .message-avatar { grid-column: 1; }
          .message-stack { grid-row: 1; min-width: 0; max-width: min(100%, 310px); display: grid; gap: 4px; }
          .assistant .message-stack { grid-column: 2; justify-self: start; }
          .user .message-stack { grid-column: 2; justify-self: end; justify-items: end; }
          .message-label { padding: 0 3px; color: var(--zach-muted); font-size: 9px; font-weight: 700; letter-spacing: .035em; }
          .bubble {
            position: relative;
            max-width: 100%;
            padding: 10px 13px;
            border-radius: 17px;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            font-size: 14px;
            line-height: 1.5;
            box-shadow: 0 5px 14px rgb(31 52 75 / .1), inset 0 1px 0 rgb(255 255 255 / .5);
          }
          .bubble::after {
            content: "";
            position: absolute;
            top: 11px;
            width: 8px;
            height: 12px;
          }
          .user .bubble {
            color: #15300e;
            background: linear-gradient(145deg, #aff28a, var(--zach-wechat));
            border-top-right-radius: 8px;
          }
          .user .bubble::after {
            right: -7px;
            background: var(--zach-wechat);
            clip-path: polygon(0 0, 100% 38%, 0 100%);
          }
          .assistant .bubble {
            border: 1px solid var(--zach-line);
            color: var(--zach-ink);
            background: color-mix(in srgb, var(--zach-surface-strong) 84%, transparent);
            border-top-left-radius: 8px;
          }
          .assistant .bubble::after { left: -7px; background: var(--zach-surface-strong); clip-path: polygon(100% 0, 0 38%, 100% 100%); opacity: .84; }
          .assistant[data-status="pending"] .bubble:empty::after {
            content: "";
            display: block;
            width: 22px;
            height: 8px;
            background: radial-gradient(circle, var(--zach-muted) 2px, transparent 2.5px) 0 50% / 8px 8px;
            animation: thinking 850ms linear infinite;
          }
          @keyframes thinking { to { background-position: 8px 50%; } }
          .assistant[data-status="stopped"] .bubble, .assistant[data-status="error"] .bubble {
            border-style: dashed;
          }
          .message-status { padding: 0 3px; color: var(--zach-muted); font-size: 9px; }
          .message-sources { max-width: 100%; padding: 7px 10px; border: 1px solid var(--zach-line); border-radius: 11px; color: var(--zach-muted); background: var(--zach-surface); font-size: 11px; }
          .message-sources summary { cursor: pointer; color: var(--zach-ink); }
          .message-sources ol { margin: 7px 0 0; padding-left: 17px; }
          .message-sources li + li { margin-top: 7px; }
          .message-sources a { color: var(--zach-accent-strong); overflow-wrap: anywhere; }
          .message-source-location, .message-source-snippet { display: block; margin-top: 2px; overflow-wrap: anywhere; }
          .error-banner {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 9px 12px;
            border-top: 1px solid color-mix(in srgb, var(--zach-danger) 35%, var(--zach-line));
            color: var(--zach-danger);
            background: color-mix(in srgb, var(--zach-danger) 7%, var(--zach-surface));
            font-size: 12px;
          }
          .error-text { flex: 1; }
          .retry-button {
            border: 1px solid currentColor;
            border-radius: 9px;
            padding: 5px 9px;
            color: inherit;
            background: transparent;
            font-size: 11px;
            font-weight: 750;
          }
          .composer {
            padding: 11px 12px 10px;
            border-top: 1px solid var(--zach-line);
            background: linear-gradient(0deg, rgb(255 255 255 / .3), rgb(255 255 255 / .08));
            -webkit-backdrop-filter: blur(22px) saturate(160%);
            backdrop-filter: blur(22px) saturate(160%);
          }
          .input-wrap {
            display: grid;
            grid-template-columns: minmax(0, 1fr) auto;
            align-items: end;
            gap: 8px;
            padding: 6px 6px 6px 14px;
            border: 1px solid var(--zach-glass-line);
            border-radius: 22px;
            background: color-mix(in srgb, var(--zach-surface-strong) 58%, transparent);
            box-shadow: 0 6px 18px rgb(31 52 75 / .1), inset 0 1px 0 rgb(255 255 255 / .6);
            -webkit-backdrop-filter: blur(16px) saturate(145%);
            backdrop-filter: blur(16px) saturate(145%);
          }
          .input-wrap:focus-within { border-color: var(--zach-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--zach-accent) 14%, transparent); }
          textarea {
            width: 100%;
            min-height: 36px;
            max-height: 108px;
            resize: none;
            border: 0;
            outline: 0;
            color: var(--zach-ink);
            background: transparent;
            line-height: 1.4;
          }
          textarea::placeholder { color: var(--zach-muted); }
          .primary-button {
            min-width: 64px;
            min-height: 36px;
            border: 1px solid rgb(255 255 255 / .46);
            border-radius: 17px;
            padding: 7px 12px;
            color: #163412;
            background: linear-gradient(145deg, #b5f38f, var(--zach-wechat-strong));
            box-shadow: 0 6px 14px rgb(72 156 46 / .22), inset 0 1px 0 rgb(255 255 255 / .54);
            font-size: 12px;
            font-weight: 750;
          }
          .primary-button:hover:not(:disabled) { filter: brightness(1.04); transform: translateY(-1px); }
          .stop-button { color: white; background: linear-gradient(145deg, #ff7b72, var(--zach-danger)); box-shadow: 0 6px 14px rgb(180 35 24 / .2); }
          .composer-meta { display: flex; align-items: center; gap: 8px; padding: 7px 2px 0; }
          .disclaimer-short { flex: 1; color: var(--zach-muted); font-size: 9px; }
          .char-count { color: var(--zach-muted); font-size: 9px; font-variant-numeric: tabular-nums; }
          .reset-button { border: 0; padding: 2px; color: var(--zach-muted); background: transparent; font-size: 9px; text-decoration: underline; }
          .launcher {
            position: relative;
            overflow: hidden;
            display: grid;
            grid-template-columns: auto 1fr auto;
            align-items: center;
            gap: 11px;
            min-width: 238px;
            min-height: 58px;
            padding: 9px 13px 9px 9px;
            border: 1px solid var(--zach-glass-line);
            border-radius: 24px;
            color: var(--zach-ink);
            background: linear-gradient(145deg, rgb(255 255 255 / .7), rgb(242 249 255 / .4));
            box-shadow: 0 18px 42px rgb(30 57 89 / .2), inset 0 1px 0 rgb(255 255 255 / .84);
            -webkit-backdrop-filter: blur(24px) saturate(180%);
            backdrop-filter: blur(24px) saturate(180%);
            text-align: left;
            transition: transform 220ms cubic-bezier(.2, .8, .2, 1), box-shadow 220ms ease;
          }
          .launcher::before {
            content: "";
            position: absolute;
            inset: 0 42% 50% 10%;
            border-radius: 999px;
            background: rgb(255 255 255 / .42);
            filter: blur(12px);
            pointer-events: none;
          }
          .launcher:hover { transform: translateY(-3px) scale(1.012); box-shadow: 0 22px 48px rgb(30 57 89 / .24), inset 0 1px 0 rgb(255 255 255 / .9); }
          .launcher-mark {
            position: relative;
            width: 40px;
            height: 40px;
            display: grid;
            place-items: center;
            overflow: hidden;
            border: 1px solid rgb(255 255 255 / .64);
            border-radius: 14px;
            color: white;
            background: linear-gradient(145deg, #7ee1ff, #0a84ff 52%, #7065ff);
            box-shadow: 0 7px 16px rgb(10 132 255 / .26), inset 0 1px 0 rgb(255 255 255 / .58);
            font-size: 13px;
            font-weight: 850;
          }
          .launcher-copy { display: grid; gap: 1px; }
          .launcher-title { font-size: 13px; font-weight: 760; }
          .launcher-hint { color: var(--zach-muted); font-size: 10px; }
          .launcher-arrow { color: var(--zach-accent-strong); font-size: 18px; }
          .mini {
            width: min(310px, calc(100vw - 32px));
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 12px;
            padding: 7px;
            border: 1px solid var(--zach-glass-line);
            border-radius: 22px;
            background: var(--zach-glass);
            box-shadow: 0 18px 42px rgb(30 57 89 / .2), inset 0 1px 0 rgb(255 255 255 / .68);
            -webkit-backdrop-filter: blur(24px) saturate(175%);
            backdrop-filter: blur(24px) saturate(175%);
          }
          .mini-restore { flex: 1; border: 0; padding: 7px 9px; color: var(--zach-ink); background: transparent; text-align: left; font-size: 12px; font-weight: 700; }
          .sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; }
          :host([layout="stage"]) {
            position: relative;
            right: auto;
            bottom: auto;
            z-index: 1;
            display: block;
            width: 100%;
            height: 680px;
          }
          :host([layout="stage"]) .widget,
          :host([layout="stage"]) .widget[data-position="bottom-left"] {
            position: relative;
            inset: auto;
            width: 100%;
            height: 100%;
            justify-items: stretch;
          }
          :host([layout="stage"]) .panel {
            width: 100%;
            height: 100%;
            margin: 0;
            transform-origin: center;
          }
          :host([layout="stage"]) .launcher,
          :host([layout="stage"]) .mini {
            align-self: center;
            justify-self: center;
          }
          :host([layout="stage"]) .mini { margin: 0; }
          @media (max-width: 480px) {
            .widget, .widget[data-position="bottom-left"] { right: 8px; bottom: 8px; left: 8px; justify-items: stretch; }
            .panel {
              width: 100%;
              height: min(552px, calc(100dvh - 78px));
              margin-bottom: 8px;
              border-radius: 26px;
            }
            .launcher { min-width: 0; width: 100%; }
            .mini { width: 100%; margin-bottom: 8px; }
            .header { grid-template-columns: auto minmax(0, 1fr); }
            .controls { grid-column: 1 / -1; justify-content: flex-end; margin-top: -5px; }
            .header { min-height: 92px; }
            .panel { grid-template-rows: auto minmax(0, 1fr) auto auto; }
          }
          @media (max-width: 760px) {
            :host([layout="stage"]) { height: max(540px, calc(100dvh - 96px)); }
            :host([layout="stage"]) .panel { width: 100%; height: 100%; margin: 0; }
          }
          @media (prefers-contrast: more) {
            :host { --zach-line: rgb(50 63 78 / .62); --zach-glass-line: rgb(50 63 78 / .7); }
            .widget[data-theme="dark"] { --zach-line: rgb(240 246 255 / .58); --zach-glass-line: rgb(240 246 255 / .64); }
            .panel, .launcher, .mini { background: var(--zach-surface-strong); }
          }
          @supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
            .panel, .launcher, .mini, .header, .composer, .input-wrap, .quick-button { background: var(--zach-surface-strong); }
          }
          @media (prefers-reduced-motion: reduce) {
            *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
          }
        </style>
        <div class="widget" data-theme="light" data-position="bottom-right">
          <section class="panel" id="agent-chat-panel" role="dialog" aria-modal="true" aria-labelledby="agent-chat-title" hidden>
            <header class="header">
              <div class="header-leading">
                <button class="icon-button back-button" type="button" hidden>‹</button>
                <div class="avatar" aria-hidden="true">ZZ</div>
              </div>
              <div class="identity">
                <span class="eyebrow"></span>
                <strong class="name" id="agent-chat-title"></strong>
                <span class="presence"><span class="presence-dot"></span><span class="presence-text"></span></span>
              </div>
              <div class="controls">
                <label class="sr-only" for="zach-locale"></label>
                <select class="locale-select" id="zach-locale">
                  <option value="auto">AUTO</option>
                  <option value="zh">中文</option>
                  <option value="en">EN</option>
                  <option value="de">DE</option>
                </select>
                <button class="icon-button theme-button" type="button">◐</button>
                <button class="icon-button minimize-button" type="button">−</button>
                <button class="icon-button close-button" type="button">×</button>
              </div>
            </header>
            <div class="conversation">
              <div class="messages" role="log" aria-busy="false" aria-label="Conversation"></div>
            </div>
            <div class="error-banner" role="alert" hidden>
              <span class="error-text"></span>
              <button class="retry-button" type="button"></button>
            </div>
            <form class="composer">
              <label class="sr-only" for="zach-message">Message</label>
              <div class="input-wrap">
                <textarea id="zach-message" rows="1" maxlength="2000"></textarea>
                <button class="primary-button send-button" type="submit"></button>
                <button class="primary-button stop-button" type="button" hidden></button>
              </div>
              <div class="composer-meta">
                <span class="disclaimer-short"></span>
                <span class="char-count"></span>
                <button class="reset-button" type="button"></button>
              </div>
            </form>
          </section>
          <section class="mini" aria-label="Minimized chat" hidden>
            <button class="mini-restore" type="button"></button>
            <button class="icon-button mini-close" type="button">×</button>
          </section>
          <button class="launcher" type="button" aria-expanded="false" aria-controls="agent-chat-panel">
            <span class="launcher-mark" aria-hidden="true">AI</span>
            <span class="launcher-copy"><span class="launcher-title"></span><span class="launcher-hint"></span></span>
            <span class="launcher-arrow" aria-hidden="true">↗</span>
          </button>
          <div class="sr-only live-region" aria-live="polite" aria-atomic="true"></div>
        </div>
      `;
    }

    cacheElements() {
      const select = (selector) => this.shadowRoot.querySelector(selector);
      this.elements = {
        widget: select(".widget"),
        panel: select(".panel"),
        mini: select(".mini"),
        launcher: select(".launcher"),
        launcherTitle: select(".launcher-title"),
        launcherHint: select(".launcher-hint"),
        title: select(".name"),
        eyebrow: select(".eyebrow"),
        avatar: select(".avatar"),
        backButton: select(".back-button"),
        presence: select(".presence"),
        presenceText: select(".presence-text"),
        localeSelect: select(".locale-select"),
        localeLabel: select('label[for="zach-locale"]'),
        themeButton: select(".theme-button"),
        minimizeButton: select(".minimize-button"),
        closeButton: select(".close-button"),
        miniRestore: select(".mini-restore"),
        miniClose: select(".mini-close"),
        messages: select(".messages"),
        errorBanner: select(".error-banner"),
        errorText: select(".error-text"),
        retryButton: select(".retry-button"),
        form: select(".composer"),
        textarea: select("textarea"),
        sendButton: select(".send-button"),
        stopButton: select(".stop-button"),
        disclaimerShort: select(".disclaimer-short"),
        charCount: select(".char-count"),
        resetButton: select(".reset-button"),
        liveRegion: select(".live-region"),
      };
    }

    configureLayout() {
      if (!this.elements) return;
      this.elements.widget.dataset.layout = this.stageLayout ? "stage" : "floating";
      if (this.stageLayout) {
        this.elements.panel.setAttribute("role", "region");
        this.elements.panel.removeAttribute("aria-modal");
      } else {
        this.elements.panel.setAttribute("role", "dialog");
        this.elements.panel.setAttribute("aria-modal", "true");
      }
    }

    bindEvents() {
      this.elements.launcher.addEventListener("click", () => this.open());
      this.elements.closeButton.addEventListener("click", () => this.close());
      this.elements.miniClose.addEventListener("click", () => this.close());
      this.elements.minimizeButton.addEventListener("click", () => this.minimize());
      this.elements.backButton.addEventListener("click", () => this.showPersonaPicker());
      this.elements.miniRestore.addEventListener("click", () => this.open());
      this.elements.themeButton.addEventListener("click", () => this.cycleTheme());
      this.elements.localeSelect.addEventListener("change", (event) => {
        this.localePreference = normalizeLocalePreference(event.target.value);
        this.applyLocale();
        this.persistSession();
      });
      this.elements.form.addEventListener("submit", (event) => {
        event.preventDefault();
        this.send(this.elements.textarea.value);
      });
      this.elements.textarea.addEventListener("input", () => {
        this.autoSizeTextarea();
        this.updateComposer();
      });
      this.elements.textarea.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
          event.preventDefault();
          this.send(this.elements.textarea.value);
        }
      });
      this.elements.stopButton.addEventListener("click", () => this.stop());
      this.elements.retryButton.addEventListener("click", () => this.retry());
      this.elements.resetButton.addEventListener("click", () => this.reset());
      this.shadowRoot.addEventListener("keydown", (event) => this.handleDialogKeydown(event));
      const media = this.ownerDocument.defaultView?.matchMedia("(prefers-color-scheme: dark)");
      media?.addEventListener("change", this._onSchemeChange);
    }

    loadSession() {
      if (this.personaMode) {
        this.loadPersonaSession();
        return;
      }
      let stored = null;
      try {
        const current = this.ownerDocument.defaultView.sessionStorage.getItem(STORAGE_KEY);
        if (current) stored = JSON.parse(current);
        if (!stored) {
          for (const key of LEGACY_STORAGE_KEYS) {
            const legacy = this.ownerDocument.defaultView.sessionStorage.getItem(key);
            if (legacy) {
              stored = JSON.parse(legacy);
              break;
            }
          }
        }
      } catch {
        stored = null;
      }
      const migrated = migrateSession(stored);
      if (migrated) {
        this.sessionId = migrated.sessionId;
        this.messages = migrated.messages;
        this.localePreference = migrated.locale;
        this.themePreference = migrated.theme;
      } else {
        this.localePreference = normalizeLocalePreference(this.getAttribute("locale"));
        this.themePreference = normalizeTheme(this.getAttribute("theme"));
      }
      this.persistSession();
    }

    persistSession() {
      if (this.personaMode) {
        this.persistPersonaSession();
        return;
      }
      try {
        const state = {
          version: STATE_VERSION,
          sessionId: this.sessionId,
          messages: this.messages.slice(-MAX_MESSAGES).map(({ id, role, content, status, sources }) => ({
            id,
            role,
            content,
            status: ["pending", "streaming"].includes(status) ? "stopped" : status,
            ...(role === "assistant" && sources?.length ? { sources } : {}),
          })),
          locale: this.localePreference,
          theme: this.themePreference,
        };
        this.ownerDocument.defaultView.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
        for (const key of LEGACY_STORAGE_KEYS) {
          this.ownerDocument.defaultView.sessionStorage.removeItem(key);
        }
      } catch {
        // Storage can be unavailable in privacy modes; the widget still works in memory.
      }
    }

    loadPersonaSession() {
      let stored = null;
      let legacy = null;
      try {
        const current = this.ownerDocument.defaultView.sessionStorage.getItem(PERSONA_STORAGE_KEY);
        if (current) stored = JSON.parse(current);
        if (!stored) {
          const previous = this.ownerDocument.defaultView.sessionStorage.getItem(STORAGE_KEY);
          if (previous) legacy = migrateSession(JSON.parse(previous));
        }
      } catch {
        stored = null;
        legacy = null;
      }
      const migrated = migratePersonaSession(stored, legacy);
      this.personaConversations = migrated.conversations;
      this.activePersona = migrated.activePersona;
      this.localePreference = stored || legacy
        ? migrated.locale
        : normalizeLocalePreference(this.getAttribute("locale"));
      this.themePreference = stored || legacy
        ? migrated.theme
        : normalizeTheme(this.getAttribute("theme"));
      if (this.activePersona) {
        const conversation = this.personaConversations[this.activePersona];
        this.sessionId = conversation.sessionId;
        this.messages = conversation.messages;
      } else {
        this.sessionId = randomId();
        this.messages = [];
      }
      this.persistPersonaSession();
    }

    persistPersonaSession() {
      try {
        if (this.activePersona) {
          this.personaConversations[this.activePersona] = {
            sessionId: this.sessionId,
            messages: this.messages.slice(-MAX_MESSAGES).map(({ id, role, content, status, sources }) => ({
              id,
              role,
              content,
              status: ["pending", "streaming"].includes(status) ? "stopped" : status,
              ...(role === "assistant" && sources?.length ? { sources } : {}),
            })),
          };
        }
        const state = {
          version: PERSONA_STATE_VERSION,
          activePersona: this.activePersona,
          conversations: this.personaConversations,
          locale: this.localePreference,
          theme: this.themePreference,
        };
        this.ownerDocument.defaultView.sessionStorage.setItem(
          PERSONA_STORAGE_KEY,
          JSON.stringify(state),
        );
      } catch {
        // Storage can be unavailable in privacy modes; both chats still work in memory.
      }
    }

    selectPersona(id) {
      if (!this.personaMode || !["professional", "casual"].includes(id) || this.busy) {
        return false;
      }
      if (this.activePersona) this.persistPersonaSession();
      this.activePersona = id;
      const conversation = this.personaConversations[id] || createPersonaConversation();
      this.personaConversations[id] = conversation;
      this.sessionId = conversation.sessionId;
      this.messages = conversation.messages;
      this.requestState = "idle";
      this.lastFailed = null;
      this.clearError();
      this.renderProfile();
      this.renderMessages();
      this.updateComposer();
      this.updatePresence();
      this.persistPersonaSession();
      this.ownerDocument.defaultView?.requestAnimationFrame(() => this.elements.textarea.focus());
      return true;
    }

    showPersonaPicker() {
      if (!this.personaMode || this.busy) return false;
      this.persistPersonaSession();
      this.activePersona = null;
      this.messages = [];
      this.sessionId = randomId();
      this.lastFailed = null;
      this.clearError();
      this.renderProfile();
      this.renderMessages();
      this.updateComposer();
      this.updatePresence();
      this.persistPersonaSession();
      this.shadowRoot.querySelector(".persona-contact")?.focus();
      return true;
    }

    open() {
      this._previousFocus = this.ownerDocument.activeElement;
      this.view = "open";
      this.updateView();
      this.ownerDocument.defaultView?.requestAnimationFrame(() => {
        if (this.personaMode && !this.activePersona) {
          this.shadowRoot.querySelector(".persona-contact")?.focus();
        } else {
          this.elements.textarea.focus();
        }
      });
    }

    minimize() {
      this.view = "minimized";
      this.updateView();
      this.elements.miniRestore.focus();
    }

    close() {
      this.abortRequest("close");
      this.view = "closed";
      this.updateView();
      this.elements.launcher.focus();
    }

    updateView() {
      const open = this.view === "open";
      const minimized = this.view === "minimized";
      this.elements.panel.hidden = !open;
      this.elements.mini.hidden = !minimized;
      this.elements.launcher.hidden = open || minimized;
      this.elements.launcher.setAttribute("aria-expanded", String(open));
      if (open) this.scrollToEnd(false);
    }

    handleDialogKeydown(event) {
      if (event.key === "Escape" && this.view !== "closed") {
        event.preventDefault();
        this.close();
        return;
      }
      if (this.stageLayout) return;
      if (event.key !== "Tab" || this.view !== "open") return;
      const focusable = [...this.shadowRoot.querySelectorAll("button:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href]")].filter(
        (element) => !element.hidden && element.getClientRects().length,
      );
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && this.shadowRoot.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && this.shadowRoot.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    applyLocale() {
      if (!this.elements) return;
      const copy = this.copy;
      this.elements.localeSelect.value = this.localePreference;
      this.elements.localeLabel.textContent = copy.language;
      this.elements.localeSelect.setAttribute("aria-label", copy.language);
      this.elements.launcherTitle.textContent = copy.launcher;
      this.elements.launcherHint.textContent = copy.launcherHint;
      this.elements.launcher.setAttribute("aria-label", copy.launcher);
      this.elements.eyebrow.textContent = copy.aiTwin;
      this.elements.minimizeButton.setAttribute("aria-label", copy.minimize);
      this.elements.minimizeButton.title = copy.minimize;
      this.elements.closeButton.setAttribute("aria-label", copy.close);
      this.elements.closeButton.title = copy.close;
      this.elements.miniClose.setAttribute("aria-label", copy.close);
      this.elements.backButton.setAttribute("aria-label", this.personaCopy.back);
      this.elements.backButton.title = this.personaCopy.back;
      this.elements.miniRestore.textContent = copy.restore;
      this.elements.textarea.placeholder = copy.placeholder;
      this.elements.textarea.setAttribute("aria-label", copy.placeholder);
      this.elements.sendButton.textContent = copy.send;
      this.elements.stopButton.textContent = copy.stop;
      this.elements.retryButton.textContent = copy.retry;
      this.elements.resetButton.textContent = copy.reset;
      this.elements.disclaimerShort.textContent = copy.disclaimerShort;
      this.elements.messages.setAttribute("aria-label", copy.conversation);
      this.elements.mini.setAttribute("aria-label", copy.minimize);
      this.renderProfile();
      this.renderMessages();
      this.updateThemeButton();
      this.updatePresence();
      this.updateComposer();
      if (!this.elements.errorBanner.hidden && this.lastFailed?.code) {
        this.showError(this.lastFailed.code, this.lastFailed.retryable);
      }
    }

    applyTheme() {
      if (!this.elements) return;
      const darkSystem = this.ownerDocument.defaultView?.matchMedia("(prefers-color-scheme: dark)").matches;
      const resolved = this.themePreference === "auto" ? (darkSystem ? "dark" : "light") : this.themePreference;
      this.dataset.themePreference = this.themePreference;
      this.dataset.resolvedTheme = resolved;
      this.elements.widget.dataset.theme = resolved;
      this.elements.widget.dataset.position =
        this.getAttribute("position") === "bottom-left" ? "bottom-left" : "bottom-right";
      this.updateThemeButton();
      this.dispatchEvent(new CustomEvent("zach-theme-change", {
        bubbles: true,
        composed: true,
        detail: {
          preference: this.themePreference,
          resolvedTheme: resolved,
        },
      }));
    }

    cycleTheme() {
      const order = ["auto", "light", "dark"];
      this.themePreference = order[(order.indexOf(this.themePreference) + 1) % order.length];
      this.applyTheme();
      this.persistSession();
    }

    updateThemeButton() {
      if (!this.elements) return;
      const label = this.copy.theme.replace("{value}", this.copy.themes[this.themePreference]);
      this.elements.themeButton.setAttribute("aria-label", label);
      this.elements.themeButton.title = label;
      this.elements.themeButton.textContent = { auto: "◐", light: "☀", dark: "☾" }[this.themePreference];
    }

    updatePresence() {
      if (!this.elements) return;
      const online = this.ownerDocument.defaultView?.navigator.onLine !== false;
      this.elements.presence.dataset.offline = String(!online);
      this.elements.presenceText.textContent = online
        ? this.personaMode && !this.activePersona
          ? this.personaCopy.pickerStatus
          : this.copy.online
        : this.copy.offline;
    }

    apiUrl(path) {
      const windowRef = this.ownerDocument.defaultView;
      const fallback = windowRef.location.origin;
      try {
        const url = new URL(this.getAttribute("api-base") || fallback, windowRef.location.href);
        if (!["http:", "https:"].includes(url.protocol)) throw new Error("unsafe protocol");
        return `${url.href.replace(/\/$/, "")}${path}`;
      } catch {
        return `${fallback}${path}`;
      }
    }

    async fetchProfile() {
      this.profileController?.abort();
      this.profileController = new AbortController();
      this.elements.presenceText.textContent = this.copy.loadingProfile;
      try {
        const response = await this.ownerDocument.defaultView.fetch(this.apiUrl("/api/v1/profile"), {
          headers: { Accept: "application/json" },
          signal: this.profileController.signal,
        });
        if (!response.ok) throw new Error("profile unavailable");
        const profile = await response.json();
        this.profile = {
          displayName: safeText(profile.display_name, 100) || "Example Candidate",
          title: safeText(profile.title, 240),
          intro: {
            zh: safeText(profile.intro?.zh, 1000),
            en: safeText(profile.intro?.en, 1000),
          },
          quickQuestions: profile.quick_questions && typeof profile.quick_questions === "object" ? profile.quick_questions : {},
          contacts: profile.contact && typeof profile.contact === "object" ? profile.contact : {},
          disclaimer: safeText(profile.disclaimer, 1000),
        };
        this.renderProfile();
        this.renderMessages();
        this.updatePresence();
      } catch (error) {
        if (error.name !== "AbortError") {
          this.elements.presenceText.textContent = this.copy.profileUnavailable;
        }
      }
    }

    renderProfile() {
      if (!this.elements) return;
      if (this.personaMode) {
        const definition = this.personaDefinition();
        this.elements.title.textContent = definition?.name || this.personaCopy.pickerTitle;
        this.elements.eyebrow.textContent = definition ? this.copy.aiTwin : this.personaCopy.pickerHeading;
        this.elements.avatar.textContent = definition?.avatar || "ZZ";
        this.elements.backButton.hidden = !this.activePersona;
        this.elements.backButton.disabled = this.busy;
        this.elements.widget.dataset.persona = this.activePersona || "picker";
        this.elements.panel.setAttribute(
          "aria-label",
          `${this.elements.title.textContent} — ${this.copy.aiTwin}`,
        );
        return;
      }
      const titleOverride = safeText(this.getAttribute("title"), 100);
      this.elements.title.textContent = titleOverride || this.profile?.displayName || "Example Candidate";
      this.elements.panel.setAttribute(
        "aria-label",
        `${this.elements.title.textContent} — ${this.copy.aiTwin}`,
      );
    }

    currentIntro() {
      if (this.personaMode && this.activePersona) return this.personaDefinition().intro;
      if (this.locale === "zh") return this.profile?.intro.zh || this.copy.introFallback;
      return this.profile?.intro.en || this.copy.introFallback;
    }

    currentQuestions() {
      if (this.personaMode && this.activePersona) return this.personaDefinition().questions;
      const fromProfile = this.profile?.quickQuestions?.[this.locale];
      if (Array.isArray(fromProfile) && fromProfile.length) {
        return fromProfile.map((item) => safeText(item, 240)).filter(Boolean).slice(0, 4);
      }
      return FALLBACK_QUESTIONS[this.locale];
    }

    renderMessages() {
      if (!this.elements) return;
      const documentRef = this.ownerDocument;
      const fragment = documentRef.createDocumentFragment();
      if (this.personaMode && !this.activePersona) {
        fragment.append(this.renderPersonaPicker());
      } else if (!this.messages.length) {
        const empty = createElement(documentRef, "div", "empty");
        const intro = createElement(documentRef, "section", "intro-card");
        intro.append(createElement(
          documentRef,
          "h2",
          "intro-title",
          this.personaMode ? this.personaDefinition().greeting : this.copy.emptyTitle,
        ));
        const subtitle = this.personaMode ? this.personaDefinition().description : this.profile?.title;
        if (subtitle) {
          intro.append(createElement(documentRef, "p", "profile-title", subtitle));
        }
        intro.append(createElement(documentRef, "p", "intro-text", this.currentIntro()));
        if (!this.personaMode || this.activePersona === "professional") {
          const contacts = this.renderContacts();
          if (contacts.childElementCount) intro.append(contacts);
        }
        const quick = createElement(documentRef, "section", "quick-section");
        quick.append(createElement(documentRef, "p", "quick-title", this.copy.quickTitle));
        const quickList = createElement(documentRef, "div", "quick-list");
        for (const question of this.currentQuestions()) {
          const button = createElement(documentRef, "button", "quick-button", question);
          button.type = "button";
          button.disabled = this.busy;
          button.addEventListener("click", () => this.send(question));
          quickList.append(button);
        }
        quick.append(quickList);
        const disclaimer = createElement(
          documentRef,
          "p",
          "disclaimer-full",
          this.locale === "zh" && this.profile?.disclaimer
            ? this.profile.disclaimer
            : this.copy.fullDisclaimer,
        );
        empty.append(intro, quick, disclaimer);
        fragment.append(empty);
      } else {
        for (const message of this.messages) {
          const row = createElement(documentRef, "article", `message-row ${message.role}`);
          row.dataset.messageId = message.id;
          row.dataset.status = message.status;
          const avatar = createElement(
            documentRef,
            "span",
            `message-avatar${message.role === "assistant" ? " assistant-avatar" : ""}`,
            message.role === "user"
              ? "ME"
              : this.personaMode
                ? this.personaDefinition().avatar
                : "ZZ",
          );
          avatar.setAttribute("aria-hidden", "true");
          const stack = createElement(documentRef, "div", "message-stack");
          const label = createElement(
            documentRef,
            "span",
            "message-label",
            message.role === "user"
              ? (this.locale === "de" ? "DU" : this.locale === "zh" ? "你" : "YOU")
              : this.personaMode
                ? `${this.personaDefinition().name} · AI`
                : "AGENT · AI",
          );
          const bubble = createElement(documentRef, "div", "bubble", message.content);
          const status = createElement(documentRef, "span", "message-status");
          if (message.status === "stopped") status.textContent = this.copy.stopped;
          stack.append(label, bubble);
          if (message.role === "assistant" && message.status === "complete" && message.sources?.length) {
            const sources = createElement(documentRef, "details", "message-sources");
            sources.append(createElement(documentRef, "summary", "", this.copy.sources));
            const list = createElement(documentRef, "ol");
            for (const source of message.sources) {
              const item = createElement(documentRef, "li");
              const link = createElement(documentRef, "a", "", `[${source.source_id}] ${source.title}`);
              link.href = this.apiUrl(source.url);
              link.target = "_blank";
              link.rel = "noopener noreferrer";
              item.append(link);
              const location = source.locations.map((part) =>
                Object.entries(part).map(([key, value]) => `${key}: ${value}`).join(" · ")).filter(Boolean).join(" / ");
              if (location) item.append(createElement(documentRef, "span", "message-source-location", location));
              if (source.snippet) item.append(createElement(documentRef, "span", "message-source-snippet", source.snippet));
              list.append(item);
            }
            sources.append(list);
            stack.append(sources);
          }
          if (status.textContent) stack.append(status);
          row.append(stack, avatar);
          fragment.append(row);
        }
      }
      this.elements.messages.replaceChildren(fragment);
      this.elements.messages.setAttribute("aria-busy", String(this.busy));
      this.scrollToEnd(false);
    }

    renderPersonaPicker() {
      const documentRef = this.ownerDocument;
      const picker = createElement(documentRef, "section", "persona-picker");
      const heading = createElement(documentRef, "div", "persona-picker-heading");
      heading.append(
        createElement(documentRef, "h2", "persona-picker-title", this.personaCopy.pickerHeading),
        createElement(documentRef, "p", "persona-picker-hint", this.personaCopy.pickerHint),
      );
      const list = createElement(documentRef, "div", "persona-list");
      for (const id of ["professional", "casual"]) {
        const definition = this.personaDefinition(id);
        const button = createElement(documentRef, "button", "persona-contact");
        button.type = "button";
        button.dataset.persona = id;
        const avatar = createElement(documentRef, "span", "persona-avatar", definition.avatar);
        avatar.setAttribute("aria-hidden", "true");
        const copy = createElement(documentRef, "span", "persona-contact-copy");
        copy.append(
          createElement(documentRef, "span", "persona-contact-name", definition.name),
          createElement(documentRef, "span", "persona-contact-description", definition.description),
        );
        const arrow = createElement(documentRef, "span", "persona-contact-arrow", "›");
        arrow.setAttribute("aria-hidden", "true");
        button.append(avatar, copy, arrow);
        button.addEventListener("click", () => this.selectPersona(id));
        list.append(button);
      }
      picker.append(
        heading,
        list,
        createElement(documentRef, "p", "persona-independent", this.personaCopy.independent),
      );
      return picker;
    }

    renderContacts() {
      const documentRef = this.ownerDocument;
      const list = createElement(documentRef, "div", "contact-list");
      const labels = { website: "WEB", github: "GITHUB", linkedin: "LINKEDIN", email: "EMAIL" };
      for (const [key, label] of Object.entries(labels)) {
        const raw = this.profile?.contacts?.[key];
        const url = this.safeContactUrl(raw, key === "email");
        if (!url) continue;
        const link = createElement(documentRef, "a", "contact-link", label);
        link.href = url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        list.append(link);
      }
      return list;
    }

    safeContactUrl(value, email = false) {
      if (typeof value !== "string" || !value.trim()) return null;
      try {
        const candidate = email && !value.startsWith("mailto:") ? `mailto:${value.trim()}` : value.trim();
        const url = new URL(candidate, this.ownerDocument.defaultView.location.href);
        return ["https:", "http:", "mailto:"].includes(url.protocol) ? url.href : null;
      } catch {
        return null;
      }
    }

    updateComposer() {
      if (!this.elements) return;
      const value = this.elements.textarea.value;
      const choosingPersona = this.personaMode && !this.activePersona;
      this.elements.form.hidden = choosingPersona;
      this.elements.backButton.disabled = this.busy;
      this.elements.sendButton.hidden = this.busy;
      this.elements.stopButton.hidden = !this.busy;
      this.elements.sendButton.disabled = this.busy || !value.trim();
      this.elements.textarea.disabled = this.busy;
      this.elements.charCount.textContent = this.copy.chars.replace("{count}", String(value.length));
      this.elements.messages.setAttribute("aria-busy", String(this.busy));
    }

    autoSizeTextarea() {
      const textarea = this.elements.textarea;
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 108)}px`;
    }

    buildHistory() {
      const completeTurns = [];
      let pendingUser = null;
      for (const message of this.messages) {
        if (message.role === "user" && message.status === "complete") {
          pendingUser = { role: "user", content: message.content };
        } else if (
          message.role === "assistant" &&
          message.status === "complete" &&
          pendingUser
        ) {
          completeTurns.push(pendingUser, { role: "assistant", content: message.content });
          pendingUser = null;
        }
      }
      return completeTurns.slice(-20);
    }

    async send(rawMessage, retryContext = null) {
      const message = safeText(rawMessage, MAX_MESSAGE_CHARS).trim();
      if (!message || this.busy || (this.personaMode && !this.activePersona)) return false;
      this.clearError();
      const history = retryContext?.history || this.buildHistory();
      const userMessage = retryContext?.userMessage || {
        id: randomId(),
        role: "user",
        content: message,
        status: "complete",
      };
      if (!retryContext) this.messages.push(userMessage);
      const assistantMessage = {
        id: randomId(),
        role: "assistant",
        content: "",
        status: "pending",
        sources: [],
      };
      this.messages.push(assistantMessage);
      this.messages = this.messages.slice(-MAX_MESSAGES);
      this.elements.textarea.value = "";
      this.autoSizeTextarea();
      this.requestState = "sending";
      const controller = new AbortController();
      const requestRecord = { controller, abortReason: null, assistantMessage };
      this.currentRequest = requestRecord;
      this.lastFailed = null;
      this.renderMessages();
      this.updateComposer();
      this.persistSession();

      if (this.ownerDocument.defaultView?.navigator.onLine === false) {
        this.failRequest(new WidgetError("OFFLINE"), { message, history, userMessage, assistantMessage });
        return false;
      }

      try {
        const response = await this.ownerDocument.defaultView.fetch(this.apiUrl("/api/v1/chat/stream"), {
          method: "POST",
          headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
          body: JSON.stringify({
            message,
            history,
            session_id: this.sessionId,
            locale: { zh: "zh-CN", en: "en", de: "de" }[this.locale],
            ...(this.personaMode ? { persona_mode: this.activePersona } : {}),
          }),
          signal: controller.signal,
        });
        if (!response.ok) throw await this.responseError(response);
        if (!response.headers.get("content-type")?.toLowerCase().includes("text/event-stream")) {
          throw new WidgetError("STREAM_INVALID");
        }
        let sawDone = false;
        let availableSources = [];
        for await (const event of parseSSEStream(response.body)) {
          let data;
          try {
            data = JSON.parse(event.data);
          } catch {
            throw new WidgetError("STREAM_INVALID");
          }
          if (event.event === "meta") {
            this.requestState = "streaming";
            assistantMessage.status = "streaming";
          } else if (event.event === "sources") {
            availableSources = Array.isArray(data.sources)
              ? data.sources.map(sourceCitation).filter(Boolean).slice(0, 5)
              : [];
          } else if (event.event === "delta") {
            if (typeof data.text !== "string") throw new WidgetError("STREAM_INVALID");
            this.requestState = "streaming";
            assistantMessage.status = "streaming";
            assistantMessage.content += data.text;
            this.renderMessages();
            this.persistSession();
          } else if (event.event === "error") {
            throw new WidgetError(
              safeText(data.code, 80) || "NETWORK_ERROR",
              safeText(data.message, 300),
              data.retryable !== false,
            );
          } else if (event.event === "done") {
            sawDone = true;
            const citedIds = new Set(Array.isArray(data.source_ids) ? data.source_ids : []);
            assistantMessage.sources = availableSources.filter((source) => citedIds.has(source.source_id));
          }
        }
        if (!sawDone || !assistantMessage.content) throw new WidgetError("STREAM_INVALID");
        assistantMessage.status = "complete";
        this.requestState = "idle";
        this.currentRequest = null;
        this.renderMessages();
        this.updateComposer();
        this.persistSession();
        this.announce(this.copy.responseReady);
        return true;
      } catch (error) {
        if (error.name === "AbortError") {
          const reason = requestRecord.abortReason;
          if (reason === "reset") return false;
          if (assistantMessage.content) {
            assistantMessage.status = "stopped";
          } else {
            this.messages = this.messages.filter((item) => item.id !== assistantMessage.id);
          }
          this.requestState = "idle";
          this.currentRequest = null;
          this.renderMessages();
          this.updateComposer();
          this.persistSession();
          this.announce(this.copy.stopped);
          return false;
        }
        this.failRequest(
          error instanceof WidgetError ? error : new WidgetError("NETWORK_ERROR"),
          { message, history, userMessage, assistantMessage },
        );
        return false;
      }
    }

    async responseError(response) {
      let payload = null;
      try {
        payload = await response.json();
      } catch {
        // The status code still maps to a stable client error.
      }
      const code = safeText(payload?.error?.code, 80) || {
        413: "REQUEST_TOO_LARGE",
        422: "REQUEST_INVALID",
        429: "RATE_LIMITED",
        503: "SERVICE_NOT_READY",
      }[response.status] || "NETWORK_ERROR";
      return new WidgetError(code, safeText(payload?.error?.message, 300), payload?.error?.retryable !== false);
    }

    failRequest(error, context) {
      if (context.assistantMessage.content) {
        context.assistantMessage.status = "error";
      } else {
        this.messages = this.messages.filter((item) => item.id !== context.assistantMessage.id);
      }
      this.requestState = "error";
      this.currentRequest = null;
      this.lastFailed = {
        code: error.code,
        retryable: error.retryable,
        message: context.message,
        history: context.history,
        userMessage: context.userMessage,
        assistantMessageId: context.assistantMessage.id,
      };
      this.showError(error.code, error.retryable);
      this.renderMessages();
      this.updateComposer();
      this.persistSession();
      this.announce(this.errorMessage(error.code));
    }

    retry() {
      if (!this.lastFailed || this.busy || !this.lastFailed.retryable) return;
      const context = this.lastFailed;
      this.messages = this.messages.filter((item) => item.id !== context.assistantMessageId);
      this.send(context.message, {
        history: context.history,
        userMessage: context.userMessage,
      });
    }

    stop() {
      this.abortRequest("stop");
    }

    abortRequest(reason) {
      if (!this.currentRequest) return;
      this.currentRequest.abortReason = reason;
      this.currentRequest.controller.abort();
    }

    reset() {
      this.abortRequest("reset");
      this.messages = [];
      this.sessionId = randomId();
      this.requestState = "idle";
      this.currentRequest = null;
      this.lastFailed = null;
      this.clearError();
      try {
        const storage = this.ownerDocument.defaultView.sessionStorage;
        if (!this.personaMode) {
          storage.removeItem(STORAGE_KEY);
          for (const key of LEGACY_STORAGE_KEYS) storage.removeItem(key);
        }
      } catch {
        // Reset still applies to in-memory state.
      }
      this.elements.textarea.value = "";
      this.renderMessages();
      this.updateComposer();
      this.persistSession();
      this.announce(this.copy.resetDone);
      this.elements.textarea.focus();
    }

    showError(code, retryable = true) {
      this.elements.errorText.textContent = this.errorMessage(code);
      this.elements.retryButton.hidden = !retryable;
      this.elements.errorBanner.hidden = false;
    }

    clearError() {
      if (!this.elements) return;
      this.elements.errorBanner.hidden = true;
      this.elements.errorText.textContent = "";
    }

    errorMessage(code) {
      return this.copy.errors[code] || this.copy.errors.DEFAULT;
    }

    announce(message) {
      this.elements.liveRegion.textContent = "";
      this.ownerDocument.defaultView?.setTimeout(() => {
        this.elements.liveRegion.textContent = message;
      }, 20);
    }

    scrollToEnd(smooth = true) {
      if (!this.elements || this.view !== "open") return;
      const reduced = this.ownerDocument.defaultView?.matchMedia("(prefers-reduced-motion: reduce)").matches;
      this.elements.messages.scrollTo({
        top: this.elements.messages.scrollHeight,
        behavior: smooth && !reduced ? "smooth" : "auto",
      });
    }
  }

  if (!globalThis.customElements.get(TAG_NAME)) {
    globalThis.customElements.define(TAG_NAME, ZachChatWidget);
  }
})();
