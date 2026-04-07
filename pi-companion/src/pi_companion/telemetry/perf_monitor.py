from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass(slots=True)
class PerfSample:
    latency_ms: float
    fps: float
    cpu_temp_c: float
    memory_mb: float
    dropped_frame_rate: float


class PerformanceMonitor:
    def __init__(self, window_size: int = 120) -> None:
        self._samples: deque[PerfSample] = deque(maxlen=window_size)

    def record(self, sample: PerfSample) -> None:
        self._samples.append(sample)

    def summary(self) -> dict[str, float]:
        if not self._samples:
            return {
                "count": 0.0,
                "latency_p50_ms": 0.0,
                "latency_p95_ms": 0.0,
                "fps_mean": 0.0,
                "cpu_temp_max_c": 0.0,
                "memory_max_mb": 0.0,
                "drop_rate_mean": 0.0,
            }

        latencies = sorted(sample.latency_ms for sample in self._samples)
        fps = [sample.fps for sample in self._samples]
        cpu = [sample.cpu_temp_c for sample in self._samples]
        memory = [sample.memory_mb for sample in self._samples]
        drop_rates = [sample.dropped_frame_rate for sample in self._samples]

        return {
            "count": float(len(self._samples)),
            "latency_p50_ms": _percentile(latencies, 50),
            "latency_p95_ms": _percentile(latencies, 95),
            "fps_mean": sum(fps) / len(fps),
            "cpu_temp_max_c": max(cpu),
            "memory_max_mb": max(memory),
            "drop_rate_mean": sum(drop_rates) / len(drop_rates),
        }


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    idx = int(round((p / 100.0) * (len(sorted_values) - 1)))
    idx = max(0, min(len(sorted_values) - 1, idx))
    return sorted_values[idx]
