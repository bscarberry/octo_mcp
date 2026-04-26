import json
import logging
from typing import Any

import azure.functions as func
import httpx

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

NWS_BASE_URL = "https://api.weather.gov"
NWS_HEADERS = {
    "User-Agent": "octo-mcp-server/1.0 (contact@example.com)",
    "Accept": "application/geo+json",
}


def _arguments(context: Any) -> dict[str, Any]:
    if isinstance(context, str):
        payload = json.loads(context)
    else:
        payload = json.loads(str(context))
    return payload.get("arguments", {})


def _number(value: Any, name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number")


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"true", "1", "yes"}
    return bool(value)


def _get_json(client: httpx.Client, url: str, **kwargs: Any) -> tuple[int, dict[str, Any]]:
    response = client.get(url, **kwargs)
    if response.status_code != 200:
        return response.status_code, {}
    return response.status_code, response.json()


@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="echo",
    description="Returns a message unchanged.",
    tool_properties=json.dumps(
        [
            {
                "propertyName": "message",
                "propertyType": "string",
                "description": "The message to echo back.",
                "isRequired": True,
            }
        ]
    ),
)
def echo(context) -> str:
    args = _arguments(context)
    return str(args.get("message", ""))


@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_weather_forecast",
    description="Get a National Weather Service forecast for a US latitude and longitude.",
    tool_properties=json.dumps(
        [
            {
                "propertyName": "latitude",
                "propertyType": "number",
                "description": "Latitude of the US location.",
                "isRequired": True,
            },
            {
                "propertyName": "longitude",
                "propertyType": "number",
                "description": "Longitude of the US location.",
                "isRequired": True,
            },
            {
                "propertyName": "hourly",
                "propertyType": "boolean",
                "description": "Return hourly forecast instead of the default period forecast.",
                "isRequired": False,
            },
        ]
    ),
)
def get_weather_forecast(context) -> str:
    try:
        args = _arguments(context)
        latitude = _number(args.get("latitude"), "latitude")
        longitude = _number(args.get("longitude"), "longitude")
        hourly = _bool(args.get("hourly", False))

        with httpx.Client(headers=NWS_HEADERS, timeout=15.0) as client:
            status, points_data = _get_json(client, f"{NWS_BASE_URL}/points/{latitude},{longitude}")
            if status != 200:
                return f"Error resolving location: HTTP {status}. The NWS API only covers US locations."

            props = points_data.get("properties", {})
            forecast_url = props.get("forecastHourly" if hourly else "forecast")
            location_props = props.get("relativeLocation", {}).get("properties", {})
            location_name = f"{location_props.get('city', '')}, {location_props.get('state', '')}".strip(", ")

            if not forecast_url:
                return "Error: could not determine forecast URL from NWS response."

            status, forecast_data = _get_json(client, forecast_url)
            if status != 200:
                return f"Error fetching forecast: HTTP {status}"

            periods = forecast_data.get("properties", {}).get("periods", [])
            if not periods:
                return "No forecast data available for this location."

            lines = [f"Weather forecast for {location_name} ({latitude}, {longitude}):\n"]
            for period in periods[:8]:
                name = period.get("name", "")
                temp = period.get("temperature", "?")
                temp_unit = period.get("temperatureUnit", "F")
                wind_speed = period.get("windSpeed", "")
                wind_dir = period.get("windDirection", "")
                short_forecast = period.get("shortForecast", "")
                detailed = period.get("detailedForecast", "")

                lines.append(f"{name}: {temp}°{temp_unit}, Wind {wind_speed} {wind_dir}")
                lines.append(f"  {short_forecast}")
                if detailed:
                    lines.append(f"  {detailed}")
                lines.append("")

            return "\n".join(lines)
    except Exception as exc:
        logging.exception("get_weather_forecast failed")
        return f"Error: {exc}"


