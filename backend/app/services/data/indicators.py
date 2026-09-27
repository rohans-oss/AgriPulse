"""Simple, explainable weather indicators for operations.

These are transparent threshold rules over stored observations and provider forecasts —
not machine-learning predictions and not spoilage models (those belong to later versions).
Each indicator says which data it used and whether that data was OBSERVED (real external data)
or a FORECAST (a model prediction from the provider).

Rainfall categories follow IMD's 24-hour rainfall classification:
  moderate 15.6–64.4 mm, heavy 64.5–115.5 mm, very heavy 115.6–204.4 mm, extremely heavy ≥204.5 mm.
"""

from datetime import UTC, datetime, timedelta

from app.schemas.data import ForecastDay, Indicator, WeatherReading
from app.services.data.freshness import IST

HEAVY_RAIN_MM = 64.5
VERY_HEAVY_RAIN_MM = 115.6
MODERATE_RAIN_MM = 15.6
THREE_DAY_RAIN_WATCH_MM = 50.0
HEAT_WATCH_C = 35.0
HEAT_WARNING_C = 40.0
GUST_WATCH_KMH = 40.0
GUST_WARNING_KMH = 60.0
HUMID_PCT = 85.0
HUMID_MIN_TEMP_C = 25.0
STORM_CODES = {95, 96, 99}
READING_MAX_AGE = timedelta(hours=6)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def evaluate(reading: WeatherReading | None, completed_days: list[dict], forecast: list[ForecastDay],
             now: datetime | None = None) -> tuple[list[Indicator], str | None]:
    """Return (indicators, note). ``completed_days``: dicts with obs_date and precipitation_mm, newest last."""
    now = now or datetime.now(UTC)
    out: list[Indicator] = []
    notes: list[str] = []

    # --- observed: current conditions (only if the reading is recent enough to be meaningful)
    if reading is None:
        notes.append("No current reading")
    elif now - _aware(reading.observed_at) > READING_MAX_AGE:
        notes.append("Current reading is more than 6 hours old; current-condition indicators were not evaluated")
    else:
        t, g, h = reading.temperature_c, reading.wind_gust_kmh, reading.humidity_pct
        if t is not None and t >= HEAT_WATCH_C:
            level = "WARNING" if t >= HEAT_WARNING_C else "WATCH"
            out.append(Indicator(key="HEAT", level=level, title="High temperature", basis="OBSERVED",
                                 data_class="REAL_EXTERNAL", as_of=reading.observed_at,
                                 message=f"{t}°C now. Protect heat-sensitive produce in storage and transit.",
                                 rule=f"Current temperature ≥ {HEAT_WATCH_C:.0f}°C (warning ≥ {HEAT_WARNING_C:.0f}°C)"))
        if g is not None and g >= GUST_WATCH_KMH:
            level = "WARNING" if g >= GUST_WARNING_KMH else "WATCH"
            out.append(Indicator(key="WIND", level=level, title="Strong wind gusts", basis="OBSERVED",
                                 data_class="REAL_EXTERNAL", as_of=reading.observed_at,
                                 message=f"Gusts of {g} km/h. Secure loads; open-bed transport may be affected.",
                                 rule=f"Current gusts ≥ {GUST_WATCH_KMH:.0f} km/h (warning ≥ {GUST_WARNING_KMH:.0f} km/h)"))
        if reading.weather_code in STORM_CODES:
            out.append(Indicator(key="STORM", level="WARNING", title="Thunderstorm", basis="OBSERVED",
                                 data_class="REAL_EXTERNAL", as_of=reading.observed_at,
                                 message="Thunderstorm conditions reported at this location.",
                                 rule="Current weather code is a thunderstorm (WMO 95–99)"))
        if h is not None and t is not None and h >= HUMID_PCT and t >= HUMID_MIN_TEMP_C:
            out.append(Indicator(key="HUMIDITY", level="WATCH", title="Warm and humid", basis="OBSERVED",
                                 data_class="REAL_EXTERNAL", as_of=reading.observed_at,
                                 message=f"{h}% humidity at {t}°C. Check ventilation for stored produce.",
                                 rule=f"Humidity ≥ {HUMID_PCT:.0f}% and temperature ≥ {HUMID_MIN_TEMP_C:.0f}°C"))

    # --- observed: completed days
    recent = [d for d in completed_days if d.get("precipitation_mm") is not None][-3:]
    if recent:
        last = recent[-1]
        mm = last["precipitation_mm"]
        total3 = round(sum(d["precipitation_mm"] for d in recent), 1)
        if mm >= HEAVY_RAIN_MM:
            cat = "Very heavy" if mm >= VERY_HEAVY_RAIN_MM else "Heavy"
            out.append(Indicator(key="RAIN", level="WARNING", title=f"{cat} rain recorded", basis="OBSERVED",
                                 data_class="REAL_EXTERNAL", as_of=last["obs_date"],
                                 message=f"{mm} mm on {last['obs_date']:%d %b}. Expect wet roads and possible delays.",
                                 rule=f"Daily rainfall ≥ {HEAVY_RAIN_MM} mm (IMD 'heavy')"))
        elif total3 >= THREE_DAY_RAIN_WATCH_MM:
            out.append(Indicator(key="RAIN", level="WATCH", title="Wet spell", basis="OBSERVED",
                                 data_class="REAL_EXTERNAL", as_of=last["obs_date"],
                                 message=f"{total3} mm over the last {len(recent)} days.",
                                 rule=f"Rainfall over the last 3 completed days ≥ {THREE_DAY_RAIN_WATCH_MM:.0f} mm"))
    else:
        notes.append("No completed-day rainfall data")

    # --- forecast (model prediction from the provider)
    for f in forecast[:3]:
        p, prob = f.precipitation_mm, f.precipitation_probability
        when = "today" if f.date == now.astimezone(IST).date() else f"{f.date:%d %b}"
        if p is not None and p >= HEAVY_RAIN_MM:
            out.append(Indicator(key="RAIN", level="WARNING", title=f"Heavy rain forecast {when}", basis="FORECAST",
                                 data_class="MODEL_PREDICTION", as_of=f.issued_at,
                                 message=f"Forecast {p} mm" + (f" ({prob:.0f}% chance)" if prob is not None else "")
                                 + ". Plan transport and loading around it.",
                                 rule=f"Forecast daily rainfall ≥ {HEAVY_RAIN_MM} mm (IMD 'heavy')"))
        elif p is not None and p >= MODERATE_RAIN_MM and (prob is None or prob >= 70):
            out.append(Indicator(key="RAIN", level="WATCH", title=f"Rain likely {when}", basis="FORECAST",
                                 data_class="MODEL_PREDICTION", as_of=f.issued_at,
                                 message=f"Forecast {p} mm" + (f" ({prob:.0f}% chance)" if prob is not None else "") + ".",
                                 rule=f"Forecast ≥ {MODERATE_RAIN_MM} mm (IMD 'moderate') with ≥70% probability"))
        if f.temp_max_c is not None and f.temp_max_c >= HEAT_WARNING_C:
            out.append(Indicator(key="HEAT", level="WARNING", title=f"Extreme heat forecast {when}", basis="FORECAST",
                                 data_class="MODEL_PREDICTION", as_of=f.issued_at,
                                 message=f"Forecast maximum {f.temp_max_c}°C.",
                                 rule=f"Forecast maximum ≥ {HEAT_WARNING_C:.0f}°C"))
        if f.weather_code in STORM_CODES and (prob is None or prob >= 50):
            out.append(Indicator(key="STORM", level="WATCH", title=f"Thunderstorms possible {when}", basis="FORECAST",
                                 data_class="MODEL_PREDICTION", as_of=f.issued_at,
                                 message="The provider forecasts thunderstorm conditions.",
                                 rule="Forecast weather code is a thunderstorm (WMO 95–99) with ≥50% rain probability"))
    order = {"WARNING": 0, "WATCH": 1}
    out.sort(key=lambda i: (order[i.level], i.basis != "OBSERVED"))
    return out, "; ".join(notes) or None

