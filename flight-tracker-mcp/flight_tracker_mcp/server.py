import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import uvicorn
from dotenv import load_dotenv
from mcp import types
from mcp.server.fastmcp import FastMCP
from mcp.types import PromptMessage, TextContent
from starlette.middleware.cors import CORSMiddleware

load_dotenv()

# ── Widget ─────────────────────────────────────────────────────────────────────

WIDGET_URI = "ui://widget/flights.html"
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"
WIDGET_HTML = (Path(__file__).parent / "web" / "widget.html").read_text(encoding="utf-8")

# ── MCP Server ─────────────────────────────────────────────────────────────────

mcp = FastMCP("flight-tracker")


@mcp.resource(WIDGET_URI, mime_type=RESOURCE_MIME_TYPE)
async def flight_widget() -> str:
    """UI widget for displaying flight results."""
    return WIDGET_HTML


# ── OpenSky API ────────────────────────────────────────────────────────────────

async def get_opensky_token() -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": os.environ["OPENSKY_CLIENT_ID"],
                "client_secret": os.environ["OPENSKY_CLIENT_SECRET"],
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


def format_unix(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


# ── Tool ───────────────────────────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Retrieve flight history for an aircraft by its ICAO 24-bit transponder address. "
        "icao24 must be a 6-character lowercase hex string (e.g. '3c675a'). "
        "Date range must not exceed 2 days. "
        "Current-day and recent historical flights are available; use today's date for the latest departures."
    ),
    meta={"ui": {"resourceUri": WIDGET_URI}},
)
async def get_flights_by_aircraft(
    icao24: str,
    begin_date: str,
    end_date: str,
) -> types.CallToolResult:
    """
    Args:
        icao24:     Aircraft transponder address, e.g. '3c675a'
        begin_date: Start date YYYY-MM-DD, e.g. '2024-01-15'
        end_date:   End date YYYY-MM-DD (max 2 days from begin_date)
    """
    begin = int(
        datetime.fromisoformat(begin_date).replace(tzinfo=timezone.utc).timestamp()
    )
    end = int(
        datetime.fromisoformat(end_date + "T23:59:59").replace(tzinfo=timezone.utc).timestamp()
    )

    if end - begin > 2 * 24 * 3600:
        raise ValueError("Date range cannot exceed 2 days.")

    token = await get_opensky_token()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://opensky-network.org/api/flights/aircraft",
                params={"icao24": icao24, "begin": begin, "end": end},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 404:
                flights_raw = []
            else:
                resp.raise_for_status()
                try:
                    flights_raw = resp.json() if resp.content else []
                except ValueError:
                    flights_raw = []
    except httpx.TimeoutException:
        flights_raw = []

    flights = [
        {
            "callsign": (f.get("callsign") or "").strip() or None,
            "from": f.get("estDepartureAirport"),
            "to": f.get("estArrivalAirport"),
            "departed": format_unix(f["firstSeen"]),
            "arrived": format_unix(f["lastSeen"]),
        }
        for f in flights_raw
    ]

    structured_content = {
        "icao24": icao24,
        "total_flights": len(flights),
        "flights": flights,
    }

    summary = (
        f"No flights found for {icao24} between {begin_date} and {end_date}."
        if not flights
        else f"Found {len(flights)} flight(s) for {icao24}. See the widget for details."
    )

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structuredContent=structured_content,
    )


# ── Tool: get_aircraft_state ───────────────────────────────────────────────────

def heading_to_compass(deg: float) -> str:
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[round(deg / 45) % 8]


