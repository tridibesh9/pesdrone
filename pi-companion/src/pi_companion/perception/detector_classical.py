from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from pi_companion.models import Detection, FrameBundle


@dataclass(slots=True)
class DetectorConfig:
    vegetation_threshold: float = 0.20
    stress_upper_threshold: float = 0.35
    min_pixels: int = 25
    max_detections: int = 4
    cell_size_px: int = 32


class ClassicalDetector:
    def __init__(self, config: DetectorConfig | None = None) -> None:
        self.config = config or DetectorConfig()
        self._age_map: dict[tuple[int, int], int] = {}

    def detect(self, bundle: FrameBundle) -> list[Detection]:
        rgb = np.asarray(bundle.rgb)
        if rgb.ndim != 3 or rgb.shape[2] < 3:
            return []

        rgb_float = rgb.astype(np.float32) / 255.0
        red = rgb_float[:, :, 0]
        green = rgb_float[:, :, 1]

        gndvi = (green - red) / (green + red + 1e-6)
        vegetation_mask = gndvi > self.config.vegetation_threshold
        stressed_mask = vegetation_mask & (gndvi < self.config.stress_upper_threshold)

        y_idx, x_idx = np.where(stressed_mask)
        if y_idx.size < self.config.min_pixels:
            return []

        cells = self._top_cells(x_idx, y_idx)
        detections: list[Detection] = []

        for idx, (cell_x, cell_y, count) in enumerate(cells):
            if idx >= self.config.max_detections:
                break

            center_x = int(cell_x * self.config.cell_size_px + self.config.cell_size_px / 2)
            center_y = int(cell_y * self.config.cell_size_px + self.config.cell_size_px / 2)

            confidence = self._confidence_from_count(count, stressed_mask.size)
            severity = "high" if confidence >= 0.8 else "medium" if confidence >= 0.6 else "low"
            age = self._next_age(cell_x, cell_y)

            detections.append(
                Detection(
                    detection_id=f"cell_{cell_x}_{cell_y}",
                    frame_id=bundle.frame_id,
                    pixel_x=center_x,
                    pixel_y=center_y,
                    confidence=confidence,
                    severity=severity,
                    age_frames=age,
                )
            )

        return detections

    def _top_cells(self, x_idx: np.ndarray, y_idx: np.ndarray) -> list[tuple[int, int, int]]:
        counts: dict[tuple[int, int], int] = {}
        for x, y in zip(x_idx.tolist(), y_idx.tolist()):
            cell = (x // self.config.cell_size_px, y // self.config.cell_size_px)
            counts[cell] = counts.get(cell, 0) + 1

        top = sorted(
            ((cx, cy, count) for (cx, cy), count in counts.items()),
            key=lambda entry: entry[2],
            reverse=True,
        )
        return top

    @staticmethod
    def _confidence_from_count(cell_count: int, frame_area: int) -> float:
        area_ratio = min(1.0, cell_count / max(1.0, frame_area * 0.02))
        return round(0.45 + 0.55 * area_ratio, 3)

    def _next_age(self, cell_x: int, cell_y: int) -> int:
        key = (cell_x, cell_y)
        age = self._age_map.get(key, 0) + 1
        self._age_map[key] = age
        return age
