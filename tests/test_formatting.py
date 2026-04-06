import sys
import unittest
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.formatting import format_happened_at_display, normalize_western_number_commas


class TestFormatHappenedAt(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(format_happened_at_display(None), "")
        self.assertEqual(format_happened_at_display(""), "")

    def test_date_only_jst_midnight_display(self) -> None:
        self.assertEqual(format_happened_at_display("2026-01-01"), "2026-01-01 00:00")

    def test_iso_z_to_jst(self) -> None:
        # 2026-03-24 10:00 UTC = 19:00 JST
        self.assertEqual(
            format_happened_at_display("2026-03-24T10:00:00.000Z"),
            "2026-03-24 19:00",
        )

    def test_iso_z_single_digit_hours_padded(self) -> None:
        self.assertEqual(
            format_happened_at_display("2026-06-01T09:05:00Z"),
            "2026-06-01 18:05",
        )

    def test_unparseable_passthrough(self) -> None:
        self.assertEqual(format_happened_at_display("昨日の午後"), "昨日の午後")


class TestNormalizeWesternNumberCommas(unittest.TestCase):
    def test_malformed_commas_fixed(self) -> None:
        self.assertEqual(
            normalize_western_number_commas("売上 5213,213 円"),
            "売上 5,213,213 円",
        )
        self.assertEqual(
            normalize_western_number_commas("23000,000"),
            "23,000,000",
        )

    def test_already_correct(self) -> None:
        self.assertEqual(
            normalize_western_number_commas("1,234,567"),
            "1,234,567",
        )

    def test_year_unchanged(self) -> None:
        self.assertEqual(
            normalize_western_number_commas("2024年の売上"),
            "2024年の売上",
        )
        self.assertEqual(
            normalize_western_number_commas("2024-03-15"),
            "2024-03-15",
        )

    def test_small_numbers(self) -> None:
        self.assertEqual(normalize_western_number_commas("12名"), "12名")
        self.assertEqual(normalize_western_number_commas("第5位"), "第5位")

    def test_decimal_untouched(self) -> None:
        self.assertEqual(normalize_western_number_commas("3.14159"), "3.14159")


if __name__ == "__main__":
    unittest.main()
