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
- [Code Walkthrough](#code-walkthrough)
- [Prerequisites](#prerequisites)
- [Set-up](#set-up)
- [Critical Troubleshooting](#critical-troubleshooting)
- [Platform Constraints and Gaps](#platform-constraints-and-gaps)
- [Quick Reference](#quick-reference)
- [References](#references)

---

## ✈️ Flight Tracker

The **Flight Tracker** is an MCP server that connects to M365 Copilot as a Declarative Agent. It supports three workflows, each rendering a live interactive widget inside the Copilot chat:

| Workflow | Trigger | What happens |
|---|---|---|
| ✈️ **Aircraft history** | ICAO24 transponder code | Fetches flight history → renders table → footer button fetches live state |
| 🛫 **Airport departures** | Airport code + date | Lists departing flights → click a row → live aircraft state inline |
| 🛬 **Airport arrivals** | Airport code + date | Lists arriving flights → click a row → historical flight track inline |

All three workflows:
- Render a **live interactive widget** directly inside the Copilot chat — no portal switch, no second prompt
- Apply light/dark theming automatically from the M365 host
- Suppress model text — the widget is the response
- Mark viewed rows **green with a ✓** — visual record of what has been checked

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

*Flow 1 — Aircraft history → live state*
```
User: "Show flights for 3c675a"
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
Widget renders flight table  →  [User clicks "Check Live State →"]
       │
window.openai.callTool("get_aircraft_state", { icao24 })  →  GET /api/states/all
       │
Live state card appears in widget footer
```

*Flow 2 — Airport departures → live state*
```
User: "Show departures from EGLL yesterday"
       │
tools/call  →  get_airport_departures(airport, begin_date, end_date)
               → GET /api/flights/departure
               → structuredContent { type: "departures", flights: [{ icao24, first_seen_ts }] }
       │
Widget renders departures table  →  [User clicks a row]
       │
window.openai.callTool("get_aircraft_state", { icao24 })
       │
Live state expands inline  →  row turns green with ✓
```

*Flow 3 — Airport arrivals → flight track*
```
User: "Show arrivals at KJFK yesterday"
       │
tools/call  →  get_airport_arrivals(airport, begin_date, end_date)
               → GET /api/flights/arrival
               → structuredContent { type: "arrivals", flights: [{ icao24, first_seen_ts }] }
       │
Widget renders arrivals table  →  [User clicks a row]
       │
window.openai.callTool("get_aircraft_track", { icao24, time: first_seen_ts })
               → GET /api/tracks/all
       │
Track detail expands inline  →  row turns green with ✓
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
├── .env.example           # Template — copy to .env and fill in credentials
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

## Code Walkthrough

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
- `lookup_flights` — flight history for a given date
- `analyse_aircraft` — two-day pattern analysis
- `flight_briefing` — full briefing combining history and live state
- `lookup_departures` — departures from an airport on a given date; offers live state follow-up
- `lookup_arrivals` — arrivals at an airport on a given date; offers track follow-up with `first_seen_ts`

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

**Checked row UX** — after a row's detail data loads, the row turns green and shows `✓`. The state persists when the row is collapsed.

Key behaviours:
- Receives data via `window.openai.toolOutput`; dispatches to the correct view via `render()`
- `toggleRow(idx)` — branches on `viewMode` to call `get_aircraft_state` or `get_aircraft_track`
- `fetchLiveState()` — aircraft view footer button; calls `get_aircraft_state` for the whole aircraft
- `renderDetail` / `renderTrackDetail` / `renderStateCard` — view-specific rendering functions
- Light/dark theming via CSS custom properties applied from `window.openai.theme`
- Auto-height notification via `window.openai.notifyIntrinsicHeight`
- Polling pattern to handle M365's delayed injection of `window.openai`

> 📝 **Note** — Developers extending the widget should review `render()`, `toggleRow()`, `checkedRows`, and the `--color-*` CSS variables for theming.

---

### `widget_test.html` — Local Test Harness

A standalone HTML page that simulates M365/ChatGPT postMessage data delivery. Allows the widget to be tested entirely locally — no live server, no tunnel, no M365 account required. Includes mock data for all three view modes, a dark/light toggle, and an event log panel. Use this before every M365 deployment.

**Three mock send buttons:**

| Button | Colour | Simulates |
|---|---|---|
| Send Mock Flights | Blue | `get_flights_by_aircraft` — aircraft view, 3 rows |
| Send Mock Departures | Green | `get_airport_departures` — EGLL, 3 rows |
| Send Mock Arrivals | Orange | `get_airport_arrivals` — KJFK, 3 rows |

The harness intercepts all `callTool` requests: `get_aircraft_state` → mock state, `get_aircraft_track` → mock track.

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

Copy `.env.example` to `.env` and populate your OpenSky credentials (obtained in Step 4):

```bash
cp .env.example .env
# then edit .env with your OPENSKY_CLIENT_ID and OPENSKY_CLIENT_SECRET
```

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

Register at [opensky-network.org](https://opensky-network.org) → **My OpenSky** → create an OAuth2 client application → note the `client_id` and `client_secret`.

Add them to your `.env` file (created in Step 2):

```ini
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

### Step 7 — Validate the Widget (`widget.html`)

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
4. Select all tools → authentication: **None** (development mode)
5. Confirm the runtime URL in `ai-plugin.json` matches the named tunnel URL
6. Update `mcp-tools.json` — **see [Issue 2](#issue-2----mcp-toolsjson-must-include-_meta) before proceeding**
7. Agents Toolkit → Lifecycle → **Provision**
8. Test at [https://m365.cloud.microsoft/chat](https://m365.cloud.microsoft/chat)

**Using the Flight Tracker:**

1. Click the agent picker and select **Flight Tracker**
2. Try an aircraft prompt — e.g. *Show me flights for aircraft 3C675A on 15 January 2024* → flight table renders; click "Check Live State →" in the footer
3. Try an airport prompt — e.g. *Show departures from Heathrow yesterday* → departures table renders; click any row for live state
4. Try an arrivals prompt — e.g. *Show arrivals at JFK yesterday* → arrivals table renders; click any row for the flight track
5. Viewed rows turn green with ✓ — your checked flights are visually tracked
6. Try pre-built prompts: *Analyse the flying pattern for 3C675A over the last 2 days* or *Show arrivals at EDDF on 15 March 2026*

> 📝 **ICAO24 codes** are 6-character hex identifiers (e.g. `3c675a`) that uniquely identify an aircraft. Find them on FlightRadar24 or FlightAware by searching a tail number or flight. **ICAO airport codes** (e.g. `EGLL`, `KJFK`, `EDDF`) identify airports.

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

### Build and deployment challenges

Real-world friction points encountered during development. None are covered in the getting-started documentation.

| Challenge | What happened | Fix |
|---|---|---|
| **Widget invisible in M365** | `background: transparent` renders the iframe invisible | Set `--color-bg: #ffffff` (light) and `#1a1a1a` (dark) explicitly in CSS |
| **"Loading flight data..." stuck** | `window.openai` injected after script runs | Poll 30 × 100ms until available |
| **WAM Error 3399614466** | `devtunnel user login` fails on Windows via auth broker | Use `devtunnel user login -d` (device code flow) |
| **Ephemeral tunnel URL breaks manifest** | Named tunnel shows ephemeral URL at startup | Use only the permanent hostname in `ai-plugin.json` |
| **OpenSky 403 Forbidden** | Wrong token endpoint | Use Keycloak realm URL: `auth.opensky-network.org/auth/realms/opensky-network/...` |
| **OpenSky 401 Unauthorised** | Tried HTTP Basic Auth | Use OAuth2 `grant_type=client_credentials` + Bearer token |
| **`outputTemplate: ""` kills the widget** | Added to suppress model text; M365 abandons widget rendering entirely | Remove it; use `instruction.txt` instead |
| **No console in M365 iframe** | Can't open DevTools inside the hosted widget | Test fully with `widget_test.html` locally before deploying to M365 |

---

## Platform Constraints and Gaps

Understanding what is **by design** versus what is a **genuine platform gap** saves significant debugging time.

### By Design — Sandbox Architecture

These are intentional security constraints of the MCP Apps model, not bugs or missing features. Do not attempt to work around them — the correct pattern is to route all external calls through the MCP server.

| Constraint | Why by design |
|---|---|
| **Widget cannot make direct authenticated API calls** | Widget iframe is credential-free by design — the MCP server is the trust boundary |
| **Widget state is message-scoped** | Each tool result is an isolated, reproducible rendering — `setWidgetState` persists state within a single message's widget only |
| **Widget state lost on conversation re-open** | `ontoolresult` does not re-fire for historical messages — by design, not a bug |
| **No file upload/download from widget** | Widgets are data viewers — file handling belongs in the MCP server |
| **No modal dialogs** | Host controls the UX chrome — widgets cannot break out of the iframe |
| **No OAuth redirects in widget** | `redirect_domains` CSP unsupported — prevents credential exposure inside the sandboxed iframe |
| **CSP/CORS origin for `callTool`** | Widget runs at `{hashed-domain}.widget-renderer.usercontent.microsoft.com` — CORS must allow this origin. Use the [Widget Host URL Generator](https://aka.ms/mcpwidgeturlgenerator) |

**Correct pattern for all external calls:**
```
Widget → callTool → MCP Server (authenticated) → External API
```

### Genuine Platform Gaps

These are real limitations where M365 falls short of the spec, of ChatGPT's implementation, or of other M365 extensibility technologies.

| Gap | Impact |
|---|---|
| **M365 uses OpenAI Apps SDK, not MCP Apps open spec** | Microsoft Learn states *"Support for MCP Apps is coming soon"* — current support is the OpenAI Apps SDK bridge (`window.openai.*`). Enterprises building now depend on an informal bridge, not the open standard. |
| **`widgetSessionId` unsupported in M365** | Supported in ChatGPT, missing in M365. Without it, widget state resets on every tool call — even within the same conversation. Multi-step workflows require a backend to persist state between tool calls. |
| **`mcp-tools.json` is a manual step** | ATK snapshots `tools/list` into a static file at provision time, stripping `_meta`. Every tool change requires manual file edit + re-provision. All other M365 extensibility technologies (API plugins, Graph connectors) fetch definitions live. Acknowledged as temporary by Microsoft. |
| **No iframe debug tooling** | Developer Mode shows orchestrator layer only — no widget-level console, no JS errors, no rendering visibility. Requires a local test harness for all widget debugging. |
| **Python/Node.js parity gap** | `@modelcontextprotocol/ext-apps` is TypeScript-only. Python developers must hand-roll the `window.openai.*` bridge — no `useApp()` hook equivalent. |
| **`ext-apps` capability not announced by Python SDK** | MCP Inspector shows no MCP Apps capability for Python servers — currently harmless but may matter as hosts gate features behind capability negotiation. |

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
| `.env.example` | Credential template — copy to `.env` and fill in values (`.env` is gitignored) |
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

