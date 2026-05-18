# Little Lion Phase 1b — PWA Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a static PWA (Vanilla TypeScript) served by the Phase 1a backend that lets the user — from desktop *and* iPhone Safari — chat with the assistant via typed text and Push-to-Talk audio, see the answer + a 4-line trace summary, and have it persist as a Home Screen app.

**Architecture:** Single-page client, two screens (`/` chat, `/settings`). Bearer token stored in `localStorage`. REST POST `/chat` for text turns. WebSocket `/ws/voice` for audio turns (MediaRecorder → backend STT → same pipeline). Service worker caches the app shell. Backend (FastAPI) serves `frontend/dist/` as static assets at root path.

**Tech Stack:**
- Vite 5
- TypeScript 5.4+
- `vite-plugin-pwa` (manifest + workbox SW)
- `marked` (markdown → HTML) + `dompurify` (sanitize)
- `vitest` + `@testing-library/dom` + `jsdom` (unit tests for non-DOM logic)
- No UI framework (vanilla DOM classes)

**Reference docs:**
- `docs/specs/2026-05-18-little-lion-personal-assistant-design.md`
- `docs/specs/2026-05-18-little-lion-design-deep-dive.md` (§5 trace UX is the source of truth for trace panel behavior)
- `docs/specs/2026-05-18-little-lion-phase1a-backend-plan.md` (API contract: `POST /chat` ChatResponse + `WS /ws/voice`)

**Prerequisite:** Phase 1a backend complete. The backend's `ChatResponse` schema is the contract this plan implements against — do not modify it from this plan.

**Working directory:** All commands assume CWD `/Users/seongwookjang/project/git/violet_sw/015_little_lion/`.

---

## Task 1: Frontend scaffolding (Vite + TS)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/.gitignore`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "little-lion-frontend",
  "version": "0.0.1",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "lint": "tsc --noEmit"
  },
  "devDependencies": {
    "@testing-library/dom": "^10.0.0",
    "@types/dompurify": "^3.0.5",
    "@types/marked": "^6.0.0",
    "jsdom": "^24.0.0",
    "typescript": "^5.4.0",
    "vite": "^5.2.0",
    "vite-plugin-pwa": "^0.20.0",
    "vitest": "^1.6.0"
  },
  "dependencies": {
    "dompurify": "^3.1.0",
    "marked": "^12.0.0"
  }
}
```

- [ ] **Step 2: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2022", "DOM", "DOM.Iterable", "WebWorker"],
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "preserve",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vite/client", "vite-plugin-pwa/client", "vitest/globals"]
  },
  "include": ["src", "vite.config.ts"]
}
```

- [ ] **Step 3: Create `frontend/vite.config.ts`** (PWA + dev proxy to backend)

```typescript
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  root: ".",
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  server: {
    port: 5173,
    proxy: {
      "/chat":     { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/healthz":  { target: "http://127.0.0.1:8765", changeOrigin: true },
      "/ws/voice": { target: "ws://127.0.0.1:8765",   ws: true, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.ts"],
  },
  plugins: [
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg"],
      manifest: {
        name: "Little Lion",
        short_name: "LittleLion",
        description: "Personal AI assistant",
        theme_color: "#1a1a1a",
        background_color: "#0d0d0d",
        display: "standalone",
        scope: "/",
        start_url: "/",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
      workbox: {
        navigateFallback: "/index.html",
        runtimeCaching: [
          {
            // Never cache API calls
            urlPattern: /\/(chat|ws|healthz)/,
            handler: "NetworkOnly",
          },
        ],
      },
    }),
  ],
});
```

- [ ] **Step 4: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="ko">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#1a1a1a" />
    <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
    <title>Little Lion</title>
    <link rel="stylesheet" href="/src/styles.css" />
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 5: Create `frontend/src/main.ts`** (placeholder mount point)

```typescript
import "./styles.css";

const root = document.querySelector<HTMLDivElement>("#app");
if (root) {
  root.innerHTML = `
    <main class="app-shell">
      <h1>Little Lion</h1>
      <p>Frontend scaffold ready. Tasks 2+ wire up the rest.</p>
    </main>
  `;
}
```

- [ ] **Step 6: Create `frontend/src/styles.css`** (minimal base)

```css
* { box-sizing: border-box; }
:root {
  color-scheme: dark;
  --bg: #0d0d0d;
  --fg: #f0f0f0;
  --accent: #8b9eff;
  --muted: #888;
  --border: #2a2a2a;
  --card: #1a1a1a;
  font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Helvetica Neue", sans-serif;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  min-height: 100vh;
  min-height: 100svh;
}
.app-shell {
  max-width: 720px;
  margin: 0 auto;
  padding: env(safe-area-inset-top, 16px) 16px env(safe-area-inset-bottom, 16px);
}
```

- [ ] **Step 7: Create `frontend/.gitignore`**

```gitignore
node_modules/
dist/
dev-dist/
*.log
.vite/
```

- [ ] **Step 8: Install + verify build**

Run:
```bash
cd frontend
npm install
npm run build
```
Expected: `dist/index.html`, `dist/assets/*`, `dist/manifest.webmanifest`, `dist/sw.js` exist.

- [ ] **Step 9: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json \
        frontend/vite.config.ts frontend/index.html frontend/.gitignore \
        frontend/src/main.ts frontend/src/styles.css
git commit -m "Scaffold PWA: Vite + TS + vite-plugin-pwa + dev proxy to backend"
```

---

## Task 2: Token storage + Settings UI

**Files:**
- Create: `frontend/src/lib/auth.ts`
- Create: `frontend/src/lib/auth.test.ts`
- Create: `frontend/src/components/settings.ts`

- [ ] **Step 1: Write failing auth tests**

```typescript
// frontend/src/lib/auth.test.ts
import { beforeEach, describe, expect, it } from "vitest";
import { clearToken, getToken, hasToken, setToken } from "./auth";

