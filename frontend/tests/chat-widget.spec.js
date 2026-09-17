const { test, expect } = require("@playwright/test");

const fixture = "/tests/fixture.html";

async function resetServer(page) {
  await page.request.post("/__test/reset");
}

async function openWidget(page) {
  await page.getByRole("button", { name: "Chat with my AI twin" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

async function finishHomepageAnimations(page) {
  await page.evaluate(async () => {
    const host = document.querySelector("#main-chat");
    const panel = host?.shadowRoot?.querySelector(".panel");
    const animations = [...document.getAnimations(), ...(panel?.getAnimations() || [])]
      .filter((animation) => animation.effect?.getComputedTiming().iterations !== Infinity);
    await Promise.all(animations.map((animation) => animation.finished.catch(() => undefined)));
  });
}

test.beforeEach(async ({ page }) => {
  await resetServer(page);
  await page.goto(fixture);
  await expect(page.getByRole("button", { name: "Chat with my AI twin" })).toBeVisible();
});

test("SSE parser handles UTF-8 splits, CRLF, cross-chunk records, comments, and multiple events", async ({ page }) => {
  const parsed = await page.evaluate(async () => {
    const Widget = customElements.get("agent-chat-widget");
    const encoder = new TextEncoder();
    const bytes = encoder.encode(
      ': keep-alive\r\n\r\nevent: delta\r\ndata: {"text":"我最有"}\r\n\r\nevent: delta\ndata: {"text":"代表性"}\n\nevent: done\ndata: {"finish_reason":"stop"}\n\n',
    );
    const chinese = encoder.encode("最");
    let split = 0;
    for (let index = 0; index < bytes.length - chinese.length; index += 1) {
      if (bytes[index] === chinese[0] && bytes[index + 1] === chinese[1]) {
        split = index + 1;
        break;
      }
    }
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(bytes.slice(0, split));
        controller.enqueue(bytes.slice(split, split + 5));
        controller.enqueue(bytes.slice(split + 5));
        controller.close();
      },
    });
    const events = [];
    for await (const event of Widget.parseSSEStream(stream)) events.push(event);
    return events;
  });

  expect(parsed).toEqual([
    { event: "delta", data: '{"text":"我最有"}' },
    { event: "delta", data: '{"text":"代表性"}' },
    { event: "done", data: '{"finish_reason":"stop"}' },
  ]);
});

test("profile, streaming, duplicate guard, session restore, minimize, close, and reset work", async ({ page }) => {
  await openWidget(page);
  await expect(page.getByText("Example Candidate", { exact: true })).toBeVisible();
  await expect(page.getByText("Fictional software engineering student")).toBeVisible();
  await expect(page.getByText("I am a completely fictional example candidate.", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "Could you introduce yourself?" }).click();
  await expect(page.getByText("我是完全虚构的示例候选人。")).toBeVisible();
  const firstRequests = await (await page.request.get("/__test/requests")).json();
  expect(firstRequests).toHaveLength(1);
  expect(firstRequests[0].history).toEqual([]);
  expect(firstRequests[0].session_id).toMatch(/^[0-9a-f-]{36}$/i);

  await page.reload();
  await openWidget(page);
  await expect(page.getByText("Could you introduce yourself?", { exact: true })).toBeVisible();
  await expect(page.getByText("我是完全虚构的示例候选人。")).toBeVisible();

  await page.getByRole("button", { name: "Minimize chat" }).click();
  await expect(page.getByRole("button", { name: "Restore chat" })).toBeVisible();
  await page.getByRole("button", { name: "Restore chat" }).click();
  await page.getByRole("button", { name: "Reset local session" }).click();
  await expect(page.getByText("Try one of these")).toBeVisible();
  await expect(page.getByText("我是完全虚构的示例候选人。")).toHaveCount(0);
  await page.getByRole("button", { name: "Close chat" }).click();
  await expect(page.getByRole("button", { name: "Chat with my AI twin" })).toBeFocused();
});

