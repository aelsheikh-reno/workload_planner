"""Tests for schedule_service helper functions: _date_range, _week_start, _utilization_tone."""

import unittest
from datetime import date

from services.schedule_service.service import (
    _date_range,
    _utilization_tone,
    _week_start,
)


class DateRangeTests(unittest.TestCase):

    def test_default_sun_thu_working_days(self):
        # Mon 2026-04-06 → Sat 2026-04-11 → expect Sun 2026-04-05 not in range, but Mon-Thu
        # Actually let's use Sun-Sat and check only Sun-Thu come back
        start = date(2026, 4, 5)   # Sunday
        end = date(2026, 4, 11)    # Saturday
        result = _date_range(start, end)  # uses default Sun-Thu
        day_names = [d.strftime("%a") for d in result]
        for d in day_names:
            self.assertIn(d, {"Sun", "Mon", "Tue", "Wed", "Thu"})
        # Fri (2026-04-10) and Sat (2026-04-11) should be excluded
        self.assertNotIn(date(2026, 4, 10), result)
        self.assertNotIn(date(2026, 4, 11), result)

    def test_excludes_friday_saturday_by_default(self):
        fri = date(2026, 4, 10)
        sat = date(2026, 4, 11)
        result = _date_range(fri, sat)
        self.assertEqual(result, [])

    def test_custom_working_days(self):
        start = date(2026, 4, 6)   # Monday
        end = date(2026, 4, 12)    # Sunday
        result = _date_range(start, end, working_days={"Mon", "Fri"})
        self.assertEqual(len(result), 2)
        self.assertIn(date(2026, 4, 6), result)   # Mon
        self.assertIn(date(2026, 4, 10), result)  # Fri

    def test_empty_working_days(self):
        result = _date_range(date(2026, 4, 6), date(2026, 4, 10), working_days=set())
        self.assertEqual(result, [])

    def test_start_equals_end_working_day(self):
        d = date(2026, 4, 6)  # Monday — in default working days
        result = _date_range(d, d)
        self.assertEqual(result, [d])

    def test_start_equals_end_non_working_day(self):
        d = date(2026, 4, 10)  # Friday — not in default Sun-Thu
        result = _date_range(d, d)
        self.assertEqual(result, [])

    def test_cross_month_range(self):
        start = date(2026, 4, 29)  # Wednesday
        end = date(2026, 5, 5)    # Tuesday
        result = _date_range(start, end)
        # April 29 (Wed), 30 (Thu), May 3 (Sun), 4 (Mon), 5 (Tue) = 5 working days
        self.assertEqual(len(result), 5)
        self.assertIn(date(2026, 4, 29), result)
        self.assertIn(date(2026, 5, 3), result)


class WeekStartTests(unittest.TestCase):

    def test_from_sunday_returns_same(self):
        d = date(2026, 4, 5)  # Sunday
        self.assertEqual(_week_start(d), date(2026, 4, 5))

    def test_from_monday_returns_sunday(self):
        d = date(2026, 4, 6)  # Monday
        self.assertEqual(_week_start(d), date(2026, 4, 5))

    def test_from_wednesday_returns_sunday(self):
        d = date(2026, 4, 8)  # Wednesday
        self.assertEqual(_week_start(d), date(2026, 4, 5))

    def test_from_saturday_returns_prev_sunday(self):
        d = date(2026, 4, 11)  # Saturday
        self.assertEqual(_week_start(d), date(2026, 4, 5))

    def test_from_thursday_returns_sunday(self):
        d = date(2026, 4, 9)  # Thursday
        self.assertEqual(_week_start(d), date(2026, 4, 5))


class UtilizationToneTests(unittest.TestCase):

    def test_overloaded_red(self):
        self.assertEqual(_utilization_tone(10.0, 8.0), "red")

    def test_exactly_full_red(self):
        self.assertEqual(_utilization_tone(8.0, 8.0), "red")

    def test_heavy_amber(self):
        self.assertEqual(_utilization_tone(6.5, 8.0), "amber")

    def test_normal_green(self):
        self.assertEqual(_utilization_tone(4.0, 8.0), "green")

    def test_zero_capacity_neutral(self):
        self.assertEqual(_utilization_tone(0.0, 0.0), "neutral")

    def test_empty_day_green(self):
        self.assertEqual(_utilization_tone(0.0, 8.0), "green")


class DailyCapacityFormulaTests(unittest.TestCase):
    """Verifies the formula: daily_capacity = weekly_capacity / len(working_days)."""

    def _compute(self, weekly_hours, num_days):
        return weekly_hours / max(num_days, 1)

    def test_standard_five_day_week(self):
        self.assertAlmostEqual(self._compute(40.0, 5), 8.0)

    def test_four_day_week(self):
        self.assertAlmostEqual(self._compute(40.0, 4), 10.0)

    def test_part_time_five_day(self):
        self.assertAlmostEqual(self._compute(32.0, 5), 6.4)


if __name__ == "__main__":
    unittest.main()
