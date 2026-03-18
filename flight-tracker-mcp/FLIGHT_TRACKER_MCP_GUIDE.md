# Building a Flight Tracker MCP App in M365 Copilot

<!-- Hero image: screenshot of the flight widget rendering in M365 Copilot chat -->

| | |
|---|---|
| **Subtitle** | A developer's field notes — victories, measured progress, and occasional bafflement |
| **Author** | Vineet Kaul, PM Architect – Agentic AI, Microsoft |
| **Date** | March 2026 |
| **Stack** | Python · FastMCP 1.26 · OpenSky Network API · Microsoft Dev Tunnels · M365 Agents Toolkit |

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![MCP SDK](https://img.shields.io/badge/FastMCP-1.26-green)
![M365](https://img.shields.io/badge/M365_Copilot-Public_Preview-orange)
![License](https://img.shields.io/badge/License-MIT-lightgrey)

**Tags:** `mcp` `copilot` `python` `m365` `agentic-ai` `declarative-agent` `mcp-apps`

---

> **TL;DR** — Build a Python MCP server that renders a live interactive flight table inside M365 Copilot. Three non-obvious fixes determine whether the widget appears: `_meta` placement on the tool definition, the `mcp-tools.json` snapshot, and the `toolOutput` data format. If the widget is not rendering, skip directly to [Critical Troubleshooting](#critical-troubleshooting).

---

## Contents

- [✈️ Flight Tracker](#️-flight-tracker)
- [What Are MCP Apps?](#what-are-mcp-apps)
- [Project Structure](#project-structure)
- [Key Scripts](#key-scripts)
- [Prerequisites](#prerequisites)
- [Set-up](#set-up)
- [Critical Troubleshooting](#critical-troubleshooting)
- [Developer Community Challenges](#developer-community-challenges)
- [Quick Reference](#quick-reference)
- [References](#references)

---

## ✈️ Flight Tracker

The **Flight Tracker** is an MCP server that connects to M365 Copilot as a Declarative Agent. Give it any aircraft's ICAO24 transponder code and it:

| Step | What happens |
|---|---|
| 1️⃣ | Fetches flight history from OpenSky Network (dates, routes, callsigns) |
| 2️⃣ | Renders a **live interactive table** directly inside the Copilot chat |
| 3️⃣ | On clicking any row, **calls back to the MCP server in real time** for live aircraft state |
| 4️⃣ | Shows altitude, speed, heading, on-ground status — inline, no second prompt |
| 5️⃣ | Applies light/dark theming automatically from the M365 host |

The agent also supports **airport departure and arrival workflows** — click any flight row in an arrivals table to fetch the historical flight track, or in a departures table to fetch the aircraft's live state. Viewed rows are marked green with a ✓ checkmark.

**Five tools exposed:**
- `get_flights_by_aircraft` — flight history by date range
- `get_aircraft_state` — live position, altitude, speed, heading
- `get_airport_departures` — departing flights from an airport for a date range
- `get_airport_arrivals` — arriving flights at an airport for a date range
- `get_aircraft_track` — historical flight track (waypoints, start/end position)

**Five pre-built prompts:**
- `lookup_flights` — flight history for a given date
- `analyse_aircraft` — two-day pattern analysis
- `flight_briefing` — full briefing combining history and live state
- `lookup_departures` — departures from an airport on a given date
- `lookup_arrivals` — arrivals at an airport on a given date

**How data flows end to end:**
```
User types prompt
       │
[M365 Copilot LLM]  →  reads tools/list → sees _meta.ui.resourceUri
       │
tools/call  →  get_flights_by_aircraft(icao24, begin_date, end_date)
       │
[server.py]  →  OpenSky OAuth2 token  →  GET /api/flights/aircraft
               returns CallToolResult { content, structuredContent }
       │
M365 fetches ui://widget/flights.html  →  renders in sandboxed iframe
               injects window.openai.toolOutput = structuredContent
       │
Widget renders flight table
       │
  [User clicks a row]
       │
window.openai.callTool("get_aircraft_state", { icao24 })
               → GET /api/states/all
       │
Live state appears inline in the expanded row
```

---

## What Are MCP Apps?

[MCP Apps](https://apps.extensions.modelcontextprotocol.io/api/documents/Overview.html) is an **official extension to the Model Context Protocol** that enables MCP servers to deliver interactive HTML user interfaces directly inside AI chat hosts. The distinction is between a civil servant reading out a spreadsheet aloud and simply handing it over — MCP Apps opts for the latter.

Before MCP Apps, every host (ChatGPT, Claude, M365) had incompatible UI mechanisms. MCP Apps standardises this into a **write-once, render-anywhere** pattern.

### Architecture

```
MCP Server              Host (M365 / ChatGPT)       Widget (sandboxed iframe)
──────────────────      ─────────────────────       ─────────────────────────
tools/list          →   reads _meta.ui.resourceUri
resources/read      →   renders iframe           →   receives structuredContent
tools/call          →   proxies postMessage      ←→  calls back via callTool
                        enforces CSP                 notifies height
```

Three entities:
- **Server** — declares tools with `_meta.ui.resourceUri` pointing to HTML resources
- **Host** — fetches the HTML resource, renders it in a sandboxed iframe
- **Widget** — receives `structuredContent` from the tool result, calls tools back, reports height

### Key Concepts

| Concept | What it does |
|---|---|
| `ui://` URI scheme | Widget resource address, e.g. `ui://widget/flights.html` |
| `text/html;profile=mcp-app` | MIME type that tells the host this is a widget, not a document |
| `_meta.ui.resourceUri` | On the **tool definition** — links a tool to its widget |
| `structuredContent` | Rich typed data in the tool result; keeps model context clean |
| `window.openai.toolOutput` | How the widget receives the tool result in ChatGPT / M365 |
| `window.openai.callTool` | Widget calling back to an MCP tool |
| `window.openai.notifyIntrinsicHeight` | Auto-sizes the iframe to content height |

### MCP Apps Widgets vs Adaptive Cards

Developers familiar with Microsoft 365 extensibility will reasonably ask: why not just use Adaptive Cards?

Adaptive Cards are a JSON-based declarative schema. The host renders them natively — consistent styling across Teams, Outlook, and Copilot, with zero custom code. They are well-suited to structured notifications, simple forms, and approval flows.

MCP Apps widgets are full HTML/CSS/JavaScript running in a sandboxed iframe. The developer controls everything.

| Capability | Adaptive Cards | MCP Apps Widget |
|---|---|---|
| Rendering | Host-rendered from JSON schema | Browser-rendered HTML in iframe |
| Interactivity | Predefined action types only | Any JavaScript interaction |
| Real-time data | Static at render; refresh requires a new card | Calls back to MCP server at any time via `callTool` |
| Styling | Host controls appearance | Full CSS control; consistent everywhere |
| Custom layout | Constrained by card schema | Unconstrained |
| Portability | Teams, Outlook, Copilot, many hosts | Any MCP Apps compliant host |
| Build complexity | JSON only; no code | Requires HTML/JS development |

**For the Flight Tracker specifically:** An Adaptive Card could display the flight table — but only as a static snapshot. Clicking a row to fetch live aircraft state is not possible within a card; it would require the user to ask a follow-up question, triggering a second tool call and a second card.

The Flight Tracker widget handles this in a single interaction: the table renders, the user clicks a row, `callTool` fires `get_aircraft_state`, and the live state appears inline — no second prompt, no additional model invocation.

> 💡 **Rule of thumb** — Use Adaptive Cards when the data is complete at render time. Use MCP Apps widgets when the UI needs to remain active after the initial tool call returns. Adaptive Cards are a very competent filing clerk. The MCP Apps widget is the analyst who follows up.

### M365 Copilot Support Status

M365 Copilot supports the OpenAI Apps SDK widget bridge. Full capability matrix: [Microsoft Learn – UI widgets for declarative agents](https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/declarative-agent-ui-widgets).

Supported APIs:
- `window.openai.toolOutput` ✅
- `window.openai.callTool` ✅
- `window.openai.notifyIntrinsicHeight` ✅
- `window.openai.theme` ✅
- `window.openai.requestDisplayMode` ✅ (fullscreen only)
- `window.openai.sendFollowUpMessage` ✅

> ⚠️ **Preview note** — MCP Apps native support (`@modelcontextprotocol/ext-apps`) is listed as "coming soon" on the M365 docs. Current support is via the **OpenAI Apps SDK bridge** (`window.openai.*`). This will change — watch the M365 release notes.

---

## Project Structure

```
flight-tracker-mcp/
├── flight_tracker_mcp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── server.py          # FastMCP server — tools, resource, prompts
│   ├── tests/
│   │   └── widget_test.html   # Local test harness — no M365 needed
│   └── web/
│       └── widget.html    # Self-contained HTML widget (no build step)
├── .env                   # OPENSKY_CLIENT_ID, OPENSKY_CLIENT_SECRET
└── pyproject.toml
```

M365 Declarative Agent project (separate):

```
flight-tracker-agent/
├── appPackage/
│   ├── declarativeAgent.json
│   ├── ai-plugin.json         # MCP runtime URL + function list
│   ├── manifest.json          # Teams/M365 app manifest
│   ├── mcp-tools.json         # tools/list snapshot — CRITICAL (see Critical Troubleshooting)
│   ├── instruction.txt        # System prompt for the agent
│   ├── color.png
│   └── outline.png
├── env/
│   ├── .env.dev
│   └── .env.dev.user
├── .vscode/
│   └── mcp.json               # MCP server config for ATK
└── m365agents.yml             # DA lifecycle stages for ATK
```

---

## Key Scripts

### `server.py` — The MCP Server

Built with [FastMCP](https://github.com/modelcontextprotocol/python-sdk) (Python MCP SDK 1.26). This is the core of the application.

**Resource registration** — the widget HTML is registered as an MCP resource with the `text/html;profile=mcp-app` MIME type, identifying it to any compliant host as a UI widget:

```python
@mcp.resource("ui://widget/flights.html", mime_type="text/html;profile=mcp-app")
async def flight_widget() -> str:
    return WIDGET_HTML
```

**Tool registration** — all tools carry `meta={"ui": {"resourceUri": ...}}` on the decorator. This places `_meta` on the **tool definition** in `tools/list`, which is where M365 reads it:

```python
@mcp.tool(
    description="...",
    meta={"ui": {"resourceUri": "ui://widget/flights.html"}},
)
async def get_flights_by_aircraft(icao24, begin_date, end_date) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structuredContent={"icao24": icao24, "total_flights": n, "flights": [...]},
    )
```

> ⚠️ **Critical** — `_meta` must be on the `@mcp.tool()` decorator, not in `CallToolResult`. See [Issue 1](#issue-1----meta-must-be-on-the-tool-definition-not-the-call-result).

**Five tools:**

| Tool | OpenSky Endpoint | Widget View |
|---|---|---|
| `get_flights_by_aircraft(icao24, begin_date, end_date)` | `/flights/aircraft` | Aircraft view |
| `get_aircraft_state(icao24)` | `/states/all` | State card (inline or standalone) |
| `get_airport_departures(airport, begin_date, end_date)` | `/flights/departure` | Departures view |
| `get_airport_arrivals(airport, begin_date, end_date)` | `/flights/arrival` | Arrivals view |
| `get_aircraft_track(icao24, time)` | `/tracks/all` | Track detail (inline in arrivals row) |

**Five prompts** (pre-built conversation starters):
- `lookup_flights` — flight history for an aircraft on a given date
- `analyse_aircraft` — two-day pattern analysis
- `flight_briefing` — full briefing combining history and live state
- `lookup_departures` — departures from an airport on a given date; offers live state follow-up
- `lookup_arrivals` — arrivals at an airport on a given date; offers track follow-up with `first_seen_ts`

**Example utterances:**

| Prompt | Example |
|---|---|
| Aircraft history | "Show flights for aircraft 3c675a" |
| Analyse aircraft | "Analyse aircraft 3c675a" |
| Airport departures | "Show departures from EGLL yesterday" |
| Airport arrivals | "Show arrivals at KJFK yesterday" |
| Live state (direct) | "Where is aircraft 3c675a right now?" |

**Entry point** — Streamable HTTP server on port 3000 with CORS middleware:

```python
def main():
    app = mcp.streamable_http_app()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], ...)
    uvicorn.run(app, host="0.0.0.0", port=3000)
```

---

### `widget.html` — The UI Widget

A **single self-contained HTML file** with no build step, no framework, no bundler. Vanilla HTML and JavaScript, served directly by the MCP server as a resource and rendered inside a sandboxed iframe in Copilot chat.

The widget supports **three view modes**, determined by the shape of `structuredContent`:

| View Mode | Triggered by | Row click behaviour |
|---|---|---|
| `aircraft` | `{ icao24, flights[] }` | No row expansion; footer button calls `get_aircraft_state` |
| `departures` | `{ type: "departures", flights[] }` | Click row → `get_aircraft_state` inline |
| `arrivals` | `{ type: "arrivals", flights[] }` | Click row → `get_aircraft_track` inline (using `first_seen_ts`) |

A standalone `get_aircraft_state` result (no `flights` array) renders as a state card rather than a table.

**Checked row UX** — after a row's detail data loads successfully, the row turns green and the toggle cell shows `✓`. The green state persists when the row is collapsed, giving the user a clear visual record of which flights have been checked.

Key behaviours:
- Receives data via `window.openai.toolOutput`; dispatches to the correct view mode via `render()`
- `toggleRow(idx)` — branches on `viewMode` to call either `get_aircraft_state` or `get_aircraft_track`
- `fetchLiveState()` — aircraft view footer button; calls `get_aircraft_state` for the whole aircraft
- `renderDetail(idx, state)` — renders live state in an expanded departures row
- `renderTrackDetail(idx, track)` — renders track summary in an expanded arrivals row
- `renderStateCard(state)` — renders a standalone state card (no table)
- Light/dark theming via CSS custom properties applied from `window.openai.theme`
- Auto-height notification via `window.openai.notifyIntrinsicHeight`
- Polling pattern to handle M365's delayed injection of `window.openai`

> 📝 **Note** — The widget is cloned with the repository in Step 2. Developers extending it should review the `render()`, `toggleRow()`, and `tryRenderFromOpenAI()` functions, and the `--color-*` CSS variables for theming.

---

### `widget_test.html` — Local Test Harness

A standalone HTML page that simulates M365/ChatGPT postMessage data delivery. Allows the widget to be tested entirely locally — no live server, no tunnel, no M365 account required. Includes mock data for all three view modes, a dark/light toggle, and an event log panel. Use this before every M365 deployment.

**Three mock send buttons:**

| Button | Colour | Simulates |
|---|---|---|
| Send Mock Flights | Blue | `get_flights_by_aircraft` — aircraft view, 3 rows, ICAO24 `3c675a` |
| Send Mock Departures | Green | `get_airport_departures` — EGLL, 3 rows, includes `icao24` + `first_seen_ts` |
| Send Mock Arrivals | Orange | `get_airport_arrivals` — KJFK, 3 rows, includes `icao24` + `first_seen_ts` |

The harness intercepts all `callTool` requests and routes them to mock responses:
- `get_aircraft_state` → returns mock position, altitude, speed, heading
- `get_aircraft_track` → returns mock waypoints, start/end time, first/last position

No live MCP server or internet connection required for local testing.

---

## Prerequisites

Before beginning, confirm all of the following are in place:

- [ ] Python 3.11+
- [ ] Microsoft 365 tenant with Copilot licence
- [ ] Custom App Upload enabled on the tenant
- [ ] Copilot Access enabled on the tenant
- [ ] VS Code + [M365 Agents Toolkit](https://marketplace.visualstudio.com/items?itemName=TeamsDevApp.ms-teams-vscode-extension) v6.5.2x prerelease or later
- [ ] [Microsoft Dev Tunnels CLI](https://learn.microsoft.com/en-us/azure/developer/dev-tunnels/get-started) installed
- [ ] [OpenSky Network account](https://opensky-network.org) (free) with an OAuth2 client application created
- [ ] [MCP Inspector](https://www.npmjs.com/package/@modelcontextprotocol/inspector) available (`npx @modelcontextprotocol/inspector`)
- [ ] Node.js installed (for MCP Inspector)

---

## Set-up

### Step 1 — Environment

```bash
cd C:\demoprojects\flight-tracker-mcp
python -m venv .venv
.venv\Scripts\activate
pip install "mcp[cli]" httpx python-dotenv uvicorn starlette
```

---

### Step 2 — Clone the Repository

```bash
git clone https://github.com/your-org/flight-tracker-mcp.git
cd flight-tracker-mcp
```

Confirm the following files are present:

```
flight_tracker_mcp/server.py
flight_tracker_mcp/web/widget.html
tests/widget_test.html
.env.example
pyproject.toml
```

Copy `.env.example` to `.env` and populate the OpenSky credentials (see Step 4).

Start the server:

```bash
python -m flight_tracker_mcp.server
```

Expected: `INFO: Uvicorn running on http://0.0.0.0:3000`

---

### Step 3 — Set up Dev Tunnel (named, persistent)

A named tunnel provides a **permanent public hostname** that does not change between sessions. This is essential — an ephemeral tunnel URL breaks the agent manifest on every restart.

```bash
# One-time login
devtunnel user login -d

# Create named tunnel (run once)
devtunnel create flight-tracker --allow-anonymous
devtunnel port create flight-tracker --port-number 3000

# Start tunnel (each session)
devtunnel host flight-tracker --allow-anonymous
```

Permanent URL format: `https://flight-tracker-3000.{region}.devtunnels.ms`

Verify the tunnel is live:

```bash
curl https://flight-tracker-3000.inc1.devtunnels.ms/mcp
```

Expected: JSON response.

#### Troubleshooting

> ⚠️ **WAM Error (Error Code: 3399614466)** — `devtunnel user login` fails on Windows via the Windows Authentication Manager broker. Use `devtunnel user login -d` to force device code flow in the browser.

> ⚠️ **Ephemeral URL on restart** — The browser connect URL shown at startup (e.g. `lzvf27m0.inc1.devtunnels.ms`) is always ephemeral. The *named* tunnel hostname (`flight-tracker-3000.inc1.devtunnels.ms`) is permanent. Only the permanent hostname belongs in `ai-plugin.json`.

---

### Step 4 — OpenSky Network API

Register at [opensky-network.org](https://opensky-network.org) → create an OAuth2 client application → obtain `client_id` and `client_secret`.

```ini
# .env
OPENSKY_CLIENT_ID=your-client-id
OPENSKY_CLIENT_SECRET=your-client-secret
```

Token endpoint:

```
https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token
```

#### Troubleshooting

> ⚠️ **403 Forbidden** — Incorrect token endpoint. The OpenSky API uses a Keycloak realm URL, not `opensky-network.org/api/auth/token`. Use the endpoint above.

> ⚠️ **401 Unauthorised** — HTTP Basic Auth is not accepted. Use OAuth2 `grant_type=client_credentials` and pass `Authorization: Bearer {token}`.

---

### Step 5 — Test the Widget Locally

Before connecting to M365, verify the widget renders correctly:

```bash
# Open in browser directly
tests/widget_test.html
```

Use **Send Mock Flights**, **Send Mock Departures**, or **Send Mock Arrivals** to test all three view modes. Click rows in departures/arrivals views to test the `callTool` flow. Use **Toggle Dark/Light** to verify theming. No server or tunnel required.

> 💡 **Always test locally first.** Debugging inside the M365 iframe is considerably less pleasant than debugging in a browser with DevTools open.

---

### Step 6 — Verify with MCP Inspector

```bash
npx @modelcontextprotocol/inspector
```

Connect using **Streamable HTTP** transport to `https://flight-tracker-3000.inc1.devtunnels.ms/mcp`.

Verify the following before proceeding to M365:

- [ ] `tools/list` returns all five tools, each with `_meta: { ui: { resourceUri: "ui://widget/flights.html" } }`
- [ ] `resources/list` returns `ui://widget/flights.html` with MIME type `text/html;profile=mcp-app`
- [ ] `get_flights_by_aircraft` returns `structuredContent` with `icao24` and `flights[]`
- [ ] `get_airport_departures` returns `structuredContent` with `type: "departures"` and `flights[]` including `first_seen_ts`
- [ ] `get_airport_arrivals` returns `structuredContent` with `type: "arrivals"` and `flights[]` including `first_seen_ts`
- [ ] `get_aircraft_track` returns `structuredContent` with `found`, `waypoints`, `first_position`, `last_position`

> 📝 MCP Inspector v0.21.1 shows no entry in the "MCPApp" tab for Python servers — the Python SDK does not announce the `ext-apps` capability. This does **not** affect functionality in M365 or ChatGPT. A perfectly functional system appearing deficient in the inspector is, one notes, rather a civil service tradition.

---

### Step 7 — The Widget (`widget.html`)

The widget is served live from the MCP server — no re-provision is needed when it changes. Developers extending it should be familiar with:

- `--color-*` CSS variables in `:root` (light) and `[data-theme="dark"]` (dark) for theming
- `render(data)` — dispatches to the correct view mode based on `structuredContent` shape
- `toggleRow(idx)` — branches on `viewMode`: departures → `get_aircraft_state`, arrivals → `get_aircraft_track`
- `fetchLiveState()` — aircraft view footer button, calls `get_aircraft_state` for the whole aircraft
- `renderDetail` / `renderTrackDetail` / `renderStateCard` — view-specific rendering functions
- `checkedRows` — tracks which rows have loaded data; drives the green row + ✓ checkmark UX
- `tryRenderFromOpenAI()` + polling loop — handles M365's delayed `window.openai` injection

#### Troubleshooting

> ⚠️ **"Loading flight data..." stuck in M365** — `window.openai` is injected after the script runs. A direct startup check always misses it. The polling loop (30 × 100ms) resolves this.

> ⚠️ **Invisible widget in M365** — CSS `background: transparent` renders the widget invisible in the M365 iframe. Set `--color-bg: #ffffff` (light) and `--color-bg: #1a1a1a` (dark) explicitly.

---

### Step 8 — Create the M365 Declarative Agent

**Steps:**

1. VS Code → Agents Toolkit → **Create a New Agent/App** → Declarative Agent → Start with MCP Server
2. Enter MCP server URL: `https://flight-tracker-3000.inc1.devtunnels.ms/mcp`
3. Open `.vscode/mcp.json` → click **Start**, then **ATK: Fetch action from MCP** → select `ai-plugin.json`
4. Select both tools → authentication: **None** (development mode)
5. Confirm the runtime URL in `ai-plugin.json` matches the named tunnel URL
6. Update `mcp-tools.json` — **see [Issue 2](#issue-2----mcp-toolsjson-must-include-_meta) before proceeding**
7. Agents Toolkit → Lifecycle → **Provision**
8. Test at [https://m365.cloud.microsoft/chat](https://m365.cloud.microsoft/chat)

---

## Critical Troubleshooting

> ⚠️ These three issues are undocumented and will silently prevent the widget from rendering in M365. Work through the diagnostic checklist first, then refer to the detailed fix for any failing item.

### Diagnostic Checklist

Widget not rendering? Work through this list in order:

- [ ] Is `_meta` on the `@mcp.tool()` decorator — not in `CallToolResult`?
- [ ] Does `mcp-tools.json` contain `_meta.ui.resourceUri` for each tool?
- [ ] Was the agent re-provisioned after updating `mcp-tools.json`?
- [ ] Is the tunnel running with `--allow-anonymous`?
- [ ] Does the tunnel URL in `ai-plugin.json` match the named tunnel hostname (not the ephemeral one)?
- [ ] Is `outputTemplate: ""` absent from `ai-plugin.json`?
- [ ] Is the widget handling both wrapped and unwrapped `toolOutput` formats?

---

### `_meta` must be on the tool definition, not the call result

M365 reads `_meta.ui.resourceUri` from the `tools/list` response at connection time — not from individual call results. Placing it only on `CallToolResult` means the widget is never fetched.

**Incorrect:**
```python
return types.CallToolResult(
    content=[...],
    structuredContent={...},
    _meta={"ui": {"resourceUri": WIDGET_URI}},  # M365 does not read this
)
```

**Correct:**
```python
@mcp.tool(
    description="...",
    meta={"ui": {"resourceUri": WIDGET_URI}},   # M365 reads this from tools/list
)
async def get_flights_by_aircraft(...):
    return types.CallToolResult(
        content=[...],
        structuredContent={...},
    )
```

> 📝 FastMCP 1.26+ supports `meta=` on `@mcp.tool()`. This maps directly to `_meta` in the `tools/list` protocol response.

---

### `mcp-tools.json` must include `_meta`

`mcp-tools.json` is the **static snapshot of `tools/list`** M365 uses at deploy time. It is generated by ATK's "Fetch action from MCP" step. If `_meta` is added to the server after this file was generated, M365 will have no knowledge of the widget.

Manually add `_meta` to **every** tool entry. All five tools share the same widget URI:

```json
{
  "tools": [
    {
      "name": "get_flights_by_aircraft",
      "description": "...",
      "inputSchema": { "..." },
      "title": "Get flights by aircraft",
      "_meta": { "ui": { "resourceUri": "ui://widget/flights.html" } }
    },
    {
      "name": "get_aircraft_state",
      "description": "...",
      "inputSchema": { "..." },
      "title": "Get aircraft state",
      "_meta": { "ui": { "resourceUri": "ui://widget/flights.html" } }
    },
    {
      "name": "get_airport_departures",
      "description": "...",
      "inputSchema": { "..." },
      "title": "Get airport departures",
      "_meta": { "ui": { "resourceUri": "ui://widget/flights.html" } }
    },
    {
      "name": "get_airport_arrivals",
      "description": "...",
      "inputSchema": { "..." },
      "title": "Get airport arrivals",
      "_meta": { "ui": { "resourceUri": "ui://widget/flights.html" } }
    },
    {
      "name": "get_aircraft_track",
      "description": "...",
      "inputSchema": { "..." },
      "title": "Get aircraft track",
      "_meta": { "ui": { "resourceUri": "ui://widget/flights.html" } }
    }
  ]
}
```

Re-provision via Agents Toolkit after updating this file.

> This is the "Yes, Minister" of MCP development: the server is functioning, the tool is being called, data is returning — yet the widget does not appear. The reason, it transpires, is that `mcp-tools.json` filed the original paperwork without the widget declaration, and M365 — being a conscientious bureaucrat — acted precisely on what it was told.

---

### `window.openai.toolOutput` data format varies between hosts

In M365, `window.openai.toolOutput` may deliver `structuredContent` as the top-level object rather than wrapped inside `{ structuredContent: {...} }`. The widget must handle both:

```javascript
var out = window.openai.toolOutput;
var data = (out && out.structuredContent !== undefined)
  ? out.structuredContent
  : out;
render(data);
```

---

### What `outputTemplate: ""` breaks

Adding `"outputTemplate": ""` to `ai-plugin.json` causes M365 to abandon widget rendering and generate its own text summary from `structuredContent`. The widget disappears entirely. Use `instruction.txt` to suppress model commentary instead.

---

## Developer Community Challenges

The MCP Apps ecosystem is active and maturing rapidly. The following challenges are commonly encountered:

| Challenge | Summary |
|---|---|
| **UI state on re-open** | When users return to a chat, `ontoolresult` does not re-fire for historical messages. Widget loads in empty state. No clean solution yet. ([GitHub #195](https://github.com/openai/openai-apps-sdk-examples/issues/195)) |
| **Python/Node.js parity gap** | `@modelcontextprotocol/ext-apps` is TypeScript-only. Python servers must use FastMCP's `meta=` parameter and handle the `window.openai.*` bridge manually — no `useApp()` hook equivalent. |
| **`mcp-tools.json` is a manual step** | ATK requires a static snapshot of `tools/list`. Any change to tool metadata requires re-fetching, editing, and re-provisioning. Acknowledged as temporary in the official docs. |
| **Debugging inside the iframe** | No accessible browser console in M365. Diagnosis requires cross-referencing server logs, MCP Inspector, and considerable patience. |
| **Dev tunnel lifecycle** | Ephemeral tunnels break manifests on restart. Named tunnels resolve this. `--allow-anonymous` is required or M365 is redirected to a login page mid-session. |
| **`ext-apps` capability not announced by Python SDK** | MCP Inspector shows no MCP Apps capability for Python servers. Currently harmless, but may matter as hosts begin gating features behind capability negotiation. |
| **M365 preview limitations** | MCP Apps native support is "coming soon". Current support is OpenAI Apps SDK bridge only. Fullscreen-only `requestDisplayMode`; no modals; no file upload. |
| **CSP and CORS for widget callbacks** | `callTool` requests originate from `{hashed-domain}.widget-renderer.usercontent.microsoft.com`. CORS must allow this. Use the [Widget Host URL Generator](https://aka.ms/mcpwidgeturlgenerator). |

---

## Quick Reference

### Key Commands

| Task | Command |
|---|---|
| Start MCP server | `python -m flight_tracker_mcp.server` |
| Start named tunnel | `devtunnel host flight-tracker --allow-anonymous` |
| Login (first time) | `devtunnel user login -d` |
| Create named tunnel | `devtunnel create flight-tracker --allow-anonymous` |
| Add tunnel port | `devtunnel port create flight-tracker --port-number 3000` |
| Run MCP Inspector | `npx @modelcontextprotocol/inspector` |
| Test widget locally | Open `tests/widget_test.html` in browser |

### Key Values

| Item | Value |
|---|---|
| MCP server port | `3000` |
| MCP endpoint | `/mcp` |
| Widget URI | `ui://widget/flights.html` |
| Widget MIME type | `text/html;profile=mcp-app` |
| Tunnel URL format | `https://flight-tracker-3000.{region}.devtunnels.ms` |
| OpenSky token endpoint | `https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token` |

### Key Files

| File | Purpose |
|---|---|
| `flight_tracker_mcp/server.py` | FastMCP server — tools, resource, prompts |
| `flight_tracker_mcp/web/widget.html` | UI widget — served as MCP resource |
| `tests/widget_test.html` | Local test harness |
| `.env` | OpenSky credentials |
| `appPackage/ai-plugin.json` | M365 plugin manifest — runtime URL |
| `appPackage/mcp-tools.json` | Static `tools/list` snapshot — must include `_meta` |
| `appPackage/instruction.txt` | Agent system prompt |

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