describe("auth token storage", () => {
  beforeEach(() => localStorage.clear());

  it("returns null when no token stored", () => {
    expect(getToken()).toBeNull();
    expect(hasToken()).toBe(false);
  });

  it("round-trips a token", () => {
    setToken("abc-123");
    expect(getToken()).toBe("abc-123");
    expect(hasToken()).toBe(true);
  });

  it("clears a token", () => {
    setToken("x");
    clearToken();
    expect(getToken()).toBeNull();
  });

  it("rejects empty token in setToken", () => {
    expect(() => setToken("")).toThrow();
    expect(() => setToken("   ")).toThrow();
  });
});
```

- [ ] **Step 2: Run to fail**

Run: `cd frontend && npx vitest run src/lib/auth.test.ts`
Expected: Module not found `./auth`.

- [ ] **Step 3: Implement `frontend/src/lib/auth.ts`**

```typescript
const KEY = "little-lion:token";

export function getToken(): string | null {
  return localStorage.getItem(KEY);
}

export function hasToken(): boolean {
  return getToken() !== null;
}

export function setToken(token: string): void {
  const trimmed = token.trim();
  if (!trimmed) throw new Error("token cannot be empty");
  localStorage.setItem(KEY, trimmed);
}

export function clearToken(): void {
  localStorage.removeItem(KEY);
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/lib/auth.test.ts`
Expected: 4 passed.

- [ ] **Step 5: Implement `frontend/src/components/settings.ts`**

```typescript
import { clearToken, getToken, setToken } from "../lib/auth";

export function renderSettings(target: HTMLElement, onSaved: () => void): void {
  const current = getToken() ?? "";
  target.innerHTML = `
    <section class="settings">
      <h2>Settings</h2>
      <label class="field">
        <span>Backend auth token</span>
        <input id="token-input" type="password" placeholder="Bearer token" value="${escape(current)}" />
      </label>
      <div class="actions">
        <button id="save-btn">Save</button>
        <button id="clear-btn" class="ghost">Clear</button>
      </div>
      <p class="hint">Get the token from the backend host's <code>.env</code> (BACKEND_AUTH_TOKEN).</p>
      <p id="msg" class="msg" role="status"></p>
    </section>
  `;
  const input = target.querySelector<HTMLInputElement>("#token-input")!;
  const save = target.querySelector<HTMLButtonElement>("#save-btn")!;
  const clear = target.querySelector<HTMLButtonElement>("#clear-btn")!;
  const msg = target.querySelector<HTMLParagraphElement>("#msg")!;

  save.addEventListener("click", () => {
    try {
      setToken(input.value);
      msg.textContent = "Saved.";
      msg.className = "msg ok";
      onSaved();
    } catch (e) {
      msg.textContent = (e as Error).message;
      msg.className = "msg err";
    }
  });
  clear.addEventListener("click", () => {
    clearToken();
    input.value = "";
    msg.textContent = "Cleared.";
    msg.className = "msg ok";
  });
}

function escape(s: string): string {
  return s.replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]!));
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/auth.ts frontend/src/lib/auth.test.ts frontend/src/components/settings.ts
git commit -m "Add token storage (localStorage) + Settings panel UI"
```

---

## Task 3: REST API client (`POST /chat`)

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/api.test.ts`
- Create: `frontend/src/lib/types.ts`

- [ ] **Step 1: Define API contract types in `frontend/src/lib/types.ts`**

```typescript
export interface ChatRequest {
  text: string;
}

export interface RouterTrace {
  stage1_rule: Record<string, unknown> | null;
  stage2_classifier: Record<string, unknown> | null;
  stage3_scorer: {
    chosen: string;
    provider: string;
    score: number;
    candidates: Record<string, number>;
    reason: string;
  };
  decided_at_stage: number;
}

export interface DecisionTrace {
  session_id: string;
  stt: Record<string, unknown>;
  router: RouterTrace;
  policy: { offline_mode: boolean; provider: string; action: string; redacted_paths: string[] };
  rag: { query_embedding_ms: number; search_ms: number; hits: Array<{ path: string; score: number }>; passed_threshold: number; used_in_prompt: number };
  llm: { provider: string; model: string; input_tokens: number; output_tokens: number; duration_ms: number; stop_reason: string };
  atom_extraction: { model: string; extracted: Record<string, unknown> | null; skipped: boolean };
  cross_link: { candidates_count: number; passed_threshold: number; llm_picked: number; linked: string[] };
  vault_writes: string[];
  total_duration_ms: number;
}

export interface ChatResponse {
  answer: string;
  route_reason: string;
  atom_slug: string | null;
  session_id: string;
  trace: DecisionTrace;
}

export interface VoiceWSResponse extends ChatResponse {
  transcript: string;
  lang: string;
}
```

- [ ] **Step 2: Write failing API client tests**

```typescript
// frontend/src/lib/api.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, postChat } from "./api";
import { setToken } from "./auth";

describe("postChat", () => {
  beforeEach(() => {
    localStorage.clear();
    setToken("test-token");
  });
  afterEach(() => vi.restoreAllMocks());

  it("sends bearer token + json body", async () => {
    const spy = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(
      JSON.stringify({
        answer: "ok", route_reason: "stage1", atom_slug: null, session_id: "sid",
        trace: { session_id: "sid", router: { decided_at_stage: 1 } } as any,
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    ));
    const out = await postChat({ text: "hi" });
    expect(out.answer).toBe("ok");
    const call = spy.mock.calls[0]!;
    expect(call[0]).toBe("/chat");
    const init = call[1]!;
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer test-token");
    expect(init.body).toBe(JSON.stringify({ text: "hi" }));
  });

  it("throws ApiError(401) without token", async () => {
    localStorage.clear();
    await expect(postChat({ text: "hi" })).rejects.toThrow(ApiError);
  });

  it("throws ApiError on non-2xx", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("nope", { status: 500 }));
    await expect(postChat({ text: "hi" })).rejects.toMatchObject({ status: 500 });
  });
});
```

- [ ] **Step 3: Run to fail**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: Module not found `./api`.

- [ ] **Step 4: Implement `frontend/src/lib/api.ts`**