test("stop aborts a stream and active requests cannot be duplicated", async ({ page }) => {
  await openWidget(page);
  const input = page.getByRole("textbox", { name: "Ask me anything…" });
  await input.fill("__STOP__ __SLOW__");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("partial response")).toBeVisible();
  await expect(page.getByRole("button", { name: "Stop generating" })).toBeVisible();
  expect(await (await page.request.get("/__test/requests")).json()).toHaveLength(1);
  await page.getByRole("button", { name: "Stop generating" }).click();
  await expect(page.getByText("Generation stopped.")).toBeVisible();
  await expect(page.getByRole("textbox", { name: "Ask me anything…" })).toBeEnabled();
  expect(await (await page.request.get("/__test/requests")).json()).toHaveLength(1);
});

test("stream error retries without duplicating the user message", async ({ page }) => {
  await openWidget(page);
  const input = page.getByRole("textbox", { name: "Ask me anything…" });
  await input.fill("__FAIL_ONCE__");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("alert")).toContainText("AI service is busy");
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("Retry succeeded.")).toBeVisible();
  await expect(page.getByText("__FAIL_ONCE__", { exact: true })).toHaveCount(1);
  expect(await (await page.request.get("/__test/requests")).json()).toHaveLength(2);
});

test("offline send stays local and can retry after reconnection", async ({ page, context }) => {
  await openWidget(page);
  await context.setOffline(true);
  await expect(page.getByText("You are offline")).toBeVisible();
  const input = page.getByRole("textbox", { name: "Ask me anything…" });
  await input.fill("send after reconnect");
  await input.press("Enter");
  await expect(page.getByRole("alert")).toContainText("offline");
  expect(await (await page.request.get("/__test/requests")).json()).toHaveLength(0);

  await context.setOffline(false);
  await expect(page.getByText("Ready", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("我是完全虚构的示例候选人。")).toBeVisible();
  expect(await (await page.request.get("/__test/requests")).json()).toHaveLength(1);
});

test("user and model HTML are always rendered as inert text", async ({ page }) => {
  await openWidget(page);
  const payload = '__XSS__ <img src=x onerror="globalThis.__xss=1"><script>globalThis.__xss=2</script>';
  await page.getByRole("textbox", { name: "Ask me anything…" }).fill(payload);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText(payload, { exact: true })).toBeVisible();
  await expect(page.getByText('<img src=x onerror="globalThis.__xss=1">', { exact: false })).toBeVisible();
  const audit = await page.evaluate(() => {
    const root = document.querySelector("agent-chat-widget").shadowRoot;
    return {
      injectedNodes: root.querySelectorAll(".messages img, .messages script").length,
      xssValue: globalThis.__xss,
    };
  });
  expect(audit).toEqual({ injectedNodes: 0, xssValue: undefined });
});

test("Liquid Glass shell and WeChat-style bubble anatomy are present", async ({ page }) => {
  await openWidget(page);
  await page.getByRole("button", { name: "Could you introduce yourself?" }).click();
  await expect(page.getByText("我是完全虚构的示例候选人。")).toBeVisible();

  const appearance = await page.evaluate(() => {
    const root = document.querySelector("agent-chat-widget").shadowRoot;
    const panel = root.querySelector(".panel");
    const composer = root.querySelector(".composer");
    const userRow = root.querySelector(".message-row.user");
    const assistantRow = root.querySelector(".message-row.assistant");
    const userAvatar = userRow.querySelector(".message-avatar");
    const assistantAvatar = assistantRow.querySelector(".message-avatar");
    const userBubble = userRow.querySelector(".bubble");
    const assistantBubble = assistantRow.querySelector(".bubble");
    return {
      panelBackdrop: getComputedStyle(panel).backdropFilter,
      composerBackdrop: getComputedStyle(composer).backdropFilter,
      panelRadius: parseFloat(getComputedStyle(panel).borderRadius),
      userAvatar: userAvatar.textContent,
      assistantAvatar: assistantAvatar.textContent,
      userAvatarColumn: getComputedStyle(userAvatar).gridColumnStart,
      assistantAvatarColumn: getComputedStyle(assistantAvatar).gridColumnStart,
      userTail: getComputedStyle(userBubble, "::after").clipPath,
      assistantTail: getComputedStyle(assistantBubble, "::after").clipPath,
    };
  });

  expect(appearance.panelBackdrop).toContain("blur");
  expect(appearance.composerBackdrop).toContain("blur");
  expect(appearance.panelRadius).toBeGreaterThanOrEqual(26);
  expect(appearance.userAvatar).toBe("ME");
  expect(appearance.assistantAvatar).toBe("ZZ");
  expect(appearance.userAvatarColumn).toBe("3");
  expect(appearance.assistantAvatarColumn).toBe("1");
  expect(appearance.userTail).not.toBe("none");
  expect(appearance.assistantTail).not.toBe("none");
});

