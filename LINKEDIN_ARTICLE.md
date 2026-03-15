# Three things nobody tells you about building MCP widgets for Microsoft 365

> **Fair Use Notice**
> This article references publicly available technical specifications, documentation, and product names for informational and educational purposes. No substantial verbatim text has been reproduced from any source. All product names, trademarks, and registered trademarks — including Microsoft 365, Copilot, Adaptive Cards, M365 Agents Toolkit, FastMCP, OpenSky Network, and the Model Context Protocol — are the property of their respective owners. Citations for factual claims are listed at the end. The three technical findings are original observations from first-hand development experience.

---

I spent a weekend building a flight tracker that renders an interactive HTML widget inside Microsoft 365 Copilot.

✅ The tool works. The widget renders. You can click a flight row and see live aircraft altitude, speed, and heading — without leaving the chat window.

Getting there involved three bugs that are not documented anywhere. That is what this article is about.

---

## ✈️ What the sample app does

The **Flight Tracker** is an MCP server that connects to M365 Copilot as a Declarative Agent. Give it any aircraft's ICAO24 transponder code and it:

| Step | What happens |
|---|---|
| 1️⃣ | Fetches flight history from OpenSky Network (dates, routes, callsigns) |
| 2️⃣ | Renders a **live interactive table** directly inside the Copilot chat |
| 3️⃣ | On clicking any row, **calls back to the MCP server in real time** for live aircraft state |
| 4️⃣ | Shows altitude, speed, heading, on-ground status — inline, no second prompt |
| 5️⃣ | Applies light/dark theming automatically from the M365 host |

**Two tools exposed:**
- `get_flights_by_aircraft` — flight history by date range
- `get_aircraft_state` — live position, altitude, speed, heading

**Three pre-built prompts:**
- `lookup_flights` — flight history for a given date
- `analyse_aircraft` — two-day pattern analysis
- `flight_briefing` — full briefing combining history and live state

**How data flows end to end:**
```
User types prompt
       │
[M365 Copilot LLM]  →  reads tools/list → sees _meta.ui.resourceUri
       │
tools/call  →  get_flights_by_aircraft(icao24, begin_date, end_date)
       │
[server.py]  →  OpenSky OAuth2 token  →  GET /api/flights/aircraft
       │         returns CallToolResult { content, structuredContent }
       │
M365 fetches ui://widget/flights.html  →  renders in sandboxed iframe
       │         injects window.openai.toolOutput = structuredContent
       │
Widget renders flight table
       │
  [User clicks a row]
       │
window.openai.callTool("get_aircraft_state", { icao24 })
       │         → GET /api/states/all
       │
Live state appears inline in the expanded row
```

---

## 🆕 Something genuinely new happened in January

On **26 January 2026**, Anthropic and OpenAI jointly published a specification extension called **MCP Apps**.

Two competitors. One spec. Co-authored together.

The Model Context Protocol already gave AI assistants a standard way to call tools. MCP Apps extends it so tools can return **interactive HTML widgets** that render directly inside the host.

> This is the first official extension to MCP since the protocol launched. Production-ready. Not a preview. And almost nobody is talking about it yet.

---

## 🔍 What Are MCP Apps?

MCP Apps enables MCP servers to deliver interactive HTML UIs **directly inside AI chat hosts** — M365 Copilot, ChatGPT, or anything that implements the spec.

**Before MCP Apps:** every host had incompatible UI mechanisms. ChatGPT did one thing, Teams did another, M365 did a third.

**After MCP Apps:** write once, render anywhere.

### How it works — three entities

```
MCP Server               Host (M365 / ChatGPT)        Widget (sandboxed iframe)
─────────────────        ─────────────────────        ─────────────────────────
tools/list          →    reads _meta.ui.resourceUri
resources/read      →    renders iframe           →    receives structuredContent
tools/call          →    proxies postMessage      ←→   calls back via callTool
                         enforces CSP                  notifies height
```

### Key concepts at a glance