```typescript
import { getToken } from "./auth";
import type { ChatRequest, ChatResponse } from "./types";

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

export async function postChat(req: ChatRequest): Promise<ChatResponse> {
  const token = getToken();
  if (!token) throw new ApiError(401, "no token configured — open Settings");
  const r = await fetch("/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(req),
  });
  if (!r.ok) {
    const body = await r.text();
    throw new ApiError(r.status, body || r.statusText);
  }
  return (await r.json()) as ChatResponse;
}
```

- [ ] **Step 5: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/lib/api.test.ts`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/api.test.ts frontend/src/lib/types.ts
git commit -m "Add REST API client (postChat) with bearer auth + typed ChatResponse"
```

---

## Task 4: WebSocket voice client

**Files:**
- Create: `frontend/src/lib/voice.ts`
- Create: `frontend/src/lib/voice.test.ts`

- [ ] **Step 1: Write failing voice client tests** (WebSocket mocked)

```typescript
// frontend/src/lib/voice.test.ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setToken } from "./auth";
import { VoiceSession } from "./voice";

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];
  readyState = 0;
  onopen: ((this: WebSocket, ev: Event) => unknown) | null = null;
  onmessage: ((this: WebSocket, ev: MessageEvent) => unknown) | null = null;
  onerror: ((this: WebSocket, ev: Event) => unknown) | null = null;
  onclose: ((this: WebSocket, ev: CloseEvent) => unknown) | null = null;
  sent: Array<string | ArrayBuffer | Blob> = [];
  constructor(public url: string) {
    MockWebSocket.instances.push(this);
    queueMicrotask(() => {
      this.readyState = MockWebSocket.OPEN;
      this.onopen?.call(this as unknown as WebSocket, new Event("open"));
    });
  }
  send(data: string | ArrayBuffer | Blob) { this.sent.push(data); }
  close() { this.readyState = 3; }
}

describe("VoiceSession", () => {
  beforeEach(() => {
    localStorage.clear();
    setToken("test-token");
    MockWebSocket.instances = [];
    (globalThis as any).WebSocket = MockWebSocket;
  });

  it("opens with token in query string", async () => {
    const s = new VoiceSession();
    await s.connect();
    expect(MockWebSocket.instances[0].url).toContain("token=test-token");
    expect(MockWebSocket.instances[0].url).toMatch(/\/ws\/voice/);
  });

  it("sendAudioChunk forwards binary", async () => {
    const s = new VoiceSession();
    await s.connect();
    const chunk = new Uint8Array([1, 2, 3]).buffer;
    s.sendAudioChunk(chunk);
    expect(MockWebSocket.instances[0].sent).toContain(chunk);
  });

  it("end() sends sentinel + resolves with server response", async () => {
    const s = new VoiceSession();
    await s.connect();
    const done = s.end();
    // simulate server response
    const ws = MockWebSocket.instances[0];
    ws.onmessage?.call(ws as unknown as WebSocket, new MessageEvent("message", {
      data: JSON.stringify({ answer: "ok", transcript: "안녕", lang: "ko",
        route_reason: "rule:default", atom_slug: null, session_id: "sid",
        trace: { session_id: "sid" } }),
    }));
    const out = await done;
    expect(out.transcript).toBe("안녕");
    expect(out.answer).toBe("ok");
    expect(ws.sent).toContain("__END__");
  });
});
```

- [ ] **Step 2: Run to fail**

Run: `cd frontend && npx vitest run src/lib/voice.test.ts`
Expected: Module not found `./voice`.

- [ ] **Step 3: Implement `frontend/src/lib/voice.ts`**

```typescript
import { getToken } from "./auth";
import type { VoiceWSResponse } from "./types";

export class VoiceSession {
  private ws: WebSocket | null = null;
  private pending: Promise<VoiceWSResponse> | null = null;

  async connect(): Promise<void> {
    const token = getToken();
    if (!token) throw new Error("no token configured");
    const url = wsUrl(`/ws/voice?token=${encodeURIComponent(token)}`);
    return new Promise((resolve, reject) => {
      const ws = new WebSocket(url);
      ws.onopen = () => resolve();
      ws.onerror = (e) => reject(e);
      this.ws = ws;
    });
  }

  sendAudioChunk(chunk: ArrayBuffer): void {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(chunk);
  }

  end(): Promise<VoiceWSResponse> {
    if (!this.ws) return Promise.reject(new Error("not connected"));
    if (this.pending) return this.pending;
    this.pending = new Promise((resolve, reject) => {
      const ws = this.ws!;
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string) as VoiceWSResponse;
          resolve(data);
        } catch (e) {
          reject(e);
        } finally {
          ws.close();
          this.ws = null;
        }
      };
      ws.onerror = (e) => reject(e);
      ws.send("__END__");
    });
    return this.pending;
  }
}

function wsUrl(path: string): string {
  // In dev, vite proxies /ws → ws://localhost:8765/ws — relative URL is enough.
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}${path}`;
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/lib/voice.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/voice.ts frontend/src/lib/voice.test.ts
git commit -m "Add VoiceSession WS client (connect/sendAudioChunk/end)"
```

---

## Task 5: Markdown rendering (marked + DOMPurify)

**Files:**
- Create: `frontend/src/lib/markdown.ts`
- Create: `frontend/src/lib/markdown.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// frontend/src/lib/markdown.test.ts
import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("renders bold + lists", () => {
    const html = renderMarkdown("**bold**\n- one\n- two");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<li>one</li>");
  });

  it("strips script tags (XSS guard)", () => {
    const html = renderMarkdown("<script>alert(1)</script> hello");
    expect(html).not.toContain("<script");
    expect(html).toContain("hello");
  });

  it("renders fenced code", () => {
    const html = renderMarkdown("```\nx = 1\n```");
    expect(html).toContain("<pre>");
    expect(html).toContain("x = 1");
  });
});
```

- [ ] **Step 2: Run to fail**

Run: `cd frontend && npx vitest run src/lib/markdown.test.ts`
Expected: Module not found `./markdown`.

- [ ] **Step 3: Implement `frontend/src/lib/markdown.ts`**

```typescript
import DOMPurify from "dompurify";
import { marked } from "marked";