@mcp.tool(
    description=(
        "Get the last known live state of an aircraft: position, altitude, speed, heading. "
        "icao24 must be a 6-character lowercase hex string (e.g. '3c675a'). "
        "Returns current live data — not historical position at time of a past flight."
    ),
    meta={"ui": {"resourceUri": WIDGET_URI}},
)
async def get_aircraft_state(icao24: str) -> types.CallToolResult:
    """
    Args:
        icao24: Aircraft transponder address, e.g. '3c675a'
    """
    token = await get_opensky_token()

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://opensky-network.org/api/states/all",
            params={"icao24": icao24},
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 404:
            states = []
        else:
            resp.raise_for_status()
            states = (resp.json().get("states") or [])

    if not states:
        structured: dict = {"icao24": icao24, "found": False}
        summary = f"No live state found for {icao24}. It may be on the ground or out of coverage."
    else:
        s = states[0]
        vel_ms    = s[9]
        alt_m     = s[7]
        track     = s[10]
        structured = {
            "icao24":         icao24,
            "found":          True,
            "callsign":       (s[1] or "").strip() or None,
            "origin_country": s[2],
            "latitude":       s[6],
            "longitude":      s[5],
            "altitude_m":     round(alt_m)          if alt_m  is not None else None,
            "altitude_ft":    round(alt_m * 3.281)  if alt_m  is not None else None,
            "on_ground":      s[8],
            "velocity_kmh":   round(vel_ms * 3.6)   if vel_ms is not None else None,
            "heading_deg":    round(track)           if track  is not None else None,
            "heading_compass":heading_to_compass(track) if track is not None else None,
            "vertical_rate":  s[11],
            "last_contact":   format_unix(s[4])     if s[4]   is not None else None,
        }
        status  = "on the ground" if s[8] else "airborne"
        summary = (
            f"Aircraft {icao24} is {status}. "
            f"Alt: {structured['altitude_ft']}ft | "
            f"Speed: {structured['velocity_kmh']} km/h | "
            f"Heading: {structured['heading_deg']}° {structured['heading_compass']}"
        )

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structuredContent=structured,
    )


# ── Tool: get_airport_departures ───────────────────────────────────────────────

@mcp.tool(
    description=(
        "Retrieve flights departing from an airport within a date range. "
        "airport must be an ICAO airport code (e.g. 'EGLL' for Heathrow, 'KJFK' for JFK). "
        "Date range must not exceed 1 day. "
        "Current-day and recent historical flights are available; use today's date for the latest departures."
    ),
    meta={"ui": {"resourceUri": WIDGET_URI}},
)
async def get_airport_departures(
    airport: str,
    begin_date: str,
    end_date: str,
) -> types.CallToolResult:
    """
    Args:
        airport:    ICAO airport code, e.g. 'EGLL'
        begin_date: Start date YYYY-MM-DD, e.g. '2024-01-15'
        end_date:   End date YYYY-MM-DD (same as begin_date for a single day)
    """
    begin = int(datetime.fromisoformat(begin_date).replace(tzinfo=timezone.utc).timestamp())
    end = int(datetime.fromisoformat(end_date + "T23:59:59").replace(tzinfo=timezone.utc).timestamp())

    if end - begin > 24 * 3600:
        raise ValueError("Date range cannot exceed 1 day for airport queries.")

    token = await get_opensky_token()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://opensky-network.org/api/flights/departure",
                params={"airport": airport.upper(), "begin": begin, "end": end},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 404:
                flights_raw = []
            else:
                resp.raise_for_status()
                try:
                    flights_raw = resp.json() if resp.content else []
                except ValueError:
                    flights_raw = []
    except httpx.TimeoutException:
        flights_raw = []

    flights = [
        {
            "icao24":        f.get("icao24"),
            "callsign":      (f.get("callsign") or "").strip() or None,
            "from":          f.get("estDepartureAirport"),
            "to":            f.get("estArrivalAirport"),
            "departed":      format_unix(f["firstSeen"]),
            "arrived":       format_unix(f["lastSeen"]),
            "first_seen_ts": f["firstSeen"],
        }
        for f in flights_raw
    ]

    structured_content = {
        "type":          "departures",
        "airport":       airport.upper(),
        "total_flights": len(flights),
        "flights":       flights,
    }

    summary = (
        f"No departures found from {airport.upper()} between {begin_date} and {end_date}."
        if not flights
        else f"Found {len(flights)} departure(s) from {airport.upper()}. See the widget for details."
    )

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structuredContent=structured_content,
    )


