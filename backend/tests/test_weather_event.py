from app.config import Settings
from app.services.weather_event import WeatherEvent, classify_weather_event


def _settings(**overrides) -> Settings:
    defaults = dict(heavy_snow_threshold_cm=5.0, heatwave_temp_c=33.0, coldwave_temp_c=-12.0)
    defaults.update(overrides)
    return Settings(**defaults)


def test_classify_normal_day_when_nothing_crosses_threshold():
    result = classify_weather_event(
        precip_mm=0.0, snow_cm=0.0, max_temp_c=20.0, min_temp_c=10.0, settings=_settings()
    )
    assert result == WeatherEvent.NORMAL


def test_classify_rain_when_precip_positive_and_no_other_threshold_crossed():
    result = classify_weather_event(
        precip_mm=5.0, snow_cm=None, max_temp_c=18.0, min_temp_c=12.0, settings=_settings()
    )
    assert result == WeatherEvent.RAIN


def test_classify_heavy_snow_at_exact_threshold():
    result = classify_weather_event(
        precip_mm=3.0, snow_cm=5.0, max_temp_c=-2.0, min_temp_c=-10.0, settings=_settings()
    )
    assert result == WeatherEvent.HEAVY_SNOW


def test_classify_heatwave_at_exact_threshold():
    result = classify_weather_event(
        precip_mm=None, snow_cm=None, max_temp_c=33.0, min_temp_c=25.0, settings=_settings()
    )
    assert result == WeatherEvent.HEATWAVE


def test_classify_coldwave_at_exact_threshold():
    result = classify_weather_event(
        precip_mm=None, snow_cm=None, max_temp_c=-5.0, min_temp_c=-12.0, settings=_settings()
    )
    assert result == WeatherEvent.COLDWAVE


def test_heavy_snow_takes_priority_over_coldwave_when_both_cross():
    """저온 강수(폭설)는 한파 조건도 같이 만족할 수 있다 — 더 구체적인 폭설 우선."""
    result = classify_weather_event(
        precip_mm=8.0, snow_cm=6.0, max_temp_c=-8.0, min_temp_c=-15.0, settings=_settings()
    )
    assert result == WeatherEvent.HEAVY_SNOW


def test_below_threshold_values_do_not_trigger_extreme_categories():
    result = classify_weather_event(
        precip_mm=0.0, snow_cm=4.9, max_temp_c=32.9, min_temp_c=-11.9, settings=_settings()
    )
    assert result == WeatherEvent.NORMAL


def test_missing_fields_are_treated_as_not_crossing_threshold():
    """None인 필드(구버전 데이터 등)는 그 유형 판정을 그냥 건너뛴다."""
    result = classify_weather_event(
        precip_mm=None, snow_cm=None, max_temp_c=None, min_temp_c=None, settings=_settings()
    )
    assert result == WeatherEvent.NORMAL