marked.setOptions({ breaks: true, gfm: true });

export function renderMarkdown(src: string): string {
  const html = marked.parse(src, { async: false }) as string;
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: ["a", "p", "br", "strong", "em", "code", "pre", "ul", "ol", "li",
                    "blockquote", "h1", "h2", "h3", "h4", "hr", "table", "thead",
                    "tbody", "tr", "th", "td", "span"],
    ALLOWED_ATTR: ["href", "title", "target", "rel", "class"],
  });
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/lib/markdown.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/markdown.ts frontend/src/lib/markdown.test.ts
git commit -m "Add renderMarkdown (marked + DOMPurify) with XSS guard"
```

---

## Task 6: Trace panel component

**Files:**
- Create: `frontend/src/components/trace-panel.ts`
- Create: `frontend/src/components/trace-panel.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// frontend/src/components/trace-panel.test.ts
import { describe, expect, it } from "vitest";
import type { DecisionTrace } from "../lib/types";
import { renderTracePanel, summarizeTrace } from "./trace-panel";

const sample: DecisionTrace = {
  session_id: "sid",
  stt: { duration_ms: 320 },
  router: {
    stage1_rule: null,
    stage2_classifier: { category: "rag", confidence: 0.78 },
    stage3_scorer: { chosen: "qwen2.5:14b", provider: "ollama", score: 8.4, candidates: { "qwen2.5:14b": 8.4 }, reason: "stage2:rag" },
    decided_at_stage: 3,
  },
  policy: { offline_mode: false, provider: "ollama", action: "allow", redacted_paths: [] },
  rag: { query_embedding_ms: 42, search_ms: 18, hits: [{ path: "atoms/a.md", score: 0.82 }], passed_threshold: 1, used_in_prompt: 1 },
  llm: { provider: "ollama", model: "qwen2.5:14b", input_tokens: 1234, output_tokens: 312, duration_ms: 4200, stop_reason: "" },
  atom_extraction: { model: "qwen2.5:14b", extracted: { title: "X" }, skipped: false },
  cross_link: { candidates_count: 18, passed_threshold: 9, llm_picked: 4, linked: ["a", "b", "c", "d"] },
  vault_writes: ["atoms/x.md"],
  total_duration_ms: 4881,
};

describe("summarizeTrace", () => {
  it("includes route, rag, latency, atom counts", () => {
    const s = summarizeTrace(sample);
    expect(s).toContain("qwen2.5:14b");
    expect(s).toContain("atoms/a.md");
    expect(s).toMatch(/4\.9 ?s|4881/);   // total latency rendered either way
    expect(s).toContain("4");             // cross-linked count
  });
});