test("chat-first homepage keeps professional and casual persona chats separate", async ({ page }) => {
  const personaRequests = [];
  await page.route("http://localhost:8000/api/v1/profile", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        persona_version: "example-0.1.0",
        display_name: "Example Candidate",
        title: "Fictional software engineering student",
        intro: { zh: "公开 Persona 简介。", en: "Public Persona profile." },
        quick_questions: {},
        contact: { website: "https://example.com" },
        disclaimer: "AI-generated",
      }),
    }),
  );
  await page.route("http://localhost:8000/api/v1/chat/stream", (route) => {
    const payload = route.request().postDataJSON();
    personaRequests.push(payload);
    const reply = payload.persona_mode === "casual" ? "这是闲聊人格回复。" : "这是专业人格回复。";
    return route.fulfill({
      status: 200,
      headers: { "Content-Type": "text/event-stream; charset=utf-8" },
      body: [
        'event: meta\ndata: {"request_id":"stage_1"}\n\n',
        `event: delta\ndata: ${JSON.stringify({ text: reply })}\n\n`,
        'event: done\ndata: {"finish_reason":"stop"}\n\n',
      ].join(""),
    });
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/index.html");
  await expect(page.getByRole("heading", { name: "你好 / Hello / Hallo" })).toBeVisible();
  await expect(page.locator(".greeting-word")).toHaveText("你好");
  await expect(page.locator(".prompt")).toHaveCount(0);
  await finishHomepageAnimations(page);

  const layout = await page.evaluate(() => {
    const host = document.querySelector("#main-chat");
    const panel = host.shadowRoot.querySelector(".panel");
    const intro = document.querySelector(".intro").getBoundingClientRect();
    const stage = document.querySelector(".chat-stage").getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    return {
      dataLayout: host.shadowRoot.querySelector(".widget").dataset.layout,
      panelRole: panel.getAttribute("role"),
      panelModal: panel.getAttribute("aria-modal"),
      panelVisible: !panel.hidden,
      panelWidth: panelRect.width,
      separateColumns: intro.right < stage.left,
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: innerWidth,
    };
  });
  expect(layout).toMatchObject({
    dataLayout: "stage",
    panelRole: "region",
    panelModal: null,
    panelVisible: true,
    separateColumns: true,
  });
  expect(layout.panelWidth).toBeGreaterThanOrEqual(520);
  expect(layout.pageWidth).toBeLessThanOrEqual(layout.viewportWidth);

  const widget = page.locator("agent-chat-widget");
  await expect(widget.locator(".persona-contact")).toHaveCount(2);

  await widget.locator('.persona-contact[data-persona="professional"]').click();
  const input = widget.locator("textarea");
  await input.fill("专业问题");
  await input.press("Enter");
  await expect(page.getByText("这是专业人格回复。", { exact: true })).toBeVisible();
  await widget.locator(".back-button").click();

  await widget.locator('.persona-contact[data-persona="casual"]').click();
  await input.fill("闲聊问题");
  await input.press("Enter");
  await expect(page.getByText("这是闲聊人格回复。", { exact: true })).toBeVisible();

  expect(personaRequests.map((request) => request.persona_mode)).toEqual([
    "professional",
    "casual",
  ]);
  expect(personaRequests[0].history).toEqual([]);
  expect(personaRequests[1].history).toEqual([]);

  const stored = await page.evaluate(() =>
    JSON.parse(sessionStorage.getItem("agent-chat-widget:personas")),
  );
  expect(stored.version).toBe(1);
  expect(stored.conversations.professional.messages).toHaveLength(2);
  expect(stored.conversations.casual.messages).toHaveLength(2);
  expect(stored.conversations.professional.sessionId).not.toBe(
    stored.conversations.casual.sessionId,
  );

  await widget.locator(".back-button").click();
  await widget.locator('.persona-contact[data-persona="professional"]').click();
  await expect(page.getByText("专业问题", { exact: true })).toBeVisible();
  await expect(page.getByText("这是专业人格回复。", { exact: true })).toBeVisible();
  await expect(page.getByText("闲聊问题", { exact: true })).toHaveCount(0);

  await page.reload();
  await expect(page.getByText("专业问题", { exact: true })).toBeVisible();
  await widget.locator(".reset-button").click();
  await expect(page.getByText("专业问题", { exact: true })).toHaveCount(0);
  await widget.locator(".back-button").click();
  await widget.locator('.persona-contact[data-persona="casual"]').click();
  await expect(page.getByText("闲聊问题", { exact: true })).toBeVisible();
});

