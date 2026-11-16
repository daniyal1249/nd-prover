import unittest

from benchmarks.validity.report import _percentile, summarize


class BenchmarkReportTests(unittest.TestCase):

    def test_unknown_gold_case_is_unsolved_not_wrong(self):
        records = [
            {
                "library": "ILTP",
                "logic": "IPL",
                "source_domain": None,
                "source_status": "Theorem",
                "expected_status": "valid",
                "status": "unknown",
                "matches_expected": None,
                "elapsed_ms": 1000.0,
                "cpu_ms": 999.0
            }
        ]

        summary = summarize(records)[0]

        self.assertEqual(summary["expected_cases"], 1)
        self.assertEqual(summary["expected_solved"], 0)
        self.assertEqual(summary["expected_matches"], 0)
        self.assertEqual(summary["expected_mismatches"], 0)

    def test_wrong_answer_is_counted_as_mismatch(self):
        records = [
            {
                "library": "QMLTP",
                "logic": "QK",
                "source_domain": "constant",
                "source_status": "Theorem",
                "expected_status": "valid",
                "status": "invalid",
                "matches_expected": False,
                "elapsed_ms": 10.0,
                "cpu_ms": 9.0
            }
        ]

        summary = summarize(records)[0]

        self.assertEqual(summary["expected_solved"], 1)
        self.assertEqual(summary["expected_matches"], 0)
        self.assertEqual(summary["expected_mismatches"], 1)

    def test_watchdog_records_do_not_invent_cpu_measurements(self):
        records = [
            {"status": "unknown", "hard_timeout": True, "elapsed_ms": 12000},
            {"status": "valid", "elapsed_ms": 10, "cpu_ms": 8}
        ]
        summary = summarize(records, ())[0]
        self.assertEqual(summary["hard_timeouts"], 1)
        self.assertEqual(summary["mean_cpu_ms"], 8)
        self.assertEqual(summary["solved_mean_ms"], 10)
        self.assertEqual(summary["mean_ms"], 6005)

    def test_percentile_uses_nearest_rank(self):
        self.assertEqual(_percentile(list(range(1, 22)), 0.95), 20)


if __name__ == "__main__":
    unittest.main()