describe("renderTracePanel", () => {
  it("mounts a collapsible panel with 4-line summary", () => {
    const target = document.createElement("div");
    renderTracePanel(target, sample);
    expect(target.innerHTML).toContain("Why this answer?");
    expect(target.innerHTML).toContain("qwen2.5:14b");
    const details = target.querySelector("details");
    expect(details).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run to fail**

Run: `cd frontend && npx vitest run src/components/trace-panel.test.ts`
Expected: Module not found.

- [ ] **Step 3: Implement `frontend/src/components/trace-panel.ts`**

```typescript
import type { DecisionTrace } from "../lib/types";

export function summarizeTrace(t: DecisionTrace): string {
  const route = `${t.router.stage3_scorer.provider}/${t.router.stage3_scorer.chosen} (stage ${t.router.decided_at_stage}, score ${t.router.stage3_scorer.score})`;
  const ragHits = t.rag.hits.length;
  const ragUsed = t.rag.used_in_prompt;
  const ragLine = ragHits === 0
    ? "RAG     : none"
    : `RAG     : ${ragHits} hits, ${ragUsed} used (${t.rag.hits[0].path}, score ${t.rag.hits[0].score})`;
  const ms = t.total_duration_ms;
  const sec = (ms / 1000).toFixed(1);
  const latency = `Latency : ${sec}s total (stt ${t.stt.duration_ms ?? "?"}ms · llm ${t.llm.duration_ms}ms)`;
  const atomsLine = t.atom_extraction.skipped
    ? "Atoms   : none extracted"
    : `Atoms   : 1 new, ${t.cross_link.linked.length} cross-linked`;
  return [
    `• Route   : ${route}`,
    `• ${ragLine}`,
    `• ${latency}`,
    `• ${atomsLine}`,
  ].join("\n");
}

export function renderTracePanel(target: HTMLElement, trace: DecisionTrace): void {
  const summary = summarizeTrace(trace);
  const full = JSON.stringify(trace, null, 2);
  target.innerHTML = `
    <details class="trace">
      <summary>Why this answer?</summary>
      <pre class="trace-summary">${escape(summary)}</pre>
      <details class="trace-full">
        <summary>Show full trace</summary>
        <pre class="trace-json">${escape(full)}</pre>
      </details>
    </details>
  `;
}

function escape(s: string): string {
  return s.replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]!));
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/components/trace-panel.test.ts`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/trace-panel.ts frontend/src/components/trace-panel.test.ts
git commit -m "Add trace panel (4-line summary + full JSON) per deep-dive §5"
```

---

## Task 7: Chat container + message list

**Files:**
- Create: `frontend/src/components/chat.ts`
- Create: `frontend/src/components/chat.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// frontend/src/components/chat.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../lib/api";
import { setToken } from "../lib/auth";
import { renderChat } from "./chat";

describe("renderChat", () => {
  beforeEach(() => {
    localStorage.clear();
    setToken("t");
    document.body.innerHTML = '<div id="app"></div>';
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders the input field + send button", () => {
    const root = document.getElementById("app")!;
    renderChat(root);
    expect(root.querySelector("textarea")).toBeTruthy();
    expect(root.querySelector("#send-btn")).toBeTruthy();
  });

  it("submitting text shows assistant reply", async () => {
    vi.spyOn(api, "postChat").mockResolvedValue({
      answer: "**hi**",
      route_reason: "stage1",
      atom_slug: "x",
      session_id: "sid",
      trace: { session_id: "sid", router: { decided_at_stage: 1, stage3_scorer: { chosen: "qwen2.5:14b", provider: "ollama", score: 8, candidates: {}, reason: "" }, stage1_rule: null, stage2_classifier: null }, policy: {} as any, rag: { hits: [], used_in_prompt: 0, passed_threshold: 0, query_embedding_ms: 0, search_ms: 0 }, llm: {} as any, atom_extraction: { skipped: true } as any, cross_link: { linked: [] } as any, vault_writes: [], stt: {}, total_duration_ms: 100 } as any,
    });
    const root = document.getElementById("app")!;
    renderChat(root);
    const textarea = root.querySelector<HTMLTextAreaElement>("textarea")!;
    textarea.value = "안녕";
    root.querySelector<HTMLButtonElement>("#send-btn")!.click();
    // wait microtasks
    await new Promise(r => setTimeout(r, 10));
    const messages = root.querySelectorAll(".message");
    expect(messages.length).toBeGreaterThanOrEqual(2);  // user + assistant
    expect(root.innerHTML).toContain("<strong>hi</strong>");  // markdown rendered
  });
});
```

- [ ] **Step 2: Run to fail**

Run: `cd frontend && npx vitest run src/components/chat.test.ts`
Expected: Module not found `./chat`.

- [ ] **Step 3: Implement `frontend/src/components/chat.ts`**

```typescript
import { ApiError, postChat } from "../lib/api";
import { hasToken } from "../lib/auth";
import { renderMarkdown } from "../lib/markdown";
import type { ChatResponse } from "../lib/types";
import { renderTracePanel } from "./trace-panel";

interface UITurn {
  who: "user" | "assistant";
  text: string;
  response?: ChatResponse;
}

const turns: UITurn[] = [];

export function renderChat(root: HTMLElement): void {
  root.innerHTML = `
    <main class="app-shell">
      <header class="topbar">
        <h1>Little Lion</h1>
        <a href="#/settings" class="ghost">Settings</a>
      </header>
      <div id="messages" class="messages"></div>
      <form id="composer" class="composer">
        <textarea id="text" rows="2" placeholder="질문을 입력하거나 마이크를 길게 눌러 말해..."></textarea>
        <div class="composer-buttons">
          <button id="mic-btn" type="button" class="mic" aria-label="Push to talk">🎙️</button>
          <button id="send-btn" type="submit">Send</button>
        </div>
        <p id="status" class="status" role="status"></p>
      </form>
    </main>
  `;
  const messages = root.querySelector<HTMLDivElement>("#messages")!;
  const text = root.querySelector<HTMLTextAreaElement>("#text")!;
  const form = root.querySelector<HTMLFormElement>("#composer")!;
  const status = root.querySelector<HTMLParagraphElement>("#status")!;

  redraw(messages);

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const value = text.value.trim();
    if (!value) return;
    if (!hasToken()) {
      status.textContent = "Set the auth token in Settings first.";
      return;
    }
    text.value = "";
    turns.push({ who: "user", text: value });
    redraw(messages);
    status.textContent = "Thinking...";
    try {
      const resp = await postChat({ text: value });
      turns.push({ who: "assistant", text: resp.answer, response: resp });
      status.textContent = "";
    } catch (err) {
      const e = err as ApiError;
      status.textContent = `Error ${e.status}: ${e.message}`;
    }
    redraw(messages);
  });
}

function redraw(target: HTMLElement): void {
  target.innerHTML = "";
  for (const t of turns) {
    const card = document.createElement("article");
    card.className = `message ${t.who}`;
    if (t.who === "user") {
      card.innerHTML = `<div class="body">${escape(t.text)}</div>`;
    } else {
      card.innerHTML = `<div class="body markdown">${renderMarkdown(t.text)}</div>`;
      if (t.response?.atom_slug) {
        const meta = document.createElement("p");
        meta.className = "atom-link";
        meta.textContent = `→ atom: ${t.response.atom_slug}`;
        card.appendChild(meta);
      }
      if (t.response?.trace) {
        const tp = document.createElement("div");
        renderTracePanel(tp, t.response.trace);
        card.appendChild(tp.firstElementChild!);
      }
    }
    target.appendChild(card);
  }
  target.scrollTop = target.scrollHeight;
}

function escape(s: string): string {
  return s.replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]!));
}
```

- [ ] **Step 4: Run tests, verify pass**

Run: `cd frontend && npx vitest run src/components/chat.test.ts`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat.ts frontend/src/components/chat.test.ts
git commit -m "Add chat component (composer + message list + trace panel embed)"
```

---

## Task 8: Microphone Push-to-Talk wiring

**Files:**
- Modify: `frontend/src/components/chat.ts:1-200`
- Create: `frontend/src/lib/mic.ts`
- Create: `frontend/src/lib/mic.test.ts`

This task adds microphone Push-to-Talk support. The mic button (already rendered in Task 7) becomes active.

- [ ] **Step 1: Write failing mic tests**

```typescript
// frontend/src/lib/mic.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MicRecorder } from "./mic";

class FakeRecorder {
  static instances: FakeRecorder[] = [];
  state = "inactive";
  ondataavailable: ((ev: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(public stream: MediaStream, public _opts: unknown) {
    FakeRecorder.instances.push(this);
  }
  start(_ms: number) { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob([new Uint8Array([1, 2, 3])]) });
    this.onstop?.();
  }
}

beforeEach(() => {
  FakeRecorder.instances = [];
  (globalThis as any).MediaRecorder = FakeRecorder;
  (globalThis as any).navigator.mediaDevices = {
    getUserMedia: vi.fn().mockResolvedValue({ getTracks: () => [{ stop: vi.fn() }] }),
  };
});
afterEach(() => vi.restoreAllMocks());

describe("MicRecorder", () => {
  it("start() requests microphone permission", async () => {
    const m = new MicRecorder();
    await m.start();
    expect((navigator.mediaDevices.getUserMedia as any)).toHaveBeenCalled();
    expect(FakeRecorder.instances[0].state).toBe("recording");
  });

  it("stop() returns concatenated blob via onChunk", async () => {
    const chunks: Blob[] = [];
    const m = new MicRecorder({ onChunk: (b) => chunks.push(b) });
    await m.start();
    await m.stop();
    expect(chunks.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run to fail**

Run: `cd frontend && npx vitest run src/lib/mic.test.ts`
Expected: Module not found.

- [ ] **Step 3: Implement `frontend/src/lib/mic.ts`**

```typescript
export interface MicOptions {
  onChunk?: (blob: Blob) => void;
  mimeType?: string;
}

