"""
Agent tools for search, weather, directions, local time, and currency exchange.

Each tool is a Strands @tool decorated function that the agent can invoke.
Tools are kept in this separate module so they can be:
- Reused across different agents
- Tested independently
- Expanded into multiple files as the tool list grows

All tool log messages are prefixed with [Tool] for easy filtering in debug.log:
    grep "\\[Tool\\]" debug.log
"""

import json
import logging
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from ddgs import DDGS
from strands.tools.decorator import tool


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# Constants
NOMINATIM_BASE_URL = "https://nominatim.openstreetmap.org/search"
OSRM_BASE_URL = "https://router.project-osrm.org/route/v1/driving"
OPEN_METEO_BASE_URL = "https://api.open-meteo.com/v1/forecast"
NOMINATIM_USER_AGENT = "simple-agent-evals/1.0"
HTTP_TIMEOUT_SECONDS = 10
FRANKFURTER_BASE_URL = "https://api.frankfurter.app/latest"

# City name (lowercase) -> IANA timezone id for get_current_time
_CITY_TO_TIMEZONE: dict[str, str] = {
    "tokyo": "Asia/Tokyo",
    "new york": "America/New_York",
    "new york city": "America/New_York",
    "nyc": "America/New_York",
    "manhattan": "America/New_York",
    "brooklyn": "America/New_York",
    "london": "Europe/London",
    "paris": "Europe/Paris",
    "berlin": "Europe/Berlin",
    "sydney": "Australia/Sydney",
    "chicago": "America/Chicago",
    "los angeles": "America/Los_Angeles",
    "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles",
    "washington dc": "America/New_York",
    "washington": "America/New_York",
    "miami": "America/New_York",
    "denver": "America/Denver",
    "dubai": "Asia/Dubai",
    "singapore": "Asia/Singapore",
    "hong kong": "Asia/Hong_Kong",
    "mumbai": "Asia/Kolkata",
    "moscow": "Europe/Moscow",
    "toronto": "America/Toronto",
    "mexico city": "America/Mexico_City",
    "sao paulo": "America/Sao_Paulo",
}


# ---------------------------------------------------------------------------
# Private helpers (used by the public tool functions below)
# ---------------------------------------------------------------------------


def _resolve_city_timezone(
    city: str
) -> str:
    """
    Map a user-provided city name to an IANA timezone identifier.

    Args:
        city: City or region name (e.g. 'Tokyo', 'New York')

    Returns:
        IANA timezone string

    Raises:
        ValueError: if the city is not in the mapping
    """
    key = city.strip().lower()
    if not key:
        raise ValueError("City name is empty")
    if key not in _CITY_TO_TIMEZONE:
        raise ValueError(
            f"Unknown city for timezone lookup: {city!r}. "
            f"Try a major city (e.g. Tokyo, London, New York, Sydney)."
        )
    return _CITY_TO_TIMEZONE[key]


def _format_utc_offset(
    dt: datetime
) -> str:
    """Format datetime's UTC offset as +HH:MM or -HH:MM."""
    s = dt.strftime("%z")
    if not s or s == "+0000":
        return "+00:00"
    sign = s[0]
    hh, mm = s[1:3], s[3:5]
    return f"{sign}{hh}:{mm}"


