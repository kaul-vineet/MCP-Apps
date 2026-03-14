# Building a Flight Tracker MCP App with UI Widgets in M365 Copilot
### A developer's field notes — victories, failures, and a few moments of quiet despair

**Author:** Vineet Kaul, PM Architect – Agentic AI, Microsoft
**Date:** March 2026
**Stack:** Python · FastMCP 1.26 · OpenSky Network API · Microsoft Dev Tunnels · M365 Agents Toolkit

---

## What We Built

A **Flight Tracker MCP server** that plugs into Microsoft 365 Copilot (and ChatGPT) as a Declarative Agent. Ask it about any aircraft by ICAO24 transponder code and it:

1. Fetches flight history from the [OpenSky Network](https://opensky-network.org/) API
2. Renders a **live interactive widget** — a flight table directly inside the Copilot chat
3. On clicking any flight row, **calls back to the MCP server in real time** to fetch the aircraft's live position, altitude, speed, and heading
4. Applies light/dark theming automatically from the host
5. Suppresses model text — the widget *is* the response

The agent supports three prompts: `lookup_flights`, `analyse_aircraft`, and `flight_briefing`. It uses two tools: `get_flights_by_aircraft` and `get_aircraft_state`.

> *As Sir Humphrey might put it: "The widget renders the data in a manner that is both informative and — dare I say — visually courageous."*

---

## What Are MCP Apps?

[MCP Apps](https://apps.extensions.modelcontextprotocol.io/api/documents/Overview.html) is an **official extension to the Model Context Protocol** that lets MCP servers deliver interactive HTML user interfaces directly inside AI chat hosts. Think of it as the difference between a civil servant reading out a spreadsheet aloud versus handing you the spreadsheet.

Before MCP Apps, every host (ChatGPT, Claude, M365) had incompatible UI mechanisms. MCP Apps standardises this into a **write-once, render-anywhere** pattern.

### Architecture in 30 seconds

```
MCP Server          →   Host (M365 / ChatGPT)   →   Widget (sandboxed iframe)
  tools/list             renders iframe               receives structuredContent
  resources/read         proxies postMessage          calls back via callTool
  tools/call             enforces CSP                 notifies height
```

Three entities:
- **Server** — declares tools with `_meta.ui.resourceUri` pointing to HTML resources
- **Host** — fetches the HTML resource, renders it in a sandboxed iframe
- **Widget** — receives `structuredContent` from the tool result, calls tools back, reports height

### Key concepts

| Concept | What it does |
|---|---|
| `ui://` URI scheme | Widget resource address, e.g. `ui://widget/flights.html` |
| `text/html;profile=mcp-app` | MIME type that tells the host "this is a widget, not a document" |
| `_meta.ui.resourceUri` | On the **tool definition** — links a tool to its widget |
| `structuredContent` | Rich typed data in the tool result; keeps model context clean |
| `window.openai.toolOutput` | How the widget receives the tool result in ChatGPT / M365 |
| `window.openai.callTool` | Widget calling back to an MCP tool (e.g. fetch live state on click) |
| `window.openai.notifyIntrinsicHeight` | Auto-sizes the iframe to content height |

### M365 Copilot support status

M365 Copilot supports the OpenAI Apps SDK widget bridge. Full capability matrix: [Microsoft Learn – UI widgets for declarative agents](https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/declarative-agent-ui-widgets).

Key supported APIs: `toolOutput` ✅ · `callTool` ✅ · `notifyIntrinsicHeight` ✅ · `theme` ✅ · `requestDisplayMode` (fullscreen only) ✅

> ⚠️ Note: MCP Apps native support (`@modelcontextprotocol/ext-apps`) is listed as "coming soon" on the M365 docs. Today's support is via the **OpenAI Apps SDK bridge** (`window.openai.*`). Keep an eye on this — it's moving fast.

---

## Project Structure

```
flight-tracker-mcp/
├── flight_tracker_mcp/
│   ├── __init__.py
│   ├── server.py          # FastMCP server — tools, resource, prompts
│   └── web/
│       └── widget.html    # Self-contained HTML widget (no build step)
├── tests/
│   └── widget_test.html   # Local test harness — no M365 needed
├── .env                   # OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET
└── pyproject.toml
```

And separately, the M365 Declarative Agent project:

```
flight-tracker-agent/
└── Flight Tracker/
    └── appPackage/
        ├── declarativeAgent.json
        ├── ai-plugin.json         # MCP runtime URL + function list
        ├── mcp-tools.json         # tools/list snapshot — CRITICAL (see below)
        └── instruction.txt        # System prompt for the agent
```

---

## Step-by-Step Setup — As We Actually Did It

### Step 1 — Environment

```bash
cd C:\demoprojects\flight-tracker-mcp
python -m venv .venv
.venv\Scripts\activate
pip install "mcp[cli]" httpx python-dotenv uvicorn starlette
```

**✅ Passed.** No drama here. The calm before the storm.

---

### Step 2 — Create the project structure

Create these files manually or via CLI:

```
flight_tracker_mcp/__init__.py
flight_tracker_mcp/server.py
flight_tracker_mcp/web/widget.html
tests/widget_test.html
.env
pyproject.toml
```

**✅ Passed.**

---

### Step 3 — Write the MCP server (`server.py`)

Key patterns:

```python
WIDGET_URI = "ui://widget/flights.html"
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"
WIDGET_HTML = (Path(__file__).parent / "web" / "widget.html").read_text(encoding="utf-8")

mcp = FastMCP("flight-tracker")

@mcp.resource(WIDGET_URI, mime_type=RESOURCE_MIME_TYPE)
async def flight_widget() -> str:
    return WIDGET_HTML

@mcp.tool(
    description="...",
    meta={"ui": {"resourceUri": WIDGET_URI}},   # ← on the DEFINITION, not the result
)
async def get_flights_by_aircraft(icao24, begin_date, end_date) -> types.CallToolResult:
    ...
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structuredContent={"icao24": icao24, "total_flights": n, "flights": [...]},
    )
```

Entry point:

```python
def main():
    app = mcp.streamable_http_app()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
    uvicorn.run(app, host="0.0.0.0", port=3000)
```

**✅ Passed.** Run with:
```bash
python -m flight_tracker_mcp.server
```

---

### Step 4 — Set up Dev Tunnel (named, persistent)

```bash
# One-time login (use device code to avoid Windows Auth Manager errors)
devtunnel user login -d

# Create a named tunnel (do this once — gives you a permanent hostname)
devtunnel create flight-tracker --allow-anonymous
devtunnel port create flight-tracker --port-number 3000

# Start the tunnel (every session)
devtunnel host flight-tracker --allow-anonymous
```

Permanent URL format: `https://flight-tracker-3000.{region}.devtunnels.ms`
e.g. `https://flight-tracker-3000.inc1.devtunnels.ms`

**🔴 Fix — WAM Error (Error Code: 3399614466):** Standard `devtunnel user login` failed on Windows via the Windows Authentication Manager broker. Fix: `devtunnel user login -d` forces device code flow in the browser.

**🔴 Fix — Ephemeral URLs:** Early sessions used ephemeral tunnels. Every restart gave a new URL, breaking `ai-plugin.json`. Fix: named tunnels with `devtunnel create` give a permanent hostname. The browser connect URL (e.g. `lzvf27m0.inc1.devtunnels.ms`) is still ephemeral — the *named* hostname (`flight-tracker-3000.inc1.devtunnels.ms`) is permanent.

**✅ Verify tunnel is live:**
```bash
curl https://flight-tracker-3000.inc1.devtunnels.ms/mcp
```
Should return JSON.

---

### Step 5 — OpenSky Network API

Register at [opensky-network.org](https://opensky-network.org) → create an OAuth2 client application → get `client_id` and `client_secret`.

```ini
# .env
OPENSKY_CLIENT_ID=your-client-id
OPENSKY_CLIENT_SECRET=your-client-secret
```

Token endpoint:
```
https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token
```

**🔴 Fix — 403 error:** Wrong token endpoint. Initially used `https://opensky-network.org/api/auth/token` (wrong). Correct endpoint is the Keycloak realm URL above.

**🔴 Fix — 401 error:** Attempted HTTP Basic Auth instead of OAuth2 Bearer token. Fix: use `grant_type=client_credentials` POST to the correct token endpoint, then pass `Authorization: Bearer {token}`.

**✅ Passed** after fixes.

---

### Step 6 — Build the widget (`widget.html`)

The widget is a **single self-contained HTML file** served as an MCP resource. No build step, no React, no bundler. Just HTML + vanilla JS.

Key features:
- CSS custom properties for light/dark theming (`[data-theme="dark"]`)
- Flight table with click-to-expand rows
- On row expand: calls `get_aircraft_state` via `window.openai.callTool`
- `notifyIntrinsicHeight` for auto-sizing
- MCP identity badge: `⚡ MCP Widget · flight-tracker-mcp`

**Data reception pattern (M365 compatibility):**

```javascript
function tryRenderFromOpenAI() {
  if (rendered) return;
  if (window.openai) {
    if (window.openai.theme) { applyTheme(window.openai.theme); }
    if (window.openai.toolOutput) {
      var out = window.openai.toolOutput;
      // M365 may deliver structuredContent directly or wrapped
      var data = (out && out.structuredContent !== undefined)
        ? out.structuredContent : out;
      render(data);
      rendered = true;
    }
  }
}
// M365 injects window.openai AFTER script runs — poll for it
tryRenderFromOpenAI();
if (!rendered) {
  var attempts = 0;
  var poll = setInterval(function() {
    attempts++;
    tryRenderFromOpenAI();
    if (rendered || attempts >= 30) clearInterval(poll);
  }, 100);
}
```

**🔴 Fix — Widget showed "Loading flight data..." in M365:** `window.openai` is injected *after* the script runs. Simple `if (window.openai)` check at startup always missed it. Fix: polling loop (30 × 100ms = 3 seconds).

**🔴 Fix — Transparent background in M365:** CSS default `background: transparent` caused the widget to be invisible inside the M365 iframe. Fix: explicitly set `--color-bg: #ffffff` (light) and `--color-bg: #1a1a1a` (dark).

**✅ Tested locally with `tests/widget_test.html`** — a mock harness that simulates M365 postMessage delivery without needing a live connection.

---

### Step 7 — Test with MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Connect to `https://flight-tracker-3000.inc1.devtunnels.ms/mcp` using **Streamable HTTP** transport.

Use to verify:
- `tools/list` returns tools with `_meta.ui.resourceUri`
- `resources/list` returns `ui://widget/flights.html` with MIME type `text/html;profile=mcp-app`
- Tool calls return `structuredContent`

> *Like Constable Goody with a new speed gun — extremely enthusiastic, occasionally baffled by the readings.*

**Note:** MCP Inspector v0.21.1 shows no entry in the "MCPApp" tab for Python servers. This is a known limitation — the Python SDK doesn't announce the `ext-apps` capability. It does **not** affect actual functionality in M365 or ChatGPT.

---

### Step 8 — Create the M365 Declarative Agent

**Prerequisites:**
- Microsoft 365 tenant with Copilot licence
- Custom App Upload enabled
- VS Code + [M365 Agents Toolkit](https://marketplace.visualstudio.com/items?itemName=TeamsDevApp.ms-teams-vscode-extension) v6.5.2x prerelease

**Steps:**
1. VS Code → Agents Toolkit → **Create a New Agent/App** → Declarative Agent → Start with MCP Server
2. Enter MCP server URL: `https://flight-tracker-3000.inc1.devtunnels.ms/mcp`
3. Open `.vscode/mcp.json` → click **Start**, then **ATK: Fetch action from MCP** → select `ai-plugin.json`
4. Select both tools → authentication: **None** (dev mode)
5. Update `ai-plugin.json` runtime URL to your named tunnel URL
6. **Update `mcp-tools.json`** (see critical fix below)
7. Agents Toolkit → Lifecycle → **Provision**
8. Test at [https://m365.cloud.microsoft/chat](https://m365.cloud.microsoft/chat)

---

### Step 9 — Fix: `instruction.txt`

Replace the default agent instructions with flight-tracker-specific behaviour:

```
You are a Flight Tracker assistant.
- When flight data is returned by a tool, DO NOT summarise in text. The widget displays it.
- If no flights are found, briefly say so in one sentence.
- For a "briefing", call get_flights_by_aircraft first, then get_aircraft_state.
- Keep all responses concise.
```

**Why:** Without this, the model dutifully typed out a full text table of flights *alongside* the widget. Like Baldrick reading aloud from a document while you're already reading it yourself.

---

## The Three Critical Fixes That Made It Work

### 🔴 Critical Fix 1 — `_meta` belongs on the tool DEFINITION, not the result

**Wrong (what we initially had):**
```python
return types.CallToolResult(
    content=[...],
    structuredContent={...},
    _meta={"ui": {"resourceUri": WIDGET_URI}},  # ← M365 ignores this
)
```

**Correct:**
```python
@mcp.tool(
    description="...",
    meta={"ui": {"resourceUri": WIDGET_URI}},   # ← M365 reads this from tools/list
)
async def get_flights_by_aircraft(...):
    return types.CallToolResult(
        content=[...],
        structuredContent={...},
        # no _meta here
    )
```

**Why:** M365 Copilot reads `_meta.ui.resourceUri` from the `tools/list` response at connection time — not from individual call results. It uses this to know *upfront* which tools have associated widgets. FastMCP 1.26+ supports `meta=` on `@mcp.tool()`.

---

### 🔴 Critical Fix 2 — `mcp-tools.json` must include `_meta`

`mcp-tools.json` is the **static snapshot** of `tools/list` that M365 uses at deploy time. It was generated by ATK's "Fetch action from MCP" before we added `meta` to the server. Result: M365 had no idea the tools had widgets.

**Fix:** Manually add `_meta` to each tool in `mcp-tools.json`:

```json
{
  "tools": [
    {
      "name": "get_flights_by_aircraft",
      "description": "...",
      "inputSchema": { ... },
      "title": "Get flights by aircraft",
      "_meta": {
        "ui": {
          "resourceUri": "ui://widget/flights.html"
        }
      }
    }
  ]
}
```

Then **re-provision** via Agents Toolkit.

> *This is the "Yes, Minister" of MCP development: the system was working perfectly. The widget was rendering. The tool was being called. OpenSky was returning data. But the civil service — `mcp-tools.json` — had filed the wrong paperwork, so nothing was authorised to actually happen.*

---

### 🔴 Critical Fix 3 — `window.openai.toolOutput` data format varies

In M365, `window.openai.toolOutput` may deliver `structuredContent` as the object **directly** rather than wrapped in `{ structuredContent: {...} }`. Handle both:

```javascript
var out = window.openai.toolOutput;
var data = (out && out.structuredContent !== undefined)
  ? out.structuredContent
  : out;
render(data);
```

---

## What `outputTemplate: ""` Breaks (Don't Do This)

Early attempts to suppress model text used:
```json
"outputTemplate": ""
```
in `ai-plugin.json`. This caused M365 to abandon widget rendering entirely and fall back to generating its own text summary from `structuredContent`. The widget disappeared. Use `instruction.txt` to suppress commentary instead.

---

## Developer Community Challenges

The MCP Apps ecosystem is young and moving fast. Here's what the community is running into:

| Challenge | Summary |
|---|---|
| **UI state on re-open** | When users return to a chat, `ontoolresult` doesn't re-fire for historical messages. Widget loads in empty state. No clean solution yet. ([GitHub #195](https://github.com/openai/openai-apps-sdk-examples/issues/195)) |
| **Python/Node.js parity gap** | The official `@modelcontextprotocol/ext-apps` package is TypeScript-only. Python servers must use FastMCP's `meta=` parameter and handle the `window.openai.*` bridge manually — no `useApp()` hook equivalent. |
| **`mcp-tools.json` is a manual step** | ATK requires a static snapshot of `tools/list`. Any server-side change to tool metadata requires re-fetching, re-editing, and re-provisioning. (Acknowledged as temporary in the docs.) |
| **Debugging black box** | When the widget shows nothing, there's no browser console accessible inside the M365 iframe. Diagnosis requires reading server logs, MCP Inspector, and a lot of educated guessing. |
| **Dev tunnel lifecycle** | Ephemeral tunnels break agent manifests on every restart. Named tunnels fix this but add setup friction. `--allow-anonymous` is required or M365 gets redirected to a login page mid-session. |
| **`ext-apps` capability not announced by Python SDK** | MCP Inspector shows no MCP Apps capability for Python servers. Functionally harmless for M365 today, but may matter as hosts start gating features behind capability negotiation. |
| **M365 preview limitations** | MCP Apps native support (`app.ontoolresult`, React hooks) is "coming soon" for M365. Today's support is the OpenAI Apps SDK bridge. Fullscreen-only for `requestDisplayMode`. No modals. No file upload. |
| **CSP and CORS for widget callbacks** | Widgets calling back to the MCP server via `callTool` go through `{hashed-domain}.widget-renderer.usercontent.microsoft.com`. CORS must allow this origin. The [Widget Host URL Generator](https://aka.ms/mcpwidgeturlgenerator) helps. |

---

## References

| Resource | Link |
|---|---|
| MCP Apps Overview | https://apps.extensions.modelcontextprotocol.io/api/documents/Overview.html |
| OpenAI Apps SDK | https://developers.openai.com/apps-sdk |
| M365 UI Widgets Docs | https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/declarative-agent-ui-widgets |
| M365 ATK Instructions | https://github.com/microsoft/mcp-interactiveUI-samples/blob/main/M365-Agents-Toolkit-Instructions.md |
| MCP Interactive UI Samples (Node.js) | https://github.com/microsoft/mcp-interactiveUI-samples |
| ext-apps npm package | https://www.npmjs.com/package/@modelcontextprotocol/ext-apps |
| FastMCP Python SDK | https://github.com/modelcontextprotocol/python-sdk |
| OpenSky Network API | https://openskynetwork.github.io/opensky-api/ |
| Dev Tunnels Docs | https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/ |
| Widget Host URL Generator | https://aka.ms/mcpwidgeturlgenerator |

---

*"It's not that the technology doesn't work. It's that nobody told the manifest."*
— Vineet Kaul, after hour six of debugging `mcp-tools.json`
