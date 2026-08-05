from datetime import date

from app.services.funnel import months_active, ramp_fraction, target_treatments


def test_months_active_counts_inclusive_calendar_months() -> None:
    assert months_active(date(2026, 1, 1), date(2026, 1, 1)) == 1
    assert months_active(date(2025, 6, 1), date(2026, 2, 1)) == 9
    assert months_active(date(2026, 3, 1), date(2026, 2, 1)) == 0


def test_ramp_fraction_floors_and_plateaus() -> None:
    assert ramp_fraction(0) == 0.0
    assert ramp_fraction(-3) == 0.0
    assert ramp_fraction(1) == 0.36
    assert ramp_fraction(12) == 1.0  # 0.3 + 0.72 caps at 1.0
    assert ramp_fraction(100) == 1.0


def test_target_treatments_scales_with_ramp() -> None:
    assert target_treatments(0) == 0
    assert 0 < target_treatments(1) < target_treatments(6) <= target_treatments(12)
    assert target_treatments(12) == 28