| Concept | What it does |
|---|---|
| `ui://` URI scheme | Widget resource address |
| `text/html;profile=mcp-app` | MIME type telling the host this is a widget |
| `_meta.ui.resourceUri` | On the **tool definition** — links a tool to its widget |
| `structuredContent` | Rich typed data in the tool result; keeps the model context clean |
| `window.openai.toolOutput` | How the widget receives data |
| `window.openai.callTool` | Widget calling back to an MCP tool |
| `window.openai.notifyIntrinsicHeight` | Auto-sizes the iframe |

**What the widget actually is:**
- 🖥️ A live iframe — not a screenshot, not a card
- 🔄 Calls back to your MCP server on user interaction
- 🎨 Responds to light/dark theme from the host
- 📐 Resizes itself to fit content
- 🧠 Runs *inside* the conversation, not alongside it

---

## 🃏 Why this is different from Adaptive Cards

If you have built on M365 or Teams, you have used Adaptive Cards. They work. But they have a fundamental limit.

| | Adaptive Cards | MCP Apps Widget |
|---|---|---|
| **Nature** | Static snapshot | Live running application |
| **State** | Lost on every update | Lives in the widget |
| **Interaction** | New card per action | JS call inside iframe |
| **Context window** | Grows with each card payload | Untouched |
| **Data updates** | Replace the card | Update in place |
| **Layout** | Constrained by JSON schema | Full HTML/CSS control |
| **Portability** | Teams, Outlook, Copilot | Any MCP Apps compliant host |

**The flight tracker example makes this concrete:**
- With Adaptive Cards: click a row → send a new question → wait for model → receive new card → lose previous state
- With MCP Apps: click a row → one `callTool` call → live data appears inline. No second prompt. No model invocation.

> 💡 **Rule of thumb** — Use Adaptive Cards when data is complete at render time. Use MCP Apps widgets when the UI needs to stay alive after the tool call returns.

---

## ⚠️ The three things nobody tells you

### Fix 1 — `_meta` goes on the tool *definition*, not the tool *result*

**What the spec says:** put the widget URI in `_meta.ui.resourceUri`.
**What it doesn't say clearly:** *where* that `_meta` lives.

❌ **Wrong** — in `CallToolResult` (M365 ignores it entirely here)
✅ **Right** — in `tools/list`, on the tool definition

By the time your tool runs, M365 has already decided whether to render a widget. That decision is made at **discovery time**, not execution time.

```python
# ✅ Correct — FastMCP decorator
@mcp.tool(
    meta={"ui": {"resourceUri": "ui://widget/flights.html"}}
)
async def get_flights_by_aircraft(...):
    ...
```

> ⚠️ If you use a static `mcp-tools.json` manifest (required by M365 Agents Toolkit), you must also add `_meta` manually to that file **and** re-provision. Both places. Neither alone is sufficient.

---

### Fix 2 — `mcp-tools.json` is a snapshot, not a live mirror

M365 Agents Toolkit generates `mcp-tools.json` once by interrogating your server. That snapshot is deployed. **It does not update automatically.**

**The trap:**
1. ✅ Fix your server — `_meta` now in `tools/list`
2. ✅ Confirm with MCP Inspector — looks correct
3. ❌ Widget still doesn't render in M365
4. 🔍 Because the *deployed manifest* has the old snapshot with no `_meta`

> 🔁 **Rule:** Re-provision after every structural change to `mcp-tools.json`.

---

### Fix 3 — `window.openai.toolOutput` isn't always what the spec implies

The widget gets data via `window.openai.toolOutput`. The spec implies it contains a `structuredContent` field. In M365, it sometimes delivers `structuredContent` *unwrapped* — the data **is** `toolOutput`, not `toolOutput.structuredContent`.

```javascript
var out = window.openai.toolOutput;
var data = (out && out.structuredContent !== undefined)
  ? out.structuredContent : out;   // handle both formats
render(data);
```

Without this: widget receives data, renders nothing, gives no error.

> Also: `window.openai` is injected **after** your script runs. Poll for it — 30 × 100ms is enough.

---

## 🛠️ Challenges building the sample app