# ── Tool: get_airport_arrivals ─────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Retrieve flights arriving at an airport within a date range. "
        "airport must be an ICAO airport code (e.g. 'EGLL' for Heathrow, 'KJFK' for JFK). "
        "Date range must not exceed 1 day. "
        "Use yesterday's date — same-day arrival data is not yet available as OpenSky processes arrivals after flights complete."
    ),
    meta={"ui": {"resourceUri": WIDGET_URI}},
)
async def get_airport_arrivals(
    airport: str,
    begin_date: str,
    end_date: str,
) -> types.CallToolResult:
    """
    Args:
        airport:    ICAO airport code, e.g. 'EGLL'
        begin_date: Start date YYYY-MM-DD, e.g. '2024-01-15'
        end_date:   End date YYYY-MM-DD (same as begin_date for a single day)
    """
    begin = int(datetime.fromisoformat(begin_date).replace(tzinfo=timezone.utc).timestamp())
    end = int(datetime.fromisoformat(end_date + "T23:59:59").replace(tzinfo=timezone.utc).timestamp())

    if end - begin > 24 * 3600:
        raise ValueError("Date range cannot exceed 1 day for airport queries.")

    token = await get_opensky_token()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://opensky-network.org/api/flights/arrival",
                params={"airport": airport.upper(), "begin": begin, "end": end},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 404:
                flights_raw = []
            else:
                resp.raise_for_status()
                try:
                    flights_raw = resp.json() if resp.content else []
                except ValueError:
                    flights_raw = []
    except httpx.TimeoutException:
        flights_raw = []

    flights = [
        {
            "icao24":        f.get("icao24"),
            "callsign":      (f.get("callsign") or "").strip() or None,
            "from":          f.get("estDepartureAirport"),
            "to":            f.get("estArrivalAirport"),
            "departed":      format_unix(f["firstSeen"]),
            "arrived":       format_unix(f["lastSeen"]),
            "first_seen_ts": f["firstSeen"],
        }
        for f in flights_raw
    ]

    structured_content = {
        "type":          "arrivals",
        "airport":       airport.upper(),
        "total_flights": len(flights),
        "flights":       flights,
    }

    from datetime import date
    today = date.today().isoformat()
    if not flights:
        if begin_date >= today:
            summary = (
                f"No arrivals found at {airport.upper()} for {begin_date}. "
                f"Same-day arrival data is not yet available — OpenSky processes arrivals after flights complete. "
                f"Try yesterday's date instead."
            )
        else:
            summary = f"No arrivals found at {airport.upper()} between {begin_date} and {end_date}."
    else:
        summary = f"Found {len(flights)} arrival(s) at {airport.upper()}. See the widget for details."

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structuredContent=structured_content,
    )


# ── Tool: get_aircraft_track ───────────────────────────────────────────────────

@mcp.tool(
    description=(
        "Get the flight track (waypoints) for an aircraft. "
        "icao24 must be a 6-character lowercase hex string (e.g. '3c675a'). "
        "time is a Unix timestamp within the flight's time window to retrieve a specific "
        "historical track; pass 0 to retrieve the most recent track. "
        "Use the first_seen_ts from a departure or arrival result to get the track for that flight."
    ),
)
async def get_aircraft_track(icao24: str, time: int = 0) -> types.CallToolResult:
    """
    Args:
        icao24: Aircraft transponder address, e.g. '3c675a'
        time:   Unix timestamp within the flight window, or 0 for most recent track
    """
    token = await get_opensky_token()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://opensky-network.org/api/tracks/all",
                params={"icao24": icao24, "time": time},
                headers={"Authorization": f"Bearer {token}"},
            )
            if resp.status_code == 404:
                structured: dict = {"icao24": icao24, "found": False}
                summary = f"No track found for {icao24}."
            else:
                resp.raise_for_status()
                try:
                    data = resp.json() if resp.content else {}
                except ValueError:
                    data = {}
                path = data.get("path") or []
                first = path[0]  if path else None
                last  = path[-1] if path else None
                structured = {
                    "icao24":          icao24,
                    "found":           True,
                    "callsign":        (data.get("callsign") or "").strip() or None,
                    "start_time":      format_unix(data["startTime"]) if data.get("startTime") else None,
                    "end_time":        format_unix(data["endTime"])   if data.get("endTime")   else None,
                    "waypoints":       len(path),
                    "first_position":  {"lat": first[1], "lon": first[2]} if first else None,
                    "last_position":   {"lat": last[1],  "lon": last[2]}  if last  else None,
                }
                summary = (
                    f"Track for {icao24} ({structured['callsign'] or 'unknown callsign'}): "
                    f"{len(path)} waypoints from {structured['start_time']} to {structured['end_time']}."
                )
    except httpx.TimeoutException:
        structured = {"icao24": icao24, "found": False}
        summary = f"No track found for {icao24} (OpenSky timed out)."

    return types.CallToolResult(
        content=[types.TextContent(type="text", text=summary)],
        structuredContent=structured,
    )


# ── Prompts ────────────────────────────────────────────────────────────────────

