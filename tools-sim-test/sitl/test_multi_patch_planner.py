from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pi-companion" / "src"))

from pi_companion.models import ProjectedTarget
from pi_companion.planning.multi_patch_planner import (
    AircraftPose,
    MultiPatchPlanner,
    PlannerConfig,
    destination_point_m,
)


def test_multi_patch_clustering_groups_near_points() -> None:
    planner = MultiPatchPlanner(
        PlannerConfig(dedupe_radius_m=0.2, cluster_radius_m=15.0, min_points_per_cluster=1)
    )

    targets = [
        ProjectedTarget("a1", 22.57280, 88.36440, 0.90, 4),
        ProjectedTarget("a2", 22.57279, 88.36442, 0.84, 4),
        ProjectedTarget("a3", 22.57282, 88.36439, 0.86, 5),
        ProjectedTarget("b1", 22.57340, 88.36550, 0.91, 4),
    ]

    planner.ingest_targets(targets, timestamp_ms=1_000)
    clusters = planner.build_clusters()

    assert len(clusters) == 2
    assert sum(len(cluster.patch_ids) for cluster in clusters) == 4


def test_route_planning_creates_leg_per_cluster() -> None:
    planner = MultiPatchPlanner(PlannerConfig(cluster_radius_m=12.0))
    targets = [
        ProjectedTarget("c1", 22.57280, 88.36440, 0.90, 4),
        ProjectedTarget("c2", 22.57310, 88.36495, 0.81, 4),
        ProjectedTarget("c3", 22.57342, 88.36555, 0.88, 4),
    ]

    planner.ingest_targets(targets, timestamp_ms=2_000)
    clusters = planner.build_clusters()
    legs = planner.plan_route(start_lat=22.5726, start_lon=88.3639, start_heading_deg=90.0)

    assert len(legs) == len(clusters)
    assert planner.active_leg() is not None


def test_lead_window_allows_spray_for_ahead_target() -> None:
    planner = MultiPatchPlanner(
        PlannerConfig(system_delay_s=0.40, trigger_window_m=2.0, default_speed_mps=14.0)
    )

    target = ProjectedTarget("lead", 22.57290, 88.36450, 0.93, 5)
    planner.ingest_targets([target], timestamp_ms=3_000)
    planner.build_clusters()
    planner.plan_route(start_lat=22.5726, start_lon=88.3639, start_heading_deg=90.0)

    lead_distance = 14.0 * 0.40
    pose_lat, pose_lon = destination_point_m(target.lat, target.lon, 270.0, lead_distance)

    opportunity = planner.select_spray_target(
        pose=AircraftPose(
            timestamp_ms=3_200,
            lat=pose_lat,
            lon=pose_lon,
            heading_deg=90.0,
            speed_mps=14.0,
        ),
        targets=[target],
    )

    assert opportunity.should_spray is True
    assert opportunity.reason == "within_lead_window"