def _geocode_location(
    place_name: str
) -> dict:
    """
    Convert a place name to latitude/longitude using Nominatim.

    Args:
        place_name: Name of the place to geocode

    Returns:
        Dictionary with lat, lon, and display_name
    """
    logger.info(f"[Tool] Geocoding location: {place_name}")

    response = requests.get(
        NOMINATIM_BASE_URL,
        params={
            "q": place_name,
            "format": "json",
            "limit": 1,
        },
        headers={"User-Agent": NOMINATIM_USER_AGENT},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    results = response.json()

    if not results:
        raise ValueError(f"Could not find location: {place_name}")

    result = results[0]
    logger.info(f"[Tool] Geocoded '{place_name}' to: {result['display_name']}")

    return {
        "lat": float(result["lat"]),
        "lon": float(result["lon"]),
        "display_name": result["display_name"],
    }


def _format_duration(
    duration_seconds: float
) -> str:
    """
    Format duration in seconds to a human-readable string.

    Args:
        duration_seconds: Duration in seconds

    Returns:
        Formatted string like '1 hour 23 minutes'
    """
    hours = int(duration_seconds // 3600)
    minutes = int((duration_seconds % 3600) // 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if not parts:
        parts.append("less than 1 minute")

    return " ".join(parts)


def _format_distance(
    distance_meters: float
) -> str:
    """
    Format distance in meters to miles.

    Args:
        distance_meters: Distance in meters

    Returns:
        Formatted string like '15.3 miles'
    """
    miles = distance_meters / 1609.34
    return f"{miles:.1f} miles"


# ---------------------------------------------------------------------------
# Public tool functions (registered with the Strands agent)
# ---------------------------------------------------------------------------


@tool
def duckduckgo_search(
    query: str,
    max_results: int = 5
) -> str:
    """
    Search DuckDuckGo for the given query. Use this for current events,
    news, general information, or any topic that requires web search.

    Args:
        query: The search query string
        max_results: Maximum number of results to return

    Returns:
        JSON string containing search results
    """
    try:
        logger.info(f"[Tool] duckduckgo_search: query='{query}', max_results={max_results}")

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))

        logger.info(f"[Tool] duckduckgo_search: found {len(results)} results")
        return json.dumps(results, indent=2)

    except Exception as e:
        logger.error(f"[Tool] duckduckgo_search failed: {e}")
        return json.dumps({"error": str(e)})


@tool
def get_weather(
    location: str
) -> str:
    """
    Get current weather for a location using Open-Meteo API (free, no API key needed).
    Use this when users ask about weather, temperature, or conditions in a place.

    Args:
        location: Name of the city or place (e.g. 'Washington DC', 'Tokyo', 'London')

    Returns:
        JSON string with current weather data including temperature, conditions, wind, humidity
    """
    try:
        logger.info(f"[Tool] get_weather: location='{location}'")

        geo = _geocode_location(location)

        response = requests.get(
            OPEN_METEO_BASE_URL,
            params={
                "latitude": geo["lat"],
                "longitude": geo["lon"],
                "current_weather": "true",
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code",
                "temperature_unit": "fahrenheit",
                "wind_speed_unit": "mph",
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        current = data.get("current", data.get("current_weather", {}))

        weather_info = {
            "location": geo["display_name"],
            "temperature_f": current.get("temperature_2m", current.get("temperature")),
            "wind_speed_mph": current.get("wind_speed_10m", current.get("windspeed")),
            "humidity_percent": current.get("relative_humidity_2m"),
            "weather_code": current.get("weather_code", current.get("weathercode")),
        }

        logger.info(f"[Tool] get_weather: {location} -> {weather_info['temperature_f']}F")
        return json.dumps(weather_info, indent=2)

    except Exception as e:
        logger.error(f"[Tool] get_weather failed: {e}")
        return json.dumps({"error": str(e)})


@tool
def get_directions(
    origin: str,
    destination: str
) -> str:
    """
    Get driving directions between two locations using OSRM (free, no API key needed).
    Use this when users ask about travel time, distance, or directions between places.

    Args:
        origin: Starting location name (e.g. 'Washington DC', 'WAS17 Amazon office Arlington VA')
        destination: Destination location name (e.g. 'Georgetown University', 'New York City')

    Returns:
        JSON string with route info including distance, duration, and turn-by-turn steps
    """
    try:
        logger.info(f"[Tool] get_directions: '{origin}' -> '{destination}'")

        origin_geo = _geocode_location(origin)
        # Small delay to respect Nominatim rate limits
        time.sleep(1)
        dest_geo = _geocode_location(destination)

        coords = f"{origin_geo['lon']},{origin_geo['lat']};{dest_geo['lon']},{dest_geo['lat']}"
        url = f"{OSRM_BASE_URL}/{coords}"

        response = requests.get(
            url,
            params={
                "overview": "false",
                "steps": "true",
                "geometries": "geojson",
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            logger.warning("[Tool] get_directions: no route found")
            return json.dumps({"error": "No route found between these locations"})

        route = data["routes"][0]

        steps = []
        for leg in route.get("legs", []):
            for step in leg.get("steps", []):
                if step.get("name") and step.get("maneuver", {}).get("type") != "depart":
                    steps.append({
                        "instruction": f"{step['maneuver'].get('type', '')} onto {step['name']}",
                        "distance": _format_distance(step["distance"]),
                        "duration": _format_duration(step["duration"]),
                    })

        directions_info = {
            "origin": origin_geo["display_name"],
            "destination": dest_geo["display_name"],
            "total_distance": _format_distance(route["distance"]),
            "total_duration": _format_duration(route["duration"]),
            "steps": steps[:10],
        }

        logger.info(
            f"[Tool] get_directions: {directions_info['total_distance']}, "
            f"{directions_info['total_duration']}"
        )
        return json.dumps(directions_info, indent=2)

    except Exception as e:
        logger.error(f"[Tool] get_directions failed: {e}")
        return json.dumps({"error": str(e)})


@tool
def get_current_time(
    city: str
) -> str:
    """
    Get the current local date and time for a supported city using its time zone.

    Use this when the user asks what time it is somewhere, local time in a city,
    or time zone information for travel planning.

    Args:
        city: City name (e.g. 'Tokyo', 'New York', 'London', 'Sydney')

    Returns:
        JSON string with local time, IANA zone id, UTC offset, and common abbreviation if available
    """
    try:
        logger.info(f"[Tool] get_current_time: city='{city}'")
        tz_name = _resolve_city_timezone(city)
        now = datetime.now(ZoneInfo(tz_name))
        offset = _format_utc_offset(now)
        abbrev = now.strftime("%Z") or ""

        payload = {
            "city_query": city.strip(),
            "timezone": tz_name,
            "local_time": now.isoformat(timespec="seconds"),
            "local_time_readable": now.strftime("%Y-%m-%d %H:%M:%S"),
            "utc_offset": offset,
            "abbreviation": abbrev,
        }
        logger.info(f"[Tool] get_current_time: {city} -> {payload['local_time_readable']} ({tz_name})")
        return json.dumps(payload, indent=2)

    except ValueError as e:
        logger.error(f"[Tool] get_current_time: {e}")
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.error(f"[Tool] get_current_time failed: {e}")
        return json.dumps({"error": str(e)})


@tool
def get_exchange_rate(
    from_currency: str,
    to_currency: str,
    amount: float = 1.0
) -> str:
    """
    Get a foreign exchange rate and converted amount using the Frankfurter API (no API key).

    Use this when the user asks for exchange rates, currency conversion, or how much
    one currency is worth in another. Use standard ISO 4217 codes (USD, EUR, GBP, JPY).

    Args:
        from_currency: Base currency code (e.g. 'USD')
        to_currency: Target currency code (e.g. 'EUR', 'JPY')
        amount: Amount of base currency to convert (default 1.0)

    Returns:
        JSON string with rate, converted amount, date, and currencies
    """
    try:
        base = from_currency.strip().upper()
        target = to_currency.strip().upper()
        logger.info(f"[Tool] get_exchange_rate: {base} -> {target}, amount={amount}")

        response = requests.get(
            FRANKFURTER_BASE_URL,
            params={"from": base, "to": target},
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        rates = data.get("rates") or {}
        if target not in rates:
            logger.warning(f"[Tool] get_exchange_rate: no rate for {target} in response")
            return json.dumps({
                "error": f"No exchange rate returned for {target}. Check currency codes.",
                "raw": data,
            })

        rate = float(rates[target])
        converted = round(float(amount) * rate, 4)

        payload = {
            "from_currency": base,
            "to_currency": target,
            "amount": float(amount),
            "exchange_rate": rate,
            "converted_amount": converted,
            "rate_date": data.get("date"),
        }
        logger.info(
            f"[Tool] get_exchange_rate: 1 {base} = {rate} {target} "
            f"({amount} {base} -> {converted} {target})"
        )
        return json.dumps(payload, indent=2)

    except requests.RequestException as e:
        logger.error(f"[Tool] get_exchange_rate API error: {e}")
        return json.dumps({"error": f"Exchange rate service unavailable: {e}"})
    except Exception as e:
        logger.error(f"[Tool] get_exchange_rate failed: {e}")
        return json.dumps({"error": str(e)})