@mcp.prompt()
def lookup_flights(icao24: str, date: str) -> list[PromptMessage]:
    """
    Look up all flights for an aircraft on a specific date.
    Args:
        icao24: Aircraft transponder address, e.g. '3c675a'
        date:   Date in YYYY-MM-DD format, e.g. '2024-01-15'
    """
    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=(
                    f"Show me all flights for aircraft {icao24} on {date}. "
                    f"Call get_flights_by_aircraft with icao24='{icao24}', "
                    f"begin_date='{date}', end_date='{date}'. "
                    f"Present the results clearly and offer to show the live state "
                    f"for any of the flights."
                ),
            ),
        )
    ]


@mcp.prompt()
def analyse_aircraft(icao24: str) -> list[PromptMessage]:
    """
    Fetch the last 2 days of flights for an aircraft and analyse its pattern.
    Args:
        icao24: Aircraft transponder address, e.g. '3c675a'
    """
    today        = datetime.now(tz=timezone.utc).date()
    two_days_ago = today - timedelta(days=2)
    yesterday    = today - timedelta(days=1)

    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=(
                    f"Analyse the recent flying pattern for aircraft {icao24}. "
                    f"Call get_flights_by_aircraft with icao24='{icao24}', "
                    f"begin_date='{two_days_ago}', end_date='{yesterday}'. "
                    f"Then summarise: how many flights, which routes, "
                    f"busiest departure airport, total air time if calculable, "
                    f"and any notable patterns. "
                    f"Finally call get_aircraft_state to show where the aircraft is right now."
                ),
            ),
        )
    ]


@mcp.prompt()
def flight_briefing(icao24: str, date: str) -> list[PromptMessage]:
    """
    Full briefing for an aircraft on a given date: flights + live state + analysis.
    Args:
        icao24: Aircraft transponder address, e.g. '3c675a'
        date:   Date in YYYY-MM-DD format, e.g. '2024-01-15'
    """
    return [
        PromptMessage(
            role="system",
            content=TextContent(
                type="text",
                text=(
                    "You are a flight data analyst. When presenting flight information: "
                    "1. Always show the widget for visual data. "
                    "2. Convert ICAO airport codes to full names where known. "
                    "3. Calculate flight duration from departed/arrived times. "
                    "4. Express altitude in both feet and metres. "
                    "5. Express speed in both km/h and knots (divide km/h by 1.852). "
                    "6. Indicate climb/descent from vertical_rate (positive=climbing, negative=descending)."
                ),
            ),
        ),
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=(
                    f"Give me a full flight briefing for aircraft {icao24} on {date}. "
                    f"Step 1: Call get_flights_by_aircraft with icao24='{icao24}', "
                    f"begin_date='{date}', end_date='{date}' and show the flight table. "
                    f"Step 2: Call get_aircraft_state with icao24='{icao24}' to show current position. "
                    f"Step 3: Provide a written summary covering routes flown, total flights, "
                    f"flight durations, and current aircraft status."
                ),
            ),
        ),
    ]


@mcp.prompt()
def lookup_departures(airport: str, date: str) -> list[PromptMessage]:
    """
    Look up all departures from an airport on a specific date.
    Args:
        airport: ICAO airport code, e.g. 'EGLL'
        date:    Date in YYYY-MM-DD format, e.g. '2024-01-15'
    """
    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=(
                    f"Show me all departures from airport {airport.upper()} on {date}. "
                    f"Call get_airport_departures with airport='{airport.upper()}', "
                    f"begin_date='{date}', end_date='{date}'. "
                    f"Present the results clearly. For any flight of interest, offer to show "
                    f"its live state by calling get_aircraft_state with the flight's icao24."
                ),
            ),
        )
    ]


@mcp.prompt()
def lookup_arrivals(airport: str, date: str) -> list[PromptMessage]:
    """
    Look up all arrivals at an airport on a specific date.
    Args:
        airport: ICAO airport code, e.g. 'EGLL'
        date:    Date in YYYY-MM-DD format, e.g. '2024-01-15'
    """
    return [
        PromptMessage(
            role="user",
            content=TextContent(
                type="text",
                text=(
                    f"Show me all arrivals at airport {airport.upper()} on {date}. "
                    f"Call get_airport_arrivals with airport='{airport.upper()}', "
                    f"begin_date='{date}', end_date='{date}'. "
                    f"Present the results clearly. For any flight of interest, offer to show "
                    f"its track by calling get_aircraft_track with the flight's icao24 and first_seen_ts as time."
                ),
            ),
        )
    ]


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    port = int(os.environ.get("PORT", 3000))
    cors_origins = os.environ.get("CORS_ORIGINS", "*").split(",")

    app = mcp.streamable_http_app()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "mcp-session-id"],
    )
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
