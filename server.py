import logging

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("octo-mcp-server", stateless_http=True)

NWS_BASE_URL = "https://api.weather.gov"
NWS_HEADERS = {
    "User-Agent": "octo-mcp-server/1.0 (contact@example.com)",
    "Accept": "application/geo+json",
}


@mcp.tool()
async def echo(message: str) -> str:
    """
    Returns the provided message unchanged. Useful for testing connectivity.

    Args:
        message: The message to echo back.
    """
    return message


@mcp.tool()
async def get_weather_forecast(latitude: float, longitude: float, hourly: bool = False) -> str:
    """
    Retrieves the weather forecast for a US location using the National Weather Service API.
    Only works for locations within the United States.

    Args:
        latitude: Latitude of the location (e.g., 38.8894 for Washington D.C.).
        longitude: Longitude of the location (e.g., -77.0352 for Washington D.C.).
        hourly: If True, returns an hourly forecast instead of the default 12-hour period forecast.
    """
    async with httpx.AsyncClient(headers=NWS_HEADERS, timeout=15.0) as client:
        # Step 1: resolve coordinates to NWS grid point
        points_resp = await client.get(f"{NWS_BASE_URL}/points/{latitude},{longitude}")
        if points_resp.status_code != 200:
            return f"Error resolving location: HTTP {points_resp.status_code}. The NWS API only covers US locations."

        points_data = points_resp.json()
        props = points_data.get("properties", {})
        forecast_url = props.get("forecastHourly" if hourly else "forecast")
        location_name = f"{props.get('relativeLocation', {}).get('properties', {}).get('city', '')}, {props.get('relativeLocation', {}).get('properties', {}).get('state', '')}".strip(", ")

        if not forecast_url:
            return "Error: could not determine forecast URL from NWS response."

        # Step 2: fetch the forecast
        forecast_resp = await client.get(forecast_url)
        if forecast_resp.status_code != 200:
            return f"Error fetching forecast: HTTP {forecast_resp.status_code}"

        forecast_data = forecast_resp.json()
        periods = forecast_data.get("properties", {}).get("periods", [])

        if not periods:
            return "No forecast data available for this location."

        lines = [f"Weather forecast for {location_name} ({latitude}, {longitude}):\n"]
        for period in periods[:8]:  # limit to 8 periods to keep output concise
            name = period.get("name", "")
            temp = period.get("temperature", "?")
            temp_unit = period.get("temperatureUnit", "F")
            wind_speed = period.get("windSpeed", "")
            wind_dir = period.get("windDirection", "")
            short_forecast = period.get("shortForecast", "")
            detailed = period.get("detailedForecast", "")

            lines.append(f"**{name}**: {temp}°{temp_unit}, Wind {wind_speed} {wind_dir}")
            lines.append(f"  {short_forecast}")
            if detailed:
                lines.append(f"  {detailed}")
            lines.append("")

        return "\n".join(lines)