test("homepage rotates Chinese, English, and German greetings without overlap", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/index.html");
  const greeting = page.locator(".greeting-word");
  await expect(greeting).toHaveCount(1);
  await expect(greeting).toHaveText("你好");
  await expect(greeting).toHaveText("Hello", { timeout: 4500 });
  await expect(greeting).toHaveText("Hallo", { timeout: 4500 });

  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  await expect(greeting).toHaveText("你好");
  await page.waitForTimeout(3200);
  await expect(greeting).toHaveText("你好");
});

test("homepage and chat stay synchronized across manual and system theme changes", async ({ page }) => {
  await page.evaluate(() => sessionStorage.clear());
  await page.emulateMedia({ colorScheme: "dark" });
  await page.goto("/index.html");

  const widget = page.locator("#main-chat");
  const themeButton = widget.locator(".theme-button");
  const themeState = () => page.evaluate(() => {
    const host = document.querySelector("#main-chat");
    return {
      pageTheme: document.documentElement.dataset.theme,
      pagePreference: document.documentElement.dataset.themePreference,
      hostTheme: host.dataset.resolvedTheme,
      hostPreference: host.dataset.themePreference,
      chatTheme: host.shadowRoot.querySelector(".widget").dataset.theme,
      pageBackground: getComputedStyle(document.documentElement).backgroundColor,
    };
  });

  await expect.poll(themeState).toMatchObject({
    pageTheme: "dark",
    pagePreference: "auto",
    hostTheme: "dark",
    hostPreference: "auto",
    chatTheme: "dark",
    pageBackground: "rgb(0, 0, 0)",
  });

  await themeButton.click();
  await expect.poll(themeState).toMatchObject({
    pageTheme: "light",
    pagePreference: "light",
    hostTheme: "light",
    hostPreference: "light",
    chatTheme: "light",
    pageBackground: "rgb(245, 245, 247)",
  });

  await themeButton.click();
  await expect.poll(themeState).toMatchObject({
    pageTheme: "dark",
    pagePreference: "dark",
    hostTheme: "dark",
    hostPreference: "dark",
    chatTheme: "dark",
    pageBackground: "rgb(0, 0, 0)",
  });

  await themeButton.click();
  await expect.poll(themeState).toMatchObject({
    pageTheme: "dark",
    pagePreference: "auto",
    hostTheme: "dark",
    hostPreference: "auto",
    chatTheme: "dark",
  });

  await page.emulateMedia({ colorScheme: "light" });
  await expect.poll(themeState).toMatchObject({
    pageTheme: "light",
    pagePreference: "auto",
    hostTheme: "light",
    hostPreference: "auto",
    chatTheme: "light",
    pageBackground: "rgb(245, 245, 247)",
  });
});

test("chat-first homepage puts the chat before the introduction on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 360, height: 640 });
  await page.goto("/index.html");
  await finishHomepageAnimations(page);
  const mobile = await page.evaluate(() => {
    const host = document.querySelector("#main-chat");
    const panel = host.shadowRoot.querySelector(".panel").getBoundingClientRect();
    const intro = document.querySelector(".intro").getBoundingClientRect();
    const stage = document.querySelector(".chat-stage").getBoundingClientRect();
    return {
      chatBeforeIntro: stage.top < intro.top,
      panelLeft: panel.left,
      panelRight: panel.right,
      panelHeight: panel.height,
      personaContacts: host.shadowRoot.querySelectorAll(".persona-contact").length,
      viewportWidth: innerWidth,
      pageWidth: document.documentElement.scrollWidth,
    };
  });
  expect(mobile.chatBeforeIntro).toBe(true);
  expect(mobile.panelLeft).toBeGreaterThanOrEqual(0);
  expect(mobile.panelRight).toBeLessThanOrEqual(mobile.viewportWidth);
  expect(mobile.panelHeight).toBeGreaterThanOrEqual(540);
  expect(mobile.personaContacts).toBe(2);
  expect(mobile.pageWidth).toBeLessThanOrEqual(mobile.viewportWidth);
});

