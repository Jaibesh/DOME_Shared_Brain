"""
Weather Service Module

Integrates with weather APIs to provide productivity adjustments
and scheduling optimization based on weather forecasts.

Phase 3 Feature: Weather Forecast Integration
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
)
logger = logging.getLogger(__name__)

# Try to import required libraries
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    logger.warning("requests not installed - weather API disabled")

# Try to import database module
try:
    from modules.database import get_connection
    HAS_DATABASE = True
except ImportError:
    HAS_DATABASE = False


# Weather condition to productivity modifier mapping
WEATHER_PRODUCTIVITY_MODIFIERS = {
    # Precipitation conditions
    "heavy_rain": 0.50,      # Major productivity loss, possible work stoppage
    "moderate_rain": 0.70,   # Significant slowdown
    "light_rain": 0.85,      # Minor impact
    "drizzle": 0.90,         # Minimal impact

    # Temperature extremes
    "extreme_heat": 0.85,    # >100F - heat breaks, hydration
    "hot": 0.92,             # 90-100F - some slowdown
    "ideal": 1.00,           # 60-85F - perfect conditions
    "cold": 0.90,            # 35-50F - slower operations
    "freezing": 0.65,        # <32F - frozen ground issues
    "extreme_cold": 0.50,    # <20F - major equipment/safety issues

    # Ground conditions
    "muddy": 0.70,           # After rain, muddy conditions
    "saturated": 0.60,       # Waterlogged ground
    "frozen_ground": 0.65,   # Frozen soil
    "dry_dusty": 0.92,       # Dust control needed

    # Wind conditions
    "high_wind": 0.80,       # >25mph - crane/lifting restrictions
    "moderate_wind": 0.95,   # 15-25mph - minor issues

    # Visibility
    "fog": 0.85,             # Reduced visibility

    # Snow/Ice
    "snow": 0.40,            # Active snowfall - likely work stoppage
    "ice": 0.30,             # Icy conditions - safety concern
}


@dataclass
class DailyForecast:
    """Represents a daily weather forecast."""
    date: str
    condition: str
    condition_text: str
    temp_high_f: float
    temp_low_f: float
    precip_mm: float
    precip_chance: int
    humidity: int
    wind_mph: float
    uv_index: int
    productivity_modifier: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "condition": self.condition,
            "condition_text": self.condition_text,
            "temp_high_f": self.temp_high_f,
            "temp_low_f": self.temp_low_f,
            "precip_mm": self.precip_mm,
            "precip_chance": self.precip_chance,
            "humidity": self.humidity,
            "wind_mph": self.wind_mph,
            "uv_index": self.uv_index,
            "productivity_modifier": self.productivity_modifier,
        }


class WeatherService:
    """
    Weather service for fetching and analyzing weather data.

    Supports WeatherAPI.com (primary) with fallback options.
    """

    # WeatherAPI.com endpoints
    WEATHERAPI_BASE = "https://api.weatherapi.com/v1"

    def __init__(self, api_key: str = None):
        """
        Initialize weather service.

        Args:
            api_key: WeatherAPI.com API key (or from WEATHER_API_KEY env var)
        """
        self.api_key = api_key or os.environ.get("WEATHER_API_KEY", "")
        self.session = requests.Session() if HAS_REQUESTS else None
        self._cache = {}  # Simple in-memory cache
        self._cache_duration = timedelta(hours=6)

    def get_forecast(self, zip_code: str, days: int = 14) -> List[DailyForecast]:
        """
        Get weather forecast for a location.

        Args:
            zip_code: ZIP code for the location
            days: Number of days to forecast (max 14 for free tier)

        Returns:
            List of DailyForecast objects
        """
        if not self.api_key:
            logger.warning("Weather API key not configured")
            return self._get_fallback_forecast(days)

        if not HAS_REQUESTS:
            logger.error("Requests library not available")
            return self._get_fallback_forecast(days)

        # Check cache
        cache_key = f"{zip_code}_{days}"
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if datetime.now() - cached_time < self._cache_duration:
                logger.debug(f"Using cached forecast for {zip_code}")
                return cached_data

        try:
            # WeatherAPI.com forecast endpoint
            url = f"{self.WEATHERAPI_BASE}/forecast.json"
            params = {
                "key": self.api_key,
                "q": zip_code,
                "days": min(days, 14),  # API limit
                "aqi": "no",
                "alerts": "no",
            }

            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            forecasts = self._parse_weatherapi_response(data)

            # Cache the result
            self._cache[cache_key] = (datetime.now(), forecasts)

            # Store in database if available
            if HAS_DATABASE:
                self._save_forecasts_to_db(zip_code, forecasts)

            return forecasts

        except requests.RequestException as e:
            logger.error(f"Weather API error: {e}")
            return self._get_cached_or_fallback(zip_code, days)

    def _parse_weatherapi_response(self, data: Dict) -> List[DailyForecast]:
        """Parse WeatherAPI.com response into DailyForecast objects."""
        forecasts = []

        forecast_days = data.get("forecast", {}).get("forecastday", [])

        for day in forecast_days:
            day_data = day.get("day", {})
            condition = day.get("day", {}).get("condition", {})

            # Determine productivity modifier
            modifier = self._calculate_productivity_modifier(
                precip_mm=day_data.get("totalprecip_mm", 0),
                temp_high=day_data.get("maxtemp_f", 70),
                temp_low=day_data.get("mintemp_f", 50),
                wind_mph=day_data.get("maxwind_mph", 0),
                condition_code=condition.get("code", 0),
            )

            forecast = DailyForecast(
                date=day.get("date", ""),
                condition=self._map_condition_code(condition.get("code", 0)),
                condition_text=condition.get("text", ""),
                temp_high_f=day_data.get("maxtemp_f", 70),
                temp_low_f=day_data.get("mintemp_f", 50),
                precip_mm=day_data.get("totalprecip_mm", 0),
                precip_chance=day_data.get("daily_chance_of_rain", 0),
                humidity=day_data.get("avghumidity", 50),
                wind_mph=day_data.get("maxwind_mph", 0),
                uv_index=day_data.get("uv", 5),
                productivity_modifier=modifier,
            )
            forecasts.append(forecast)

        return forecasts

    def _calculate_productivity_modifier(
        self,
        precip_mm: float,
        temp_high: float,
        temp_low: float,
        wind_mph: float,
        condition_code: int,
    ) -> float:
        """Calculate productivity modifier based on weather conditions."""
        modifier = 1.0

        # Precipitation impact
        if precip_mm > 10:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["heavy_rain"]
        elif precip_mm > 5:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["moderate_rain"]
        elif precip_mm > 1:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["light_rain"]
        elif precip_mm > 0:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["drizzle"]

        # Temperature impact (use high temp for heat, low temp for cold)
        if temp_high > 100:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["extreme_heat"]
        elif temp_high > 90:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["hot"]
        elif temp_low < 20:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["extreme_cold"]
        elif temp_low < 32:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["freezing"]
        elif temp_low < 50:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["cold"]

        # Wind impact
        if wind_mph > 25:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["high_wind"]
        elif wind_mph > 15:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["moderate_wind"]

        # Snow/ice conditions (based on condition codes)
        if condition_code in [1066, 1114, 1117, 1210, 1213, 1216, 1219, 1222, 1225, 1237]:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["snow"]
        elif condition_code in [1069, 1072, 1168, 1171, 1198, 1201, 1204, 1207]:
            modifier *= WEATHER_PRODUCTIVITY_MODIFIERS["ice"]

        # Cap the modifier at reasonable bounds
        return round(max(0.30, min(1.0, modifier)), 2)

    def _map_condition_code(self, code: int) -> str:
        """Map WeatherAPI condition code to internal condition string."""
        # WeatherAPI condition codes: https://www.weatherapi.com/docs/weather_conditions.json
        code_map = {
            1000: "clear",
            1003: "partly_cloudy",
            1006: "cloudy",
            1009: "overcast",
            1030: "fog",
            1063: "light_rain",
            1066: "snow",
            1087: "thunderstorm",
            1183: "light_rain",
            1186: "moderate_rain",
            1189: "moderate_rain",
            1192: "heavy_rain",
            1195: "heavy_rain",
            1240: "light_rain",
            1243: "moderate_rain",
            1246: "heavy_rain",
        }
        return code_map.get(code, "unknown")

    def _get_fallback_forecast(self, days: int) -> List[DailyForecast]:
        """Generate fallback forecast when API is unavailable."""
        forecasts = []
        today = datetime.now()

        for i in range(days):
            date = today + timedelta(days=i)
            forecasts.append(DailyForecast(
                date=date.strftime("%Y-%m-%d"),
                condition="unknown",
                condition_text="Forecast unavailable",
                temp_high_f=75,
                temp_low_f=55,
                precip_mm=0,
                precip_chance=20,
                humidity=50,
                wind_mph=10,
                uv_index=5,
                productivity_modifier=0.95,  # Slight uncertainty penalty
            ))

        return forecasts

    def _get_cached_or_fallback(self, zip_code: str, days: int) -> List[DailyForecast]:
        """Try to get cached data, or return fallback."""
        if HAS_DATABASE:
            forecasts = self._get_forecasts_from_db(zip_code, days)
            if forecasts:
                return forecasts
        return self._get_fallback_forecast(days)

    def _save_forecasts_to_db(self, zip_code: str, forecasts: List[DailyForecast]) -> None:
        """Save forecasts to database cache."""
        if not HAS_DATABASE:
            return

        with get_connection() as conn:
            cursor = conn.cursor()

            for forecast in forecasts:
                cursor.execute("""
                    INSERT OR REPLACE INTO weather_forecasts (
                        zip_code, forecast_date, condition,
                        temp_high, temp_low, precip_mm,
                        productivity_modifier, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    zip_code,
                    forecast.date,
                    forecast.condition,
                    forecast.temp_high_f,
                    forecast.temp_low_f,
                    forecast.precip_mm,
                    forecast.productivity_modifier,
                    datetime.now().isoformat(),
                ))

            conn.commit()

    def _get_forecasts_from_db(self, zip_code: str, days: int) -> List[DailyForecast]:
        """Retrieve cached forecasts from database."""
        if not HAS_DATABASE:
            return []

        with get_connection() as conn:
            cursor = conn.cursor()

            # Get forecasts from last 12 hours
            min_fetch_time = (datetime.now() - timedelta(hours=12)).isoformat()

            cursor.execute("""
                SELECT * FROM weather_forecasts
                WHERE zip_code = ?
                AND fetched_at > ?
                ORDER BY forecast_date
                LIMIT ?
            """, (zip_code, min_fetch_time, days))

            rows = cursor.fetchall()

            return [
                DailyForecast(
                    date=row["forecast_date"],
                    condition=row["condition"],
                    condition_text="",
                    temp_high_f=row["temp_high"],
                    temp_low_f=row["temp_low"],
                    precip_mm=row["precip_mm"],
                    precip_chance=0,
                    humidity=0,
                    wind_mph=0,
                    uv_index=0,
                    productivity_modifier=row["productivity_modifier"],
                )
                for row in rows
            ]


