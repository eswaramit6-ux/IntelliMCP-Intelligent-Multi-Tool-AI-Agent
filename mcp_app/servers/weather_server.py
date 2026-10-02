"""MCP server: weather via Open-Meteo (free, no API key)."""
import sys
from pathlib import Path

# Let this script import project packages (config/, tools/) when run as a subprocess.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from mcp.server.fastmcp import FastMCP

import httpx

server = FastMCP("weather")

WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow",
    75: "Heavy snow", 80: "Rain showers", 81: "Rain showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}


@server.tool()
async def get_weather(city: str) -> str:
    """Get the current weather and a 3-day forecast for a city, e.g. 'Visakhapatnam'
    or 'Paris'. Requires a city name."""
    try:
        async with httpx.AsyncClient(timeout=15) as http:
            geo = await http.get("https://geocoding-api.open-meteo.com/v1/search",
                                 params={"name": city, "count": 1})
            geo.raise_for_status()
            found = geo.json().get("results")
            if not found:
                return f"Could not find a place called '{city}'."
            place = found[0]
            wx = await http.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": place["latitude"], "longitude": place["longitude"],
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                           "wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                "timezone": "auto", "forecast_days": 3})
            wx.raise_for_status()
            data = wx.json()
    except httpx.HTTPError as exc:
        return f"Weather service unavailable: {exc}"

    cur, daily = data["current"], data["daily"]
    lines = [
        f"Weather in {place['name']}, {place.get('country', '')}:",
        f"Now: {WEATHER_CODES.get(cur['weather_code'], 'Unknown')}, "
        f"{cur['temperature_2m']}°C (feels like {cur['apparent_temperature']}°C), "
        f"humidity {cur['relative_humidity_2m']}%, wind {cur['wind_speed_10m']} km/h",
        "Forecast:"]
    for i, day in enumerate(daily["time"]):
        lines.append(f"  {day}: {daily['temperature_2m_min'][i]}-"
                     f"{daily['temperature_2m_max'][i]}°C, "
                     f"rain chance {daily['precipitation_probability_max'][i]}%")
    return "\n".join(lines)


if __name__ == "__main__":
    server.run(transport="stdio")