@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_current_conditions",
    description="Get current National Weather Service conditions for a US latitude and longitude.",
    tool_properties=json.dumps(
        [
            {
                "propertyName": "latitude",
                "propertyType": "number",
                "description": "Latitude of the US location.",
                "isRequired": True,
            },
            {
                "propertyName": "longitude",
                "propertyType": "number",
                "description": "Longitude of the US location.",
                "isRequired": True,
            },
        ]
    ),
)
def get_current_conditions(context) -> str:
    try:
        args = _arguments(context)
        latitude = _number(args.get("latitude"), "latitude")
        longitude = _number(args.get("longitude"), "longitude")

        with httpx.Client(headers=NWS_HEADERS, timeout=15.0) as client:
            status, points_data = _get_json(client, f"{NWS_BASE_URL}/points/{latitude},{longitude}")
            if status != 200:
                return f"Error resolving location: HTTP {status}. The NWS API only covers US locations."

            props = points_data.get("properties", {})
            wfo = props.get("gridId")
            grid_x = props.get("gridX")
            grid_y = props.get("gridY")
            location_props = props.get("relativeLocation", {}).get("properties", {})
            location_name = f"{location_props.get('city', '')}, {location_props.get('state', '')}".strip(", ")

            if not all([wfo, grid_x is not None, grid_y is not None]):
                return "Error: could not resolve grid coordinates from NWS response."

            status, stations_data = _get_json(client, f"{NWS_BASE_URL}/gridpoints/{wfo}/{grid_x},{grid_y}/stations")
            if status != 200:
                return f"Error fetching nearby stations: HTTP {status}"

            stations = stations_data.get("features", [])
            if not stations:
                return "No observation stations found near this location."

            station_props = stations[0].get("properties", {})
            station_id = station_props.get("stationIdentifier")
            station_name = station_props.get("name", station_id)
            if not station_id:
                return "Error: could not determine station ID from NWS response."

            status, obs_data = _get_json(client, f"{NWS_BASE_URL}/stations/{station_id}/observations/latest")
            if status != 200:
                return f"Error fetching observations from station {station_id}: HTTP {status}"

            obs = obs_data.get("properties", {})
            temp_c = obs.get("temperature", {}).get("value")
            temp_str = f"{round(temp_c, 1)}°C / {round(temp_c * 9 / 5 + 32, 1)}°F" if temp_c is not None else "N/A"
            dewpoint_c = obs.get("dewpoint", {}).get("value")
            dewpoint_str = (
                f"{round(dewpoint_c, 1)}°C / {round(dewpoint_c * 9 / 5 + 32, 1)}°F"
                if dewpoint_c is not None
                else "N/A"
            )
            wind_speed_ms = obs.get("windSpeed", {}).get("value")
            wind_speed_str = f"{round(wind_speed_ms * 2.237, 1)} mph" if wind_speed_ms is not None else "N/A"
            wind_dir = obs.get("windDirection", {}).get("value")
            wind_dir_str = f"{round(wind_dir)}°" if wind_dir is not None else "N/A"
            humidity = obs.get("relativeHumidity", {}).get("value")
            humidity_str = f"{round(humidity, 1)}%" if humidity is not None else "N/A"
            visibility_m = obs.get("visibility", {}).get("value")
            visibility_str = (
                f"{round(visibility_m / 1000, 1)} km / {round(visibility_m / 1609.34, 1)} mi"
                if visibility_m is not None
                else "N/A"
            )

            return (
                f"Current conditions for {location_name} ({latitude}, {longitude})\n"
                f"Station: {station_name} ({station_id}) - {obs.get('timestamp', 'N/A')}\n\n"
                f"Conditions:   {obs.get('textDescription', 'N/A')}\n"
                f"Temperature:  {temp_str}\n"
                f"Dewpoint:     {dewpoint_str}\n"
                f"Humidity:     {humidity_str}\n"
                f"Wind:         {wind_speed_str} from {wind_dir_str}\n"
                f"Visibility:   {visibility_str}\n"
            )
    except Exception as exc:
        logging.exception("get_current_conditions failed")
        return f"Error: {exc}"


@app.mcp_tool_trigger(
    arg_name="context",
    tool_name="get_weather_alerts",
    description="Get active National Weather Service alerts for a US state.",
    tool_properties=json.dumps(
        [
            {
                "propertyName": "state",
                "propertyType": "string",
                "description": "Two-letter US state abbreviation, such as TX, CA, or FL.",
                "isRequired": True,
            }
        ]
    ),
)
def get_weather_alerts(context) -> str:
    try:
        args = _arguments(context)
        state = str(args.get("state", "")).upper().strip()
        if len(state) != 2:
            return "Error: state must be a two-letter US state abbreviation."

        with httpx.Client(headers=NWS_HEADERS, timeout=15.0) as client:
            response = client.get(f"{NWS_BASE_URL}/alerts/active", params={"area": state})
            if response.status_code != 200:
                return f"Error fetching alerts: HTTP {response.status_code}"

            features = response.json().get("features", [])
            if not features:
                return f"No active weather alerts for {state}."

            lines = [f"Active weather alerts for {state} ({len(features)} alert(s)):\n"]
            for feature in features[:10]:
                props = feature.get("properties", {})
                lines.append(f"{props.get('event', 'Unknown')} [{props.get('severity', '')} / {props.get('urgency', '')}]")
                if props.get("headline"):
                    lines.append(f"  {props['headline']}")
                if props.get("areaDesc"):
                    lines.append(f"  Areas: {props['areaDesc']}")
                description = props.get("description", "").split("\n")[0]
                if description:
                    lines.append(f"  {description}")
                lines.append("")

            return "\n".join(lines)
    except Exception as exc:
        logging.exception("get_weather_alerts failed")
        return f"Error: {exc}"
