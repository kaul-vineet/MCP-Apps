# Building MCP Apps for Microsoft 365

> **Fair Use Notice**
> This article references publicly available technical specifications, documentation, and product names for informational and educational purposes. No substantial verbatim text has been reproduced from any source. All product names, trademarks, and registered trademarks — including Microsoft 365, Copilot, Adaptive Cards, M365 Agents Toolkit, FastMCP, OpenSky Network, and the Model Context Protocol — are the property of their respective owners. Citations for factual claims are listed at the end. The technical findings described are original observations from first-hand development experience.

---

I spent a weekend building a flight tracker that renders an interactive HTML widget inside Microsoft 365 Copilot.

✅ The tool works. The widget renders. You can click a flight row and see live aircraft altitude, speed, and heading — without leaving the chat window.

Here is what I built, how MCP Apps works, how it compares to Adaptive Cards, and what it can unlock in production.

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

## 🔍 What Are MCP Apps?

On **26 January 2026**, Anthropic and OpenAI — two companies that are, in most respects, competitors — jointly published **MCP Apps**, the first official extension to the Model Context Protocol since it launched.

MCP Apps enables MCP servers to deliver **interactive HTML UIs directly inside AI chat hosts** — M365 Copilot, ChatGPT, or anything that implements the spec.

**Before MCP Apps:** every host had incompatible UI mechanisms — ChatGPT, Teams, M365 each did something different.
**After MCP Apps:** write once, render anywhere.

> Production-ready. Not a preview. And almost nobody is talking about it yet.

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
- With Adaptive Cards: click a row → ask a follow-up question → wait for model → receive new card → lose previous state
- With MCP Apps: click a row → one `callTool` call → live data appears inline. No second prompt. No model invocation.

> 💡 **Rule of thumb** — Use Adaptive Cards when data is complete at render time. Use MCP Apps widgets when the UI needs to stay alive after the tool call returns.

---

## 🛠️ Challenges and troubleshooting

Building this on early-stage tooling with sparse documentation involved real friction. The full challenges table — including all undocumented gotchas, error codes, root causes, and fixes — is documented in the repository README under [Critical Troubleshooting → Build and deployment challenges](https://github.com/your-org/flight-tracker-mcp#critical-troubleshooting).

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

That is the gap this article fills.

**The widget rendered. It was worth it.**

---

*Built with: FastMCP · M365 Agents Toolkit · OpenSky Network API · Microsoft 365 Copilot*
*Full guide, code, and diagnostic checklist → [repository README](https://github.com/your-org/flight-tracker-mcp)*

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
