"""V8.2 phase-2 read-only real-frame capture unit tests (synthetic pixels)."""

import base64
import importlib.util
from pathlib import Path
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "agents" / "templates" / "ls20_level2_frame_capture.py"
spec = importlib.util.spec_from_file_location("level2_capture_v82_tests", MODULE)
assert spec is not None and spec.loader is not None
capture_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture_module)
LS20Level2FrameCapture = capture_module.LS20Level2FrameCapture


def frame(*, pixel=5):
    return [[pixel for _ in range(64)] for _ in range(64)]


def decode(sample):
    return zlib.decompress(base64.b64decode(sample["pixels_base64"]))


class Level2FrameCaptureV82Tests(unittest.TestCase):
    def test_only_second_level_is_captured(self):
        recorder = LS20Level2FrameCapture()
        self.assertFalse(recorder.observe([frame()], level=0))
        self.assertFalse(recorder.observe([frame()], level=2))
        self.assertEqual(recorder.summary()["observations"], 0)

    def test_first_real_frame_pixel_roundtrip_is_exact(self):
        g = frame()
        g[0][0] = 12
        g[63][63] = 9
        recorder = LS20Level2FrameCapture()
        self.assertTrue(recorder.observe([g], level=1))
        sample = recorder.summary()["samples"][0]
        expected = bytes(pixel for row in g for pixel in row)
        self.assertEqual(decode(sample), expected)
        self.assertEqual(len(decode(sample)), 4096)

    def test_only_latest_visible_frame_is_sampled(self):
        recorder = LS20Level2FrameCapture()
        self.assertTrue(recorder.observe([frame(pixel=1), frame(pixel=9)], level=1))
        self.assertEqual(decode(recorder.summary()["samples"][0]), bytes([9]) * 4096)

    def test_invalid_or_ambiguous_pixels_not_silently_converted(self):
        recorder = LS20Level2FrameCapture()
        self.assertFalse(recorder.observe([[[1]]], level=1))
        self.assertFalse(recorder.observe([frame(pixel=1.5)], level=1))
        self.assertFalse(recorder.observe([frame(pixel=-1)], level=1))
        self.assertFalse(recorder.observe([frame(pixel=256)], level=1))
        self.assertEqual(recorder.summary()["invalid_frames"], 4)
        self.assertEqual(recorder.summary()["samples"], [])

    def test_throttling_and_sample_cap(self):
        recorder = LS20Level2FrameCapture()
        for i in range(30):
            g = frame(pixel=i % 10)
            recorder.observe([g], level=1)
        samples = recorder.summary()["samples"]
        self.assertEqual(len(samples), 3)
        self.assertEqual([s["level2_observation"] for s in samples], [1, 6, 17])
        self.assertEqual(recorder.summary()["observations"], 30)

    def test_duplicate_visible_frames_are_skipped(self):
        recorder = LS20Level2FrameCapture()
        for _ in range(7):
            recorder.observe([frame(pixel=5)], level=1)
        self.assertEqual(recorder.summary()["captured_samples"], 1)
        self.assertEqual(recorder.summary()["duplicate_frames_skipped"], 2)
        self.assertTrue(recorder.observe([frame(pixel=9)], level=1))
        self.assertEqual(recorder.summary()["captured_samples"], 2)

    def test_publishing_summary_cannot_modify_internal_samples(self):
        recorder = LS20Level2FrameCapture()
        recorder.observe([frame()], level=1)
        published = recorder.summary()
        published["samples"].clear()
        self.assertEqual(recorder.summary()["captured_samples"], 1)


if __name__ == "__main__":
    unittest.main()