@mcp.tool()
async def get_current_conditions(latitude: float, longitude: float) -> str:
    """
    Retrieves current weather conditions for a US location by finding the nearest
    observation station and returning its latest observation.
    Only works for locations within the United States.

    Args:
        latitude: Latitude of the location (e.g., 38.8894 for Washington D.C.).
        longitude: Longitude of the location (e.g., -77.0352 for Washington D.C.).
    """
    async with httpx.AsyncClient(headers=NWS_HEADERS, timeout=15.0) as client:
        # Step 1: resolve coordinates to grid point
        points_resp = await client.get(f"{NWS_BASE_URL}/points/{latitude},{longitude}")
        if points_resp.status_code != 200:
            return f"Error resolving location: HTTP {points_resp.status_code}. The NWS API only covers US locations."

        props = points_resp.json().get("properties", {})
        wfo = props.get("gridId")
        grid_x = props.get("gridX")
        grid_y = props.get("gridY")
        location_name = (
            f"{props.get('relativeLocation', {}).get('properties', {}).get('city', '')}, "
            f"{props.get('relativeLocation', {}).get('properties', {}).get('state', '')}"
        ).strip(", ")

        if not all([wfo, grid_x is not None, grid_y is not None]):
            return "Error: could not resolve grid coordinates from NWS response."

        # Step 2: find nearby observation stations
        stations_resp = await client.get(f"{NWS_BASE_URL}/gridpoints/{wfo}/{grid_x},{grid_y}/stations")
        if stations_resp.status_code != 200:
            return f"Error fetching nearby stations: HTTP {stations_resp.status_code}"

        stations = stations_resp.json().get("features", [])
        if not stations:
            return "No observation stations found near this location."

        station_id = stations[0].get("properties", {}).get("stationIdentifier")
        station_name = stations[0].get("properties", {}).get("name", station_id)

        if not station_id:
            return "Error: could not determine station ID from NWS response."

        # Step 3: fetch the latest observation
        obs_resp = await client.get(f"{NWS_BASE_URL}/stations/{station_id}/observations/latest")
        if obs_resp.status_code != 200:
            return f"Error fetching observations from station {station_id}: HTTP {obs_resp.status_code}"

        obs = obs_resp.json().get("properties", {})

        def val(key: str, unit_key: str = "value", decimals: int = 1) -> str:
            v = obs.get(key, {})
            if isinstance(v, dict) and v.get("value") is not None:
                return f"{round(v['value'], decimals)}"
            return "N/A"

        temp_c = obs.get("temperature", {}).get("value")
        temp_str = f"{round(temp_c, 1)}°C / {round(temp_c * 9/5 + 32, 1)}°F" if temp_c is not None else "N/A"

        dewpoint_c = obs.get("dewpoint", {}).get("value")
        dewpoint_str = f"{round(dewpoint_c, 1)}°C / {round(dewpoint_c * 9/5 + 32, 1)}°F" if dewpoint_c is not None else "N/A"

        wind_speed_ms = obs.get("windSpeed", {}).get("value")
        wind_speed_str = f"{round(wind_speed_ms * 2.237, 1)} mph" if wind_speed_ms is not None else "N/A"

        wind_dir = val("windDirection", decimals=0)
        humidity = val("relativeHumidity")
        visibility_m = obs.get("visibility", {}).get("value")
        visibility_str = f"{round(visibility_m / 1000, 1)} km / {round(visibility_m / 1609.34, 1)} mi" if visibility_m is not None else "N/A"
        description = obs.get("textDescription", "N/A")
        timestamp = obs.get("timestamp", "N/A")

        return (
            f"Current conditions for {location_name} ({latitude}, {longitude})\n"
            f"Station: {station_name} ({station_id}) — {timestamp}\n\n"
            f"Conditions:   {description}\n"
            f"Temperature:  {temp_str}\n"
            f"Dewpoint:     {dewpoint_str}\n"
            f"Humidity:     {humidity}%\n"
            f"Wind:         {wind_speed_str} from {wind_dir}°\n"
            f"Visibility:   {visibility_str}\n"
        )


@mcp.tool()
async def get_weather_alerts(state: str) -> str:
    """
    Retrieves active weather alerts for a US state from the National Weather Service.

    Args:
        state: Two-letter US state abbreviation (e.g., "TX", "CA", "FL").
    """
    async with httpx.AsyncClient(headers=NWS_HEADERS, timeout=15.0) as client:
        resp = await client.get(f"{NWS_BASE_URL}/alerts/active", params={"area": state.upper()})
        if resp.status_code != 200:
            return f"Error fetching alerts: HTTP {resp.status_code}"

        data = resp.json()
        features = data.get("features", [])

        if not features:
            return f"No active weather alerts for {state.upper()}."

        lines = [f"Active weather alerts for {state.upper()} ({len(features)} alert(s)):\n"]
        for feature in features[:10]:  # cap at 10 alerts
            props = feature.get("properties", {})
            event = props.get("event", "Unknown")
            headline = props.get("headline", "")
            severity = props.get("severity", "")
            urgency = props.get("urgency", "")
            areas = props.get("areaDesc", "")
            description = props.get("description", "").split("\n")[0]  # first line only

            lines.append(f"**{event}** [{severity} / {urgency}]")
            if headline:
                lines.append(f"  {headline}")
            if areas:
                lines.append(f"  Areas: {areas}")
            if description:
                lines.append(f"  {description}")
            lines.append("")

        return "\n".join(lines)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