def get_weather_forecast(zip_code: str, days: int = 14) -> List[Dict[str, Any]]:
    """
    Convenience function to get weather forecast.

    Args:
        zip_code: ZIP code for location
        days: Number of days

    Returns:
        List of forecast dictionaries
    """
    service = WeatherService()
    forecasts = service.get_forecast(zip_code, days)
    return [f.to_dict() for f in forecasts]


def calculate_weather_productivity_modifier(zip_code: str, start_date: str, duration_days: int) -> Dict[str, Any]:
    """
    Calculate overall productivity modifier for a job based on weather forecast.

    Args:
        zip_code: Job site ZIP code
        start_date: Job start date (YYYY-MM-DD)
        duration_days: Expected job duration in days

    Returns:
        Analysis with productivity adjustments
    """
    service = WeatherService()
    forecasts = service.get_forecast(zip_code, 14)

    if not forecasts:
        return {
            "success": False,
            "message": "Weather data unavailable",
            "avg_modifier": 0.95,
            "risk_level": "unknown",
        }

    # Filter to job duration window
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        start = datetime.now()

    job_forecasts = []
    for f in forecasts:
        try:
            forecast_date = datetime.strptime(f.date, "%Y-%m-%d")
            days_from_start = (forecast_date - start).days
            if 0 <= days_from_start < duration_days:
                job_forecasts.append(f)
        except ValueError:
            continue

    if not job_forecasts:
        return {
            "success": False,
            "message": "No forecast data for job window",
            "avg_modifier": 0.95,
            "risk_level": "unknown",
        }

    # Calculate average modifier
    modifiers = [f.productivity_modifier for f in job_forecasts]
    avg_modifier = sum(modifiers) / len(modifiers)

    # Count problem days
    rain_days = len([f for f in job_forecasts if f.precip_mm > 5])
    extreme_days = len([f for f in job_forecasts if f.productivity_modifier < 0.7])

    # Determine risk level
    if avg_modifier >= 0.90:
        risk_level = "low"
    elif avg_modifier >= 0.80:
        risk_level = "medium"
    elif avg_modifier >= 0.70:
        risk_level = "high"
    else:
        risk_level = "very_high"

    return {
        "success": True,
        "zip_code": zip_code,
        "start_date": start_date,
        "duration_days": duration_days,
        "forecast_days_available": len(job_forecasts),
        "avg_modifier": round(avg_modifier, 2),
        "min_modifier": round(min(modifiers), 2),
        "max_modifier": round(max(modifiers), 2),
        "rain_days": rain_days,
        "extreme_weather_days": extreme_days,
        "risk_level": risk_level,
        "daily_forecasts": [f.to_dict() for f in job_forecasts],
        "recommendation": _get_weather_recommendation(avg_modifier, rain_days),
    }


