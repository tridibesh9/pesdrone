from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from pi_companion.models import Detection, FrameBundle
from pi_companion.perception.detector_classical import ClassicalDetector, DetectorConfig


@dataclass(slots=True)
class PixelPoint:
    detection_id: str
    x: float
    y: float
    confidence: float
    severity: str


@dataclass(slots=True)
class PixelCluster:
    cluster_id: str
    members: list[PixelPoint]
    centroid_x: float
    centroid_y: float
    radius_px: float
    mean_confidence: float


@dataclass(slots=True)
class RouteNode:
    order: int
    cluster_id: str
    x: float
    y: float


def run_trial(
    image_path: Path,
    output_dir: Path,
    detector_config: DetectorConfig,
    cluster_radius_px: float,
    speed_mps: float,
    system_delay_s: float,
    ground_sample_m_per_px: float,
    auto_tune: bool,
    show_detection_labels: bool,
    target_mode: str,
    exg_brown_threshold: float,
    border_exclusion_ratio: float,
) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    image = Image.open(image_path).convert("RGB")
    rgb = np.asarray(image)

    detections = _detect_with_optional_tune(
        rgb,
        detector_config,
        auto_tune,
        target_mode,
        exg_brown_threshold,
    )
    used_config = _last_used_config

    points = [
        PixelPoint(
            detection_id=detection.detection_id,
            x=float(detection.pixel_x),
            y=float(detection.pixel_y),
            confidence=detection.confidence,
            severity=detection.severity,
        )
        for detection in detections
    ]
    points = _filter_border_points(
        points,
        width=image.width,
        height=image.height,
        border_exclusion_ratio=border_exclusion_ratio,
    )

    clusters = cluster_pixel_points(points, cluster_radius_px)
    route = plan_route_nodes(
        clusters,
        start_x=image.width * 0.08,
        start_y=image.height * 0.90,
        start_heading_deg=0.0,
        turn_penalty_px=max(image.width, image.height) * 0.20,
    )

    lead_distance_m = speed_mps * system_delay_s
    lead_distance_px = lead_distance_m / max(ground_sample_m_per_px, 1e-6)

    mask_path = output_dir / f"{image_path.stem}_stress_mask.png"
    overlay_path = output_dir / f"{image_path.stem}_patch_overlay.png"
    summary_path = output_dir / f"{image_path.stem}_trial_report.json"

    if target_mode == "brown":
        mask = build_brown_mask(rgb, exg_threshold=exg_brown_threshold)
    else:
        mask = build_stress_mask(rgb, used_config)
    Image.fromarray(mask, mode="L").save(mask_path)

    overlay = draw_overlay(
        image=image,
        points=points,
        clusters=clusters,
        route=route,
        lead_distance_px=lead_distance_px,
        show_detection_labels=show_detection_labels,
    )
    overlay.save(overlay_path)

    summary = {
        "image_path": str(image_path),
        "output_dir": str(output_dir),
        "detector_config": {
            "vegetation_threshold": used_config.vegetation_threshold,
            "stress_upper_threshold": used_config.stress_upper_threshold,
            "min_pixels": used_config.min_pixels,
            "max_detections": used_config.max_detections,
            "cell_size_px": used_config.cell_size_px,
            "target_mode": target_mode,
            "exg_brown_threshold": exg_brown_threshold,
            "border_exclusion_ratio": border_exclusion_ratio,
        },
        "counts": {
            "detections": len(points),
            "clusters": len(clusters),
            "route_nodes": len(route),
        },
        "timing": {
            "speed_mps": speed_mps,
            "system_delay_s": system_delay_s,
            "lead_distance_m": round(lead_distance_m, 3),
            "ground_sample_m_per_px": ground_sample_m_per_px,
            "lead_distance_px": round(lead_distance_px, 2),
        },
        "detections": [
            {
                "id": point.detection_id,
                "x": round(point.x, 2),
                "y": round(point.y, 2),
                "confidence": point.confidence,
                "severity": point.severity,
            }
            for point in points
        ],
        "clusters": [
            {
                "cluster_id": cluster.cluster_id,
                "size": len(cluster.members),
                "centroid": [round(cluster.centroid_x, 2), round(cluster.centroid_y, 2)],
                "radius_px": round(cluster.radius_px, 2),
                "mean_confidence": round(cluster.mean_confidence, 3),
                "member_ids": [member.detection_id for member in cluster.members],
            }
            for cluster in clusters
        ],
        "route": [
            {
                "order": node.order,
                "cluster_id": node.cluster_id,
                "x": round(node.x, 2),
                "y": round(node.y, 2),
            }
            for node in route
        ],
        "files": {
            "mask": str(mask_path),
            "overlay": str(overlay_path),
            "report": str(summary_path),
        },
    }

    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


