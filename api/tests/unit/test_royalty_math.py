"""Unit tests for the pure royalty computation layer (R1, R4; ADR-0004)."""

import uuid
from datetime import date
from decimal import Decimal

from app.services.royalty import (
    ExclusionInput,
    LineInput,
    aging_bucket,
    compute_fingerprint,
    compute_line_amount,
    prorated_minimum_cents,
    round_half_up_cents,
)

RATE_7 = Decimal("0.0700")
PERIOD = date(2026, 7, 1)


class TestRoundHalfUp:
    def test_exact_half_rounds_up(self) -> None:
        assert round_half_up_cents(Decimal("864.5")) == 865

    def test_below_half_rounds_down(self) -> None:
        assert round_half_up_cents(Decimal("864.49")) == 864

    def test_integer_passes_through(self) -> None:
        assert round_half_up_cents(Decimal("864")) == 864

    def test_seven_percent_of_odd_cents(self) -> None:
        # 0.07 * 12,345 = 864.15 -> 864 (bankers' rounding would also give 864,
        # but 0.07 * 12,350 = 864.50 -> 865 is where half-up shows).
        assert round_half_up_cents(RATE_7 * Decimal(12_345)) == 864
        assert round_half_up_cents(RATE_7 * Decimal(12_350)) == 865


class TestProratedMinimum:
    def test_full_period_is_full_minimum(self) -> None:
        assert prorated_minimum_cents(200_000, 31, 31) == 200_000

    def test_half_period_is_half_minimum(self) -> None:
        assert prorated_minimum_cents(200_000, 15, 30) == 100_000

    def test_proration_rounds_half_up(self) -> None:
        # 100,001 * 1/3 = 33,333.67 -> 33,334
        assert prorated_minimum_cents(100_001, 10, 30) == 33_334


class TestComputeLineAmount:
    def test_percentage_when_no_minimum(self) -> None:
        amount, applied = compute_line_amount(1_900_000, RATE_7, None, 31, 31)
        assert amount == 133_000
        assert applied is False

    def test_minimum_binds_when_percentage_below_it(self) -> None:
        amount, applied = compute_line_amount(1_000_000, RATE_7, 200_000, 31, 31)
        assert amount == 200_000
        assert applied is True

    def test_percentage_wins_when_above_minimum(self) -> None:
        amount, applied = compute_line_amount(10_000_000, RATE_7, 200_000, 31, 31)
        assert amount == 700_000
        assert applied is False

    def test_exact_tie_is_not_minimum_applied(self) -> None:
        # 7% of 1,000,000 = 70,000 == minimum -> the percentage suffices.
        amount, applied = compute_line_amount(1_000_000, RATE_7, 70_000, 31, 31)
        assert amount == 70_000
        assert applied is False

    def test_minimum_prorates_but_percentage_never_does(self) -> None:
        # Active 15 of 30 days: floor halves to 100,000; 7% of 2,000,000 stays 140,000.
        amount, applied = compute_line_amount(2_000_000, RATE_7, 200_000, 15, 30)
        assert amount == 140_000
        assert applied is False
        # Same activation, weak revenue: halved floor still binds.
        amount, applied = compute_line_amount(1_000_000, RATE_7, 200_000, 15, 30)
        assert amount == 100_000
        assert applied is True

    def test_negative_net_base_clamps_to_zero_without_minimum(self) -> None:
        # Refunds exceeding gross never produce a negative royalty.
        amount, applied = compute_line_amount(-50_000, RATE_7, None, 31, 31)
        assert amount == 0
        assert applied is False

    def test_negative_net_base_still_owes_minimum(self) -> None:
        amount, applied = compute_line_amount(-50_000, RATE_7, 200_000, 31, 31)
        assert amount == 200_000
        assert applied is True


def _line(
    location_id: uuid.UUID | None = None,
    report_id: uuid.UUID | None = None,
    net_base_cents: int = 1_000_000,
    rate: Decimal = RATE_7,
    monthly_minimum_cents: int | None = None,
) -> LineInput:
    return LineInput(
        location_id=location_id or uuid.uuid4(),
        org_id=uuid.uuid4(),
        report_id=report_id or uuid.uuid4(),
        net_base_cents=net_base_cents,
        rate=rate,
        monthly_minimum_cents=monthly_minimum_cents,
        active_days=31,
        days_in_period=31,
    )


class TestFingerprint:
    def test_deterministic_and_order_insensitive(self) -> None:
        a, b = _line(), _line()
        ex = ExclusionInput(uuid.uuid4(), uuid.uuid4(), "no_locked_report")
        assert compute_fingerprint(PERIOD, [a, b], [ex]) == compute_fingerprint(
            PERIOD, [b, a], [ex]
        )

    def test_changed_report_id_changes_fingerprint(self) -> None:
        loc = uuid.uuid4()
        original = _line(location_id=loc)
        corrected = _line(location_id=loc)  # same figures, new report row
        assert compute_fingerprint(PERIOD, [original], []) != compute_fingerprint(
            PERIOD, [corrected], []
        )

    def test_changed_figures_change_fingerprint(self) -> None:
        base = _line()
        for variant in (
            LineInput(
                base.location_id,
                base.org_id,
                base.report_id,
                base.net_base_cents + 1,
                base.rate,
                base.monthly_minimum_cents,
                base.active_days,
                base.days_in_period,
            ),
            LineInput(
                base.location_id,
                base.org_id,
                base.report_id,
                base.net_base_cents,
                Decimal("0.0500"),
                base.monthly_minimum_cents,
                base.active_days,
                base.days_in_period,
            ),
            LineInput(
                base.location_id,
                base.org_id,
                base.report_id,
                base.net_base_cents,
                base.rate,
                200_000,
                base.active_days,
                base.days_in_period,
            ),
        ):
            assert compute_fingerprint(PERIOD, [base], []) != compute_fingerprint(
                PERIOD, [variant], []
            )

    def test_exclusions_are_part_of_the_inputs(self) -> None:
        line = _line()
        loc = uuid.uuid4()
        org = uuid.uuid4()
        without = compute_fingerprint(PERIOD, [line], [])
        with_exclusion = compute_fingerprint(
            PERIOD, [line], [ExclusionInput(loc, org, "no_locked_report")]
        )
        other_reason = compute_fingerprint(
            PERIOD, [line], [ExclusionInput(loc, org, "no_active_agreement")]
        )
        assert len({without, with_exclusion, other_reason}) == 3

    def test_period_is_part_of_the_inputs(self) -> None:
        line = _line()
        assert compute_fingerprint(PERIOD, [line], []) != compute_fingerprint(
            date(2026, 8, 1), [line], []
        )


class TestAgingBucket:
    def test_bucket_boundaries(self) -> None:
        assert aging_bucket(0) == "0-30"
        assert aging_bucket(30) == "0-30"
        assert aging_bucket(31) == "31-60"
        assert aging_bucket(60) == "31-60"
        assert aging_bucket(61) == "61-90"
        assert aging_bucket(90) == "61-90"
        assert aging_bucket(91) == "90+"