export class MicRecorder {
  private rec: MediaRecorder | null = null;
  private stream: MediaStream | null = null;
  private chunks: Blob[] = [];
  constructor(private readonly opts: MicOptions = {}) {}

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mt = this.opts.mimeType ?? pickMimeType();
    this.rec = new MediaRecorder(this.stream, { mimeType: mt });
    this.chunks = [];
    this.rec.ondataavailable = (ev) => {
      if (ev.data && ev.data.size > 0) {
        this.chunks.push(ev.data);
        this.opts.onChunk?.(ev.data);
      }
    };
    this.rec.start(250);  // emit every 250ms
  }

  async stop(): Promise<Blob> {
    return new Promise((resolve) => {
      if (!this.rec) return resolve(new Blob([]));
      this.rec.onstop = () => {
        const blob = new Blob(this.chunks, { type: this.rec!.mimeType });
        this.stream?.getTracks().forEach((t) => t.stop());
        this.rec = null;
        this.stream = null;
        resolve(blob);
      };
      this.rec.stop();
    });
  }
}

function pickMimeType(): string {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  for (const c of candidates) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported?.(c)) return c;
  }
  return "audio/webm";
}
```

- [ ] **Step 4: Run mic tests, verify pass**

Run: `cd frontend && npx vitest run src/lib/mic.test.ts`
Expected: 2 passed.

- [ ] **Step 5: Wire PTT into `frontend/src/components/chat.ts`**

Add to the bottom of `renderChat`, before the final `function redraw`:

```typescript
  // ─── Push-to-Talk wiring ────────────────────────────────────────────────
  const micBtn = root.querySelector<HTMLButtonElement>("#mic-btn")!;
  let active: { recorder: MicRecorder; session: VoiceSession } | null = null;

  const startPTT = async () => {
    if (active) return;
    if (!hasToken()) { status.textContent = "Set token first."; return; }
    try {
      const session = new VoiceSession();
      await session.connect();
      const recorder = new MicRecorder({
        onChunk: (blob) => blob.arrayBuffer().then((buf) => session.sendAudioChunk(buf)),
      });
      await recorder.start();
      micBtn.classList.add("recording");
      status.textContent = "Listening...";
      active = { recorder, session };
    } catch (err) {
      status.textContent = `Mic error: ${(err as Error).message}`;
    }
  };

  const stopPTT = async () => {
    if (!active) return;
    const { recorder, session } = active;
    active = null;
    micBtn.classList.remove("recording");
    status.textContent = "Transcribing...";
    try {
      await recorder.stop();
      const resp = await session.end();
      turns.push({ who: "user", text: resp.transcript });
      turns.push({ who: "assistant", text: resp.answer, response: resp });
      status.textContent = "";
    } catch (err) {
      status.textContent = `Voice error: ${(err as Error).message}`;
    }
    redraw(messages);
  };

  micBtn.addEventListener("pointerdown", startPTT);
  micBtn.addEventListener("pointerup", stopPTT);
  micBtn.addEventListener("pointercancel", stopPTT);
  micBtn.addEventListener("pointerleave", () => { if (active) stopPTT(); });
```

Add imports at top of `chat.ts`:

```typescript
import { MicRecorder } from "../lib/mic";
import { VoiceSession } from "../lib/voice";
```

- [ ] **Step 6: Run all tests, verify pass**

Run: `cd frontend && npx vitest run`
Expected: all existing tests still pass (chat tests didn't exercise PTT).

- [ ] **Step 7: Manual smoke test (browser)**

```bash
# Terminal 1: backend
cd /Users/seongwookjang/project/git/violet_sw/015_little_lion
./scripts/run_dev.sh

# Terminal 2: frontend dev
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`, go to Settings → paste BACKEND_AUTH_TOKEN → return to chat → hold mic button → speak "오늘 날씨" → release. Expected: transcript appears as user message, assistant replies, atom is written to vault.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/mic.ts frontend/src/lib/mic.test.ts frontend/src/components/chat.ts
git commit -m "Wire Push-to-Talk: MicRecorder → VoiceSession → /ws/voice"
```

---

## Task 9: App shell + hash routing + entry point

**Files:**
- Modify: `frontend/src/main.ts`
- Create: `frontend/src/router.ts`

- [ ] **Step 1: Implement `frontend/src/router.ts`**

```typescript
import { renderChat } from "./components/chat";
import { renderSettings } from "./components/settings";

export function mount(root: HTMLElement): void {
  const route = () => {
    const hash = location.hash.replace(/^#/, "") || "/";
    if (hash === "/settings") {
      renderSettings(root, () => { location.hash = "/"; });
    } else {
      renderChat(root);
    }
  };
  window.addEventListener("hashchange", route);
  route();
}
```

- [ ] **Step 2: Update `frontend/src/main.ts`**

```typescript
import "./styles.css";
import { mount } from "./router";

const root = document.querySelector<HTMLDivElement>("#app");
if (!root) {
  throw new Error("#app mount point missing");
}
mount(root);
```

- [ ] **Step 3: Manual smoke**

