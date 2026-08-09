"""
Voxora Studio - süre tahmini birim testleri.

estimate_duration_range pure helper'ı test eder. Qt bağımlılığı yok.
"""
from __future__ import annotations

import unittest

from app.main_window import estimate_duration_range


class DurationEstimateTests(unittest.TestCase):
    def test_zero_words(self):
        self.assertEqual(estimate_duration_range(0, 0, 1.0, 0.0), (0, 0))
        self.assertEqual(estimate_duration_range(0, 5, 0.9, 0.35), (0, 0))

    def test_default_speed_pause(self):
        # 100/170*60=35.29 -> 35; 100/130*60=46.15 -> 46
        self.assertEqual(estimate_duration_range(100, 1, 1.0, 0.0), (35, 46))

    def test_slow_speed(self):
        # 35.29/0.9=39.21 -> 39; 46.15/0.9=51.28 -> 51
        self.assertEqual(estimate_duration_range(100, 1, 0.9, 0.0), (39, 51))

    def test_pause_between_chunks(self):
        # 4 chunk -> 3 pause * 0.35 = 1.05 sn
        # 35.29 -> 35; 46.15 + 1.05 = 47.20 -> 47
        self.assertEqual(estimate_duration_range(100, 4, 1.0, 0.35), (35, 47))

    def test_fast_speed(self):
        # 35.29/1.6=22.06 -> 22; 46.15/1.6=28.84 -> 29
        self.assertEqual(estimate_duration_range(100, 1, 1.6, 0.0), (22, 29))

    def test_single_chunk_no_pause(self):
        # parts=1 -> n_pauses=0, pause dahil edilmez
        self.assertEqual(estimate_duration_range(100, 1, 1.0, 0.5), (35, 46))

    def test_zero_parts_with_words(self):
        # n_pauses = max(0, -1) = 0; pause ihmal
        self.assertEqual(estimate_duration_range(100, 0, 1.0, 0.35), (35, 46))

    def test_large_word_count(self):
        # 10000/170*60=3529.41 -> 3529; 10000/130*60=4615.38 -> 4615
        # 50 chunk -> 49 pause * 0.35 = 17.15
        # 4615.38 + 17.15 = 4632.53 -> 4633
        mn, mx = estimate_duration_range(10000, 50, 1.0, 0.35)
        self.assertEqual(mn, 3529)
        self.assertEqual(mx, 4633)


if __name__ == "__main__":
    unittest.main()