test("legacy sessionStorage migrates to version 3 and preserves safe messages", async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.removeItem("agent-chat-widget:session");
    sessionStorage.setItem(
      "agent-chat-session",
      JSON.stringify({
        sessionId: "b7f8d8dd-0dba-4f4c-b9aa-e21a7c48ad57",
        messages: [
          { role: "system", content: "must be dropped" },
          { role: "user", content: "legacy hello" },
          { role: "assistant", content: "legacy reply", status: "streaming" },
        ],
      }),
    );
  });
  await page.reload();
  await openWidget(page);
  await expect(page.getByText("legacy hello")).toBeVisible();
  await expect(page.getByText("legacy reply")).toBeVisible();
  await expect(page.getByText("Generation stopped.")).toBeVisible();
  const stored = await page.evaluate(() => JSON.parse(sessionStorage.getItem("agent-chat-widget:session")));
  expect(stored.version).toBe(3);
  expect(stored.sessionId).toBe("b7f8d8dd-0dba-4f4c-b9aa-e21a7c48ad57");
  expect(stored.messages.map((message) => message.role)).toEqual(["user", "assistant"]);
  expect(await page.evaluate(() => sessionStorage.getItem("agent-chat-session"))).toBeNull();
});

test("German locale, dark theme, keyboard focus, ARIA, and reduced motion are supported", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await openWidget(page);
  await expect(page.getByRole("textbox", { name: "Ask me anything…" })).toBeFocused();
  await page.getByRole("combobox", { name: "Interface language" }).selectOption("de");
  const input = page.getByRole("textbox", { name: "Frag mich etwas…" });
  await expect(input).toBeVisible();
  await input.fill("Zeile eins");
  await input.press("Shift+Enter");
  await input.type("Zeile zwei");
  await expect(input).toHaveValue("Zeile eins\nZeile zwei");
  await page.getByRole("button", { name: /Farbschema wechseln/ }).click();
  const state = await page.evaluate(() => {
    const root = document.querySelector("agent-chat-widget").shadowRoot;
    const panel = root.querySelector(".panel");
    return {
      theme: root.querySelector(".widget").dataset.theme,
      role: panel.getAttribute("role"),
      modal: panel.getAttribute("aria-modal"),
      controls: root.querySelector(".launcher").getAttribute("aria-controls"),
      live: root.querySelector(".live-region").getAttribute("aria-live"),
      transition: getComputedStyle(panel).transitionDuration,
      animation: getComputedStyle(panel).animationDuration,
    };
  });
  expect(state.theme).toBe("dark");
  expect(state.role).toBe("dialog");
  expect(state.modal).toBe("true");
  expect(state.controls).toBe("agent-chat-panel");
  expect(state.live).toBe("polite");
  expect(parseFloat(state.transition)).toBeLessThanOrEqual(0.01);
  expect(parseFloat(state.animation)).toBeLessThanOrEqual(0.01);

  await page.getByRole("button", { name: "Lokale Sitzung zurücksetzen" }).focus();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("combobox", { name: "Oberflächensprache" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("button", { name: "Mit meinem KI-Zwilling chatten" })).toBeFocused();
});

for (const viewport of [
  { name: "mobile-360x640", width: 360, height: 640 },
  { name: "tablet-768x1024", width: 768, height: 1024 },
  { name: "desktop-1440x900", width: 1440, height: 900 },
]) {
  test(`${viewport.name} has no horizontal overflow and keeps the dialog in view`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.reload();
    await openWidget(page);
    const geometry = await page.evaluate(() => {
      const root = document.querySelector("agent-chat-widget").shadowRoot;
      const rect = root.querySelector(".panel").getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
        viewportWidth: innerWidth,
        viewportHeight: innerHeight,
        pageWidth: document.documentElement.scrollWidth,
      };
    });
    expect(geometry.left).toBeGreaterThanOrEqual(0);
    expect(geometry.top).toBeGreaterThanOrEqual(0);
    expect(geometry.right).toBeLessThanOrEqual(geometry.viewportWidth);
    expect(geometry.bottom).toBeLessThanOrEqual(geometry.viewportHeight);
    expect(geometry.pageWidth).toBeLessThanOrEqual(geometry.viewportWidth);
  });
}