Run: `cd frontend && npm run dev` and verify navigating `#/settings` switches to the settings panel, returning to `#/` shows chat. Token persists across reloads.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/main.ts frontend/src/router.ts
git commit -m "Add hash-router (#/ chat, #/settings) and mount in main.ts"
```

---

## Task 10: Production styling pass

**Files:**
- Modify: `frontend/src/styles.css`

The composer, messages, mic button, and trace panel all need real styling before this is usable. This is a single-step task: rewrite `styles.css` and verify in the browser. Visual smoke test only.

- [ ] **Step 1: Rewrite `frontend/src/styles.css`**

```css
* { box-sizing: border-box; }
:root {
  color-scheme: dark;
  --bg: #0d0d0d;
  --fg: #f0f0f0;
  --accent: #8b9eff;
  --muted: #888;
  --border: #2a2a2a;
  --card: #1a1a1a;
  --user-bg: #21304a;
  --assistant-bg: #1a1a1a;
  --ok: #4ade80;
  --err: #f87171;
  font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo",
               "Helvetica Neue", "Segoe UI", sans-serif;
}
body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  min-height: 100svh;
}
.app-shell {
  max-width: 720px;
  margin: 0 auto;
  padding: env(safe-area-inset-top, 12px) 12px env(safe-area-inset-bottom, 12px);
  min-height: 100svh;
  display: flex;
  flex-direction: column;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 12px;
}
.topbar h1 { margin: 0; font-size: 1.4rem; }
.topbar a { color: var(--muted); text-decoration: none; }
.messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 12px;
}
.message {
  border-radius: 12px;
  padding: 10px 14px;
  max-width: 90%;
  word-wrap: break-word;
}
.message.user {
  background: var(--user-bg);
  align-self: flex-end;
}
.message.assistant {
  background: var(--assistant-bg);
  border: 1px solid var(--border);
  align-self: flex-start;
}
.markdown p { margin: 0 0 8px 0; }
.markdown p:last-child { margin-bottom: 0; }
.markdown code { background: #2a2a2a; padding: 1px 6px; border-radius: 4px; font-size: 0.9em; }
.markdown pre { background: #0a0a0a; border: 1px solid var(--border); padding: 10px; border-radius: 6px; overflow-x: auto; }
.atom-link { margin: 8px 0 0 0; font-size: 0.85em; color: var(--accent); }
.trace { margin-top: 8px; font-size: 0.85em; }
.trace summary { color: var(--muted); cursor: pointer; }
.trace-summary { white-space: pre-wrap; background: #0a0a0a; padding: 8px; border-radius: 6px; margin: 6px 0; }
.trace-json { background: #0a0a0a; padding: 8px; border-radius: 6px; overflow-x: auto; font-size: 0.9em; }
.composer {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.composer textarea {
  background: var(--card);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 1rem;
  resize: vertical;
}
.composer-buttons {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}
.composer button {
  background: var(--accent);
  color: #0d0d0d;
  border: none;
  border-radius: 8px;
  padding: 10px 16px;
  font-weight: 600;
  cursor: pointer;
}
.composer button.ghost { background: transparent; color: var(--muted); border: 1px solid var(--border); }
.composer button.mic { font-size: 1.4rem; padding: 8px 16px; touch-action: none; }
.composer button.mic.recording { background: var(--err); }
.status { min-height: 1.2em; color: var(--muted); margin: 0; font-size: 0.85em; }
.status.err { color: var(--err); }
.status.ok { color: var(--ok); }
.settings { padding: 12px; background: var(--card); border-radius: 8px; }
.settings .field { display: flex; flex-direction: column; gap: 4px; margin: 12px 0; }
.settings input {
  background: #0a0a0a;
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 10px;
}
.settings .actions { display: flex; gap: 8px; }
.msg.ok { color: var(--ok); }
.msg.err { color: var(--err); }
.hint { color: var(--muted); font-size: 0.85em; }
```

- [ ] **Step 2: Visual smoke**

Run dev server (`npm run dev`), open chat, send a test message. Verify: composer is sticky at the bottom, message bubbles align (user right, assistant left), mic button turns red while recording, trace summary is monospaced and readable.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles.css
git commit -m "Polish styles: bubbles, composer, mic state, trace panel"
```

---

## Task 11: Backend serves frontend `dist/` as static assets

**Files:**
- Modify: `015_little_lion/backend/main.py`
- Modify: `015_little_lion/scripts/run_dev.sh`
- Create: `frontend/src/icons/icon-192.png` + `frontend/src/icons/icon-512.png` (placeholder; or via online generator)

The production flow: `npm run build` produces `frontend/dist/`. The FastAPI backend mounts that at `/` so a single process serves both API and PWA over Tailscale.

- [ ] **Step 1: Update `backend/main.py`** to mount static assets at `/`

```python
"""FastAPI entry — wires config, auth, routes, and (in prod) serves the PWA build."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api.auth import BearerAuthMiddleware
from backend.api.chat import router as chat_router
from backend.api.health import router as health_router
from backend.api.voice import router as voice_router
from backend.config import get_settings


def build_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Little Lion", version="0.0.1")
    app.add_middleware(BearerAuthMiddleware, token=settings.auth_token)
    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(voice_router)

    dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if dist.exists() and os.environ.get("LITTLE_LION_SERVE_FRONTEND", "true").lower() != "false":
        # html=True makes StaticFiles fall back to index.html for SPA routes.
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
    return app


app = build_app()


def main() -> None:
    import uvicorn
    s = get_settings()
    uvicorn.run("backend.main:app", host=s.backend_host, port=s.backend_port, log_level=s.log_level.lower())


if __name__ == "__main__":
    main()
```

Note: the StaticFiles mount must be added LAST. The bearer middleware allows `/healthz` and rejects API calls without token, but the SPA needs `/`, `/index.html`, `/assets/*` to be publicly readable. Since these paths don't match any earlier router, they fall through to StaticFiles. We need to add the static asset paths to `PUBLIC_PATHS` in `backend/api/auth.py`.

- [ ] **Step 2: Update `PUBLIC_PATHS` in `backend/api/auth.py`**

```python
PUBLIC_PATHS = {"/healthz"}
PUBLIC_PREFIXES = ("/assets/", "/icons/")
PUBLIC_FILES = {"/", "/index.html", "/manifest.webmanifest", "/sw.js", "/registerSW.js", "/favicon.svg"}
```

And update `dispatch`:

```python
async def dispatch(self, request: Request, call_next):  # type: ignore[override]
    path = request.url.path
    if path in PUBLIC_PATHS or path in PUBLIC_FILES:
        return await call_next(request)
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != self._token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad token")
    return await call_next(request)
```

- [ ] **Step 3: Update existing backend tests if they break**

Run: `cd /Users/seongwookjang/project/git/violet_sw/015_little_lion && pytest tests/api/ -v`
Expected: pass — the previously-protected paths (`/chat`, `/ws/voice`) are still protected; only the static SPA files are public.

- [ ] **Step 4: Update `scripts/run_dev.sh`** to optionally skip serving frontend (for backend-only dev)

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo ".env not found — copy .env.example and fill in keys."
  exit 1
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
  echo "WARN: Ollama not responding at http://127.0.0.1:11434"
fi

# Build the PWA if dist/ is missing (skip with --no-frontend for backend-only loop).
if [[ "${1:-}" != "--no-frontend" ]]; then
  if [[ ! -d frontend/dist ]]; then
    echo "Building frontend (one-time)..."
    (cd frontend && npm install && npm run build)
  fi
fi

exec uvicorn backend.main:app \
  --host "${BACKEND_HOST:-127.0.0.1}" \
  --port "${BACKEND_PORT:-8765}" \
  --reload \
  --log-level info
```

- [ ] **Step 5: Build + run end-to-end smoke**

```bash
cd frontend && npm run build && cd ..
./scripts/run_dev.sh
# Open http://127.0.0.1:8765 in browser → should show the PWA
```

Verify: chat page loads, mic permission prompt fires on PTT button press, settings page accessible at `#/settings`, healthz still returns 200 unauthenticated, `/chat` rejects unauthenticated.

- [ ] **Step 6: Commit**

```bash
git add backend/main.py backend/api/auth.py scripts/run_dev.sh
git commit -m "Backend serves frontend dist/ at / with public SPA path allow-list"
```

---

## Task 12: README quickstart update + iPhone install guide

**Files:**
- Modify: `README.md`
- Create: `docs/IOS_INSTALL.md`

- [ ] **Step 1: Append to `README.md`** (after the existing quickstart)

```markdown
## Frontend (PWA) build

```bash
cd frontend
npm install
npm run build       # produces frontend/dist/
```

The backend serves `dist/` at `/` automatically on next start (`./scripts/run_dev.sh`).

For frontend-only dev with hot reload (Vite proxies `/chat`+`/ws` to the backend):

```bash
cd frontend && npm run dev
# → http://127.0.0.1:5173
```

## Mobile access (iPhone via Tailscale)

See `docs/IOS_INSTALL.md`.
```

- [ ] **Step 2: Create `docs/IOS_INSTALL.md`**

```markdown
# iPhone Install — Little Lion PWA

Prerequisite: Plan 1c installs Tailscale on the Mac and your iPhone. Once both devices are on the same Tailscale network, the Mac is reachable at `http://<mac-tailscale-name>:8765`.

1. Open Safari on the iPhone.
2. Navigate to `http://<mac-tailscale-name>:8765`.
3. Tap the Share icon → **Add to Home Screen**. The icon launches the app in standalone mode.
4. First launch: tap the gear icon (top-right) → paste the BACKEND_AUTH_TOKEN from the Mac's `.env` → Save.
5. To use Push-to-Talk: tap the mic button and hold while speaking. Safari will prompt for microphone permission on first use.

Known iOS limitations:
- Background mic recording is not supported; the app must be foreground.
- WebSocket connections survive screen lock but pause network for a few seconds after wake.
- iOS does not let PWAs ring a notification badge from the server; assistant push notifications are deferred to Phase 3 (Telegram).
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/IOS_INSTALL.md
git commit -m "Add PWA build instructions + iPhone install guide"
```

---

## Self-Review Results

**1. Spec coverage** (against Phase 1 PWA scope from design + deep-dive):
- Vite + TS scaffold → Task 1
- PWA manifest + service worker → Task 1 (vite-plugin-pwa)
- Auth token storage → Task 2
- REST `/chat` client → Task 3
- WebSocket `/ws/voice` client → Task 4
- Markdown rendering with XSS guard → Task 5
- Trace panel (deep-dive §5 4-line summary + full JSON) → Task 6
- Chat container → Task 7
- Push-to-Talk wiring → Task 8
- Hash routing (chat / settings) → Task 9
- Production styling → Task 10
- Backend static serving → Task 11
- README + iOS install → Task 12

**2. Placeholder scan** — no TBD/TODO; placeholder icons (Task 11) explicitly flagged for the executor.

**3. Type consistency** — `ChatResponse`, `DecisionTrace` from `src/lib/types.ts` exactly match the Phase 1a backend's `backend/services/pipeline.py` ChatResult.trace shape. `VoiceWSResponse` extends ChatResponse with `transcript`/`lang` matching `backend/api/voice.py`.

**4. Token consistency** — `localStorage` key `little-lion:token` used in `auth.ts`, fetched via `getToken()` in `api.ts` and `voice.ts`. Settings UI is the only writer.

**5. Cross-references** — All test fixtures use the same mock `MockWebSocket`, `FakeRecorder` patterns; no duplicate definitions across files.

**Open items deferred to Plan 1c (Ops):**
- Frontend icon assets (Task 11 leaves `icon-192.png`/`icon-512.png` as placeholders to be generated).
- Tailscale install guide referenced in `docs/IOS_INSTALL.md` — actual install steps belong in Plan 1c.

---

## Execution Handoff

**Plan complete and saved to `015_little_lion/docs/specs/2026-05-18-little-lion-phase1b-pwa-plan.md`. Same two execution options as Plan 1a — Subagent-Driven or Inline. Decide together with Plan 1a execution mode.**