These are the real-world friction points. None are in the getting-started docs.

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
| **Widget state lost on chat re-open** | `ontoolresult` doesn't re-fire for historical messages | No clean solution yet — open issue in the ecosystem |
| **Python/Node.js parity gap** | `@modelcontextprotocol/ext-apps` is TypeScript-only | Python uses FastMCP `meta=` parameter + `window.openai.*` bridge manually |

> 💡 **Strong recommendation:** Build and test the widget entirely with the local `widget_test.html` harness first. Debugging inside the M365 iframe — with no accessible console and a 30-second redeploy cycle — is considerably less pleasant.

---

## 🚀 What this actually unlocks

The flight tracker is a demo. Here is what the same pattern does in production:

| Use case | What the widget does |
|---|---|
| 🎫 **IT service desk** | Live ticket list with per-row escalate button — no portal switch |
| 📋 **Sprint planning** | Reorderable backlog inside the chat; assign and close without leaving |
| 🚨 **Incident response** | Live log viewer where the on-call engineer is already working |
| 💰 **Financial reporting** | Drillable P&L — click a line, see the underlying transactions |
| 🏭 **IoT / operations** | Shop floor sensor widget; acknowledge alerts in chat |
| 🔐 **Security operations** | Alert triage inline; mark false positives, trigger response actions |
| 🗺️ **Field operations** | Live map widget with clickable assets and status overlays |
| 📊 **Executive dashboards** | KPI widget that updates as the conversation refines the filter |

> The common thread: situations where users need to **do something with data**, not just read it. Adaptive Cards show data. MCP Apps widgets let you act on it — in place, without losing context.

---

## 💡 The broader point

MCP Apps is **six weeks old** as I write this (March 2026).

- ✅ Spec is production-ready
- ✅ FastMCP supports it (`meta=` parameter, v1.26+)
- ✅ M365 Agents Toolkit supports the full widget lifecycle
- ❌ Practical knowledge of what breaks and why isn't written down yet

**The three fixes will save you the better part of a day.**
**The challenges table will save you the rest of it.**

The widget rendered. It was worth it.

---

*Built with: FastMCP · M365 Agents Toolkit · OpenSky Network API · Microsoft 365 Copilot*
*Full guide, code, and diagnostic checklist → repository README*

---

## 📚 Sources and references

| Claim | Source |
|---|---|
| MCP Apps announced 26 January 2026; co-developed by Anthropic and OpenAI | [microsoft/mcp-interactiveUI-samples — README](https://github.com/microsoft/mcp-interactiveUI-samples) |
| MCP Apps specification and `_meta.ui.resourceUri` structure | [microsoft/mcp-interactiveUI-samples — M365 Agents Toolkit Instructions](https://github.com/microsoft/mcp-interactiveUI-samples/blob/main/M365-Agents-Toolkit-Instructions.md) |
| `window.openai` injection model; `toolOutput` / `structuredContent` fields; `callTool` API | [microsoft/mcp-interactiveUI-samples — M365 Agents Toolkit Instructions](https://github.com/microsoft/mcp-interactiveUI-samples/blob/main/M365-Agents-Toolkit-Instructions.md) |
| FastMCP `meta=` parameter introduced in v1.26 | [jlowin/fastmcp](https://github.com/jlowin/fastmcp) |
| Adaptive Cards schema and rendering model | [adaptivecards.io — Documentation](https://adaptivecards.io/documentation/) |
| M365 Agents Toolkit `mcp-tools.json` provisioning lifecycle | [microsoft/mcp-interactiveUI-samples — M365 Agents Toolkit Instructions](https://github.com/microsoft/mcp-interactiveUI-samples/blob/main/M365-Agents-Toolkit-Instructions.md) |
| OpenSky Network flight history and live state APIs | [opensky-network.org — REST API Documentation](https://openskynetwork.github.io/opensky-api/) |
| M365 supported widget APIs (`toolOutput`, `callTool`, `notifyIntrinsicHeight`, `theme`) | [Microsoft Learn — UI widgets for declarative agents](https://learn.microsoft.com/en-us/microsoft-365-copilot/extensibility/declarative-agent-ui-widgets) |

*All URLs accessed March 2026.*