_last_used_config = DetectorConfig()


def _detect_with_optional_tune(
    rgb: np.ndarray,
    base_config: DetectorConfig,
    auto_tune: bool,
    target_mode: str,
    exg_brown_threshold: float,
) -> list[Detection]:
    global _last_used_config

    if target_mode == "brown":
        _last_used_config = base_config
        if not auto_tune:
            brown_mask = build_brown_mask(rgb, exg_threshold=exg_brown_threshold)
            return _detections_from_binary_mask(brown_mask, base_config)

        thresholds = [
            max(0.18, exg_brown_threshold - 0.07),
            max(0.20, exg_brown_threshold - 0.04),
            exg_brown_threshold,
            min(0.45, exg_brown_threshold + 0.03),
            min(0.48, exg_brown_threshold + 0.06),
        ]

        height, width = rgb.shape[:2]
        best: list[Detection] = []
        best_score = -1e9
        for threshold in thresholds:
            brown_mask = build_brown_mask(rgb, exg_threshold=threshold)
            trial = _detections_from_binary_mask(brown_mask, base_config)
            score = _detection_quality_score(trial, width, height)
            if score > best_score:
                best = trial
                best_score = score
        return best

    detections = _run_detector(rgb, base_config)
    _last_used_config = base_config
    if detections or not auto_tune:
        return detections

    candidates = [
        DetectorConfig(0.15, 0.30, base_config.min_pixels, base_config.max_detections, base_config.cell_size_px),
        DetectorConfig(0.15, 0.35, base_config.min_pixels, base_config.max_detections, base_config.cell_size_px),
        DetectorConfig(0.20, 0.35, base_config.min_pixels, base_config.max_detections, base_config.cell_size_px),
        DetectorConfig(0.10, 0.30, max(12, base_config.min_pixels // 2), base_config.max_detections, base_config.cell_size_px),
        DetectorConfig(0.25, 0.40, base_config.min_pixels, base_config.max_detections, base_config.cell_size_px),
    ]

    height, width = rgb.shape[:2]
    best = detections
    best_score = _detection_quality_score(best, width, height)
    for candidate in candidates:
        trial = _run_detector(rgb, candidate)
        trial_score = _detection_quality_score(trial, width, height)
        if trial_score > best_score:
            best = trial
            _last_used_config = candidate
            best_score = trial_score
    return best


def _detection_quality_score(
    detections: list[Detection], width: int, height: int
) -> float:
    if not detections:
        return -1.0

    n = len(detections)
    mean_conf = sum(detection.confidence for detection in detections) / n
    border_margin_x = width * 0.08
    border_margin_y = height * 0.08
    border_hits = sum(
        1
        for detection in detections
        if detection.pixel_x < border_margin_x
        or detection.pixel_x > (width - border_margin_x)
        or detection.pixel_y < border_margin_y
        or detection.pixel_y > (height - border_margin_y)
    )
    border_ratio = border_hits / n
    return (mean_conf * n) - (border_ratio * n * 0.6)


def _run_detector(rgb: np.ndarray, config: DetectorConfig) -> list[Detection]:
    detector = ClassicalDetector(config)
    frame = FrameBundle(
        frame_id=1,
        timestamp_ms=int(time.time() * 1000),
        rgb=rgb,
        depth=None,
    )
    return detector.detect(frame)


def _detections_from_binary_mask(mask: np.ndarray, config: DetectorConfig) -> list[Detection]:
    y_idx, x_idx = np.where(mask > 0)
    if y_idx.size < config.min_pixels:
        return []

    counts: dict[tuple[int, int], int] = {}
    for x, y in zip(x_idx.tolist(), y_idx.tolist()):
        cell = (x // config.cell_size_px, y // config.cell_size_px)
        counts[cell] = counts.get(cell, 0) + 1

    top = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    total_pixels = float(mask.shape[0] * mask.shape[1])

    detections: list[Detection] = []
    for idx, ((cell_x, cell_y), count) in enumerate(top):
        if idx >= config.max_detections:
            break

        center_x = int(cell_x * config.cell_size_px + config.cell_size_px / 2)
        center_y = int(cell_y * config.cell_size_px + config.cell_size_px / 2)
        area_ratio = min(1.0, count / max(1.0, total_pixels * 0.01))
        confidence = round(0.45 + 0.55 * area_ratio, 3)
        severity = "high" if confidence >= 0.8 else "medium" if confidence >= 0.6 else "low"
        detections.append(
            Detection(
                detection_id=f"cell_{cell_x}_{cell_y}",
                frame_id=1,
                pixel_x=center_x,
                pixel_y=center_y,
                confidence=confidence,
                severity=severity,
                age_frames=1,
            )
        )

    return detections


def build_stress_mask(rgb: np.ndarray, config: DetectorConfig) -> np.ndarray:
    rgb_float = rgb.astype(np.float32) / 255.0
    red = rgb_float[:, :, 0]
    green = rgb_float[:, :, 1]
    gndvi = (green - red) / (green + red + 1e-6)
    vegetation = gndvi > config.vegetation_threshold
    stress = vegetation & (gndvi < config.stress_upper_threshold)
    return (stress.astype(np.uint8) * 255)


def build_brown_mask(rgb: np.ndarray, exg_threshold: float) -> np.ndarray:
    rgb_float = rgb.astype(np.float32) / 255.0
    red = rgb_float[:, :, 0]
    green = rgb_float[:, :, 1]
    blue = rgb_float[:, :, 2]
    value = np.max(rgb_float, axis=2)

    # ExG drops in dry/brown vegetation compared to healthy green cover.
    exg = (2.0 * green) - red - blue

    brown = (
        (green > blue + 0.03)
        & (red > blue + 0.08)
        & (exg < exg_threshold)
        & (value > 0.22)
        & (value < 0.92)
    )
    return (brown.astype(np.uint8) * 255)


def _filter_border_points(
    points: list[PixelPoint],
    width: int,
    height: int,
    border_exclusion_ratio: float,
) -> list[PixelPoint]:
    if not points or border_exclusion_ratio <= 0.0:
        return points

    margin_x = width * border_exclusion_ratio
    margin_y = height * border_exclusion_ratio
    filtered = [
        point
        for point in points
        if margin_x <= point.x <= (width - margin_x)
        and margin_y <= point.y <= (height - margin_y)
    ]
    return filtered


def cluster_pixel_points(points: list[PixelPoint], radius_px: float) -> list[PixelCluster]:
    if not points:
        return []

    clusters: list[PixelCluster] = []
    ordered_points = sorted(points, key=lambda point: point.confidence, reverse=True)

    for point in ordered_points:
        best_idx = -1
        best_distance = float("inf")

        for idx, cluster in enumerate(clusters):
            d = distance_px(point.x, point.y, cluster.centroid_x, cluster.centroid_y)
            if d <= radius_px and d < best_distance:
                best_distance = d
                best_idx = idx

        if best_idx < 0:
            clusters.append(
                PixelCluster(
                    cluster_id=f"C{len(clusters) + 1}",
                    members=[point],
                    centroid_x=point.x,
                    centroid_y=point.y,
                    radius_px=18.0,
                    mean_confidence=point.confidence,
                )
            )
            continue

        updated_members = clusters[best_idx].members + [point]
        centroid_x = sum(member.x for member in updated_members) / len(updated_members)
        centroid_y = sum(member.y for member in updated_members) / len(updated_members)
        radius = max(
            distance_px(member.x, member.y, centroid_x, centroid_y)
            for member in updated_members
        )
        mean_confidence = sum(member.confidence for member in updated_members) / len(
            updated_members
        )

        clusters[best_idx] = PixelCluster(
            cluster_id=clusters[best_idx].cluster_id,
            members=updated_members,
            centroid_x=centroid_x,
            centroid_y=centroid_y,
            radius_px=max(18.0, radius + 16.0),
            mean_confidence=mean_confidence,
        )

    return sorted(clusters, key=lambda cluster: cluster.mean_confidence, reverse=True)


def plan_route_nodes(
    clusters: list[PixelCluster],
    start_x: float,
    start_y: float,
    start_heading_deg: float,
    turn_penalty_px: float,
) -> list[RouteNode]:
    remaining = {cluster.cluster_id: cluster for cluster in clusters}
    route: list[RouteNode] = []

    current_x = start_x
    current_y = start_y
    current_heading = start_heading_deg
    order = 0

    while remaining:
        selected = min(
            remaining.values(),
            key=lambda cluster: _route_cost(
                cluster,
                current_x,
                current_y,
                current_heading,
                turn_penalty_px,
            ),
        )
        order += 1
        route.append(
            RouteNode(
                order=order,
                cluster_id=selected.cluster_id,
                x=selected.centroid_x,
                y=selected.centroid_y,
            )
        )
        del remaining[selected.cluster_id]

        next_heading = bearing_image_deg(
            current_x,
            current_y,
            selected.centroid_x,
            selected.centroid_y,
        )
        current_heading = next_heading
        current_x = selected.centroid_x
        current_y = selected.centroid_y

    return route


def draw_overlay(
    image: Image.Image,
    points: list[PixelPoint],
    clusters: list[PixelCluster],
    route: list[RouteNode],
    lead_distance_px: float,
    show_detection_labels: bool,
) -> Image.Image:
    canvas = image.copy().convert("RGB")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    for point in points:
        r = 7
        draw.ellipse(
            (point.x - r, point.y - r, point.x + r, point.y + r),
            outline=(255, 70, 70),
            width=2,
        )
        if show_detection_labels:
            draw.text(
                (point.x + 6, point.y - 10),
                f"{point.detection_id}:{point.confidence:.2f}",
                fill=(255, 60, 60),
                font=font,
            )

    for cluster in clusters:
        r = cluster.radius_px
        draw.ellipse(
            (
                cluster.centroid_x - r,
                cluster.centroid_y - r,
                cluster.centroid_x + r,
                cluster.centroid_y + r,
            ),
            outline=(0, 225, 225),
            width=3,
        )
        draw.text(
            (cluster.centroid_x + 6, cluster.centroid_y + 8),
            f"{cluster.cluster_id} ({len(cluster.members)})",
            fill=(0, 235, 235),
            font=font,
        )

    prev = (image.width * 0.08, image.height * 0.90)
    for node in route:
        draw.line((prev[0], prev[1], node.x, node.y), fill=(70, 120, 255), width=3)
        _draw_arrow(draw, prev[0], prev[1], node.x, node.y, (70, 120, 255))
        draw.text((node.x + 8, node.y + 18), f"R{node.order}", fill=(70, 120, 255), font=font)

        lead = _lead_point(prev[0], prev[1], node.x, node.y, lead_distance_px)
        if lead is not None:
            lx, ly = lead
            draw.ellipse((lx - 5, ly - 5, lx + 5, ly + 5), fill=(255, 190, 40), outline=(255, 160, 0), width=2)

        prev = (node.x, node.y)

    banner_h = 46
    draw.rectangle((0, 0, image.width, banner_h), fill=(10, 10, 10))
    draw.text(
        (10, 10),
        f"Detections: {len(points)} | Clusters: {len(clusters)} | Route Nodes: {len(route)} | Lead(px): {lead_distance_px:.1f}",
        fill=(245, 245, 245),
        font=font,
    )

    return canvas


def _lead_point(x0: float, y0: float, x1: float, y1: float, lead_px: float) -> tuple[float, float] | None:
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length <= 1e-6 or length < lead_px:
        return None

    ux = dx / length
    uy = dy / length
    return x1 - ux * lead_px, y1 - uy * lead_px


def _draw_arrow(
    draw: ImageDraw.ImageDraw,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    color: tuple[int, int, int],
) -> None:
    angle = math.atan2(y1 - y0, x1 - x0)
    head_len = 10.0
    left = (
        x1 - head_len * math.cos(angle - math.pi / 7.0),
        y1 - head_len * math.sin(angle - math.pi / 7.0),
    )
    right = (
        x1 - head_len * math.cos(angle + math.pi / 7.0),
        y1 - head_len * math.sin(angle + math.pi / 7.0),
    )
    draw.polygon([(x1, y1), left, right], fill=color)


def _route_cost(
    cluster: PixelCluster,
    x: float,
    y: float,
    heading_deg: float,
    turn_penalty_px: float,
) -> float:
    dist = distance_px(x, y, cluster.centroid_x, cluster.centroid_y)
    bearing = bearing_image_deg(x, y, cluster.centroid_x, cluster.centroid_y)
    heading_err = abs(angle_diff_deg(heading_deg, bearing))
    return dist + (heading_err / 180.0) * turn_penalty_px - cluster.mean_confidence * 8.0


def distance_px(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.hypot(x2 - x1, y2 - y1)


def bearing_image_deg(x1: float, y1: float, x2: float, y2: float) -> float:
    angle = math.degrees(math.atan2(-(y2 - y1), x2 - x1))
    return (angle + 360.0) % 360.0


def angle_diff_deg(a: float, b: float) -> float:
    return (b - a + 180.0) % 360.0 - 180.0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one-image detection and patch clustering trial")
    parser.add_argument("--image", required=True, help="Path to input image")
    parser.add_argument(
        "--output-dir",
        default=".runtime/image-trial",
        help="Directory for generated overlay/mask/report",
    )
    parser.add_argument("--vegetation-threshold", type=float, default=0.20)
    parser.add_argument("--stress-upper-threshold", type=float, default=0.35)
    parser.add_argument("--min-pixels", type=int, default=25)
    parser.add_argument("--max-detections", type=int, default=8)
    parser.add_argument("--cell-size-px", type=int, default=28)
    parser.add_argument("--cluster-radius-px", type=float, default=70.0)
    parser.add_argument("--speed-mps", type=float, default=14.0)
    parser.add_argument("--system-delay-s", type=float, default=0.40)
    parser.add_argument("--ground-sample-m-per-px", type=float, default=0.05)
    parser.add_argument("--disable-auto-tune", action="store_true")
    parser.add_argument("--show-detection-labels", action="store_true")
    parser.add_argument(
        "--target-mode",
        default="brown",
        choices=["brown", "classic"],
        help="Detection mode: brown for brown/dry patch focus, classic for legacy stress band.",
    )
    parser.add_argument(
        "--exg-brown-threshold",
        type=float,
        default=0.30,
        help="ExG upper threshold used in brown mode (lower = stricter).",
    )
    parser.add_argument(
        "--border-exclusion-ratio",
        type=float,
        default=0.06,
        help="Fractional image border width to ignore for detections.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    image_path = Path(args.image).expanduser().resolve()
    if not image_path.exists():
        raise FileNotFoundError(f"Image does not exist: {image_path}")

    config = DetectorConfig(
        vegetation_threshold=args.vegetation_threshold,
        stress_upper_threshold=args.stress_upper_threshold,
        min_pixels=args.min_pixels,
        max_detections=args.max_detections,
        cell_size_px=args.cell_size_px,
    )

    summary = run_trial(
        image_path=image_path,
        output_dir=Path(args.output_dir).expanduser().resolve(),
        detector_config=config,
        cluster_radius_px=args.cluster_radius_px,
        speed_mps=args.speed_mps,
        system_delay_s=args.system_delay_s,
        ground_sample_m_per_px=args.ground_sample_m_per_px,
        auto_tune=not args.disable_auto_tune,
        show_detection_labels=args.show_detection_labels,
        target_mode=args.target_mode,
        exg_brown_threshold=args.exg_brown_threshold,
        border_exclusion_ratio=args.border_exclusion_ratio,
    )

    print("Image trial completed.")
    print(f"Detections: {summary['counts']['detections']}")
    print(f"Clusters: {summary['counts']['clusters']}")
    print(f"Overlay: {summary['files']['overlay']}")
    print(f"Mask: {summary['files']['mask']}")
    print(f"Report: {summary['files']['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
