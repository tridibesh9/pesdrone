from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pi-companion" / "src"))

from pi_companion.image_patch_trial import (  # noqa: E402
    PixelCluster,
    PixelPoint,
    cluster_pixel_points,
    plan_route_nodes,
)


def test_cluster_pixel_points_groups_neighbors() -> None:
    points = [
        PixelPoint("d1", 100.0, 100.0, 0.8, "medium"),
        PixelPoint("d2", 115.0, 102.0, 0.7, "medium"),
        PixelPoint("d3", 410.0, 300.0, 0.9, "high"),
    ]

    clusters = cluster_pixel_points(points, radius_px=28.0)

    assert len(clusters) == 2
    sizes = sorted(len(cluster.members) for cluster in clusters)
    assert sizes == [1, 2]


def test_plan_route_nodes_returns_all_clusters() -> None:
    clusters = [
        PixelCluster("C1", [], 120.0, 150.0, 20.0, 0.8),
        PixelCluster("C2", [], 420.0, 180.0, 25.0, 0.9),
        PixelCluster("C3", [], 300.0, 360.0, 30.0, 0.75),
    ]

    route = plan_route_nodes(
        clusters,
        start_x=40.0,
        start_y=430.0,
        start_heading_deg=0.0,
        turn_penalty_px=120.0,
    )

    assert len(route) == 3
    assert [node.order for node in route] == [1, 2, 3]
    assert sorted(node.cluster_id for node in route) == ["C1", "C2", "C3"]
