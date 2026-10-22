"""V8.2 phase-2: bounded, read-only capture of *rendered* LS20 level-2 frames.

The capture receives only the agent's visible 64x64 frame pixels, never
private engine data or solutions. It is deliberately NOT an action planner.
A future integration can publish ``summary()`` under game diagnostics.

Each accepted sample contains 4096 unsigned pixels compressed as zlib and
base64, in row-major order. Decoding is exact (lossless), enabling validation
against genuine second-level frames rather than just synthetic fixtures.
At most three samples are kept in memory in a single game run.
"""

from __future__ import annotations

import base64
from hashlib import blake2b
from operator import index
from typing import Any, Sequence
import zlib

LEVEL_2_INDEX = 1  # levels_completed == 1 denotes LS20's second level
IMAGE_SIZE = 64
SAMPLE_STEPS = (1, 6, 16)


def _latest_visible_bytes(frames: Sequence[Any]) -> bytes | None:
    """Encode just the last rendered 64x64 index-color frame as 4096 bytes.

    Reject malformed pixels; do not silently quantize floating-point colors.
    """
    try:
        if not frames:
            return None
        grid = frames[-1]
        if len(grid) != IMAGE_SIZE:
            return None
        flat = bytearray()
        for row in grid:
            if len(row) != IMAGE_SIZE:
                return None
            for cell in row:
                value = index(cell)
                if not 0 <= value <= 255:
                    return None
                flat.append(value)
        return bytes(flat)
    except (TypeError, ValueError, OverflowError, IndexError):
        return None


class LS20Level2FrameCapture:
    """Store at most three exact visible-frame samples; never affect actions."""

    def __init__(self) -> None:
        self.observations = 0
        self.invalid_frames = 0
        self.duplicates = 0
        self._samples: list[dict[str, Any]] = []
        self._last_digest: str | None = None

    def observe(self, frames: Sequence[Any], *, level: int) -> bool:
        """Return True only when a new level-2 sample was actually retained."""
        if level != LEVEL_2_INDEX:
            return False
        self.observations += 1
        if len(self._samples) >= len(SAMPLE_STEPS):
            return False
        if self.observations < SAMPLE_STEPS[len(self._samples)]:
            return False

        pixels = _latest_visible_bytes(frames)
        if pixels is None:
            self.invalid_frames += 1
            return False
        fingerprint = blake2b(pixels, digest_size=8).hexdigest()
        if fingerprint == self._last_digest:
            self.duplicates += 1
            return False
        self._last_digest = fingerprint

        sample: dict[str, Any] = {
            "level_index": LEVEL_2_INDEX,
            "level2_observation": self.observations,
            "fingerprint": fingerprint,
            "encoding": "zlib_base64_u8_rowmajor_64x64",
            "pixels_base64": base64.b64encode(zlib.compress(pixels, 9)).decode("ascii"),
        }
        self._samples.append(sample)
        return True

    def summary(self) -> dict[str, Any]:
        """Return JSON-safe, bounded evidence from this run only."""
        return {
            "enabled": True,
            "mode": "read_only_visible_frames",
            "scope": "ls20_level_2_only",
            "max_samples": len(SAMPLE_STEPS),
            "observations": self.observations,
            "captured_samples": len(self._samples),
            "invalid_frames": self.invalid_frames,
            "duplicate_frames_skipped": self.duplicates,
            "samples": [dict(sample) for sample in self._samples],
        }