def _get_weather_recommendation(avg_modifier: float, rain_days: int) -> str:
    """Generate weather recommendation text."""
    if avg_modifier >= 0.95:
        return "Excellent weather conditions expected. Standard timeline should be achievable."
    elif avg_modifier >= 0.85:
        return "Good conditions with minor weather impacts. Consider 5-10% schedule buffer."
    elif avg_modifier >= 0.75:
        return f"Moderate weather risk with {rain_days} rain days expected. Add 15-20% schedule buffer."
    else:
        return f"Significant weather challenges expected. Consider rescheduling or add 25%+ buffer."


def get_optimal_work_days(zip_code: str, start_date: str, required_days: int) -> List[str]:
    """
    Find the best work days within a date range.

    Args:
        zip_code: Job site ZIP code
        start_date: Earliest start date
        required_days: Number of good work days needed

    Returns:
        List of optimal work dates
    """
    service = WeatherService()
    forecasts = service.get_forecast(zip_code, 14)

    # Sort by productivity modifier (best days first)
    sorted_forecasts = sorted(forecasts, key=lambda f: f.productivity_modifier, reverse=True)

    # Return the best days
    optimal_days = sorted_forecasts[:required_days]
    return sorted([f.date for f in optimal_days])


# CLI interface
if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Weather service for job sites")
    parser.add_argument("--zip", required=True, help="ZIP code")
    parser.add_argument("--days", type=int, default=7, help="Forecast days")
    parser.add_argument("--analyze", action="store_true", help="Analyze for job")
    parser.add_argument("--start", help="Job start date (YYYY-MM-DD)")
    parser.add_argument("--duration", type=int, default=5, help="Job duration in days")

    args = parser.parse_args()

    if args.analyze and args.start:
        result = calculate_weather_productivity_modifier(args.zip, args.start, args.duration)
        print(json.dumps(result, indent=2))
    else:
        forecasts = get_weather_forecast(args.zip, args.days)
        print(json.dumps(forecasts, indent=2))
