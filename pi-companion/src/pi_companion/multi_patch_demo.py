from __future__ import annotations

from pathlib import Path

from pi_companion.models import ProjectedTarget
from pi_companion.planning import AircraftPose, MultiPatchPlanner


def run_demo() -> None:
    planner = MultiPatchPlanner()
    start_lat = 22.5726
    start_lon = 88.3639
    start_heading = 92.0

    detections = _mock_projected_targets()
    planner.ingest_targets(detections, timestamp_ms=1_000)
    planner.build_clusters()
    route = planner.plan_route(start_lat=start_lat, start_lon=start_lon, start_heading_deg=start_heading)

    print("=== MULTI-PATCH MAPPING SUMMARY ===")
    summary = planner.summary()
    for key, value in summary.items():
        print(f"{key}: {value}")

    print("\n=== PLANNED SPRAY LEGS (FIXED-WING SAFE) ===")
    for index, leg in enumerate(route, start=1):
        print(
            f"{index}. {leg.leg_id} cluster={leg.cluster_id} "
            f"heading={leg.heading_deg:.1f} len={leg.length_m:.1f}m"
        )

    print("\n=== IN-FLIGHT SPRAY LOGIC DEMO ===")
    first_leg = planner.active_leg()
    if first_leg is None:
        print("No active leg.")
        return

    simulation = [
        AircraftPose(2_000, first_leg.entry_lat, first_leg.entry_lon, first_leg.heading_deg, 14.0),
        AircraftPose(2_400, first_leg.spray_start_lat, first_leg.spray_start_lon, first_leg.heading_deg, 14.0),
        AircraftPose(
            2_800,
            (first_leg.spray_start_lat + first_leg.spray_end_lat) / 2.0,
            (first_leg.spray_start_lon + first_leg.spray_end_lon) / 2.0,
            first_leg.heading_deg,
            14.0,
        ),
        AircraftPose(3_200, first_leg.spray_end_lat, first_leg.spray_end_lon, first_leg.heading_deg, 14.0),
        AircraftPose(3_600, first_leg.exit_lat, first_leg.exit_lon, first_leg.heading_deg, 14.0),
    ]

    for pose in simulation:
        opportunity = planner.select_spray_target(pose=pose, targets=detections)
        decision = "SPRAY" if opportunity.should_spray else "HOLD"
        print(
            f"t={pose.timestamp_ms} leg={opportunity.leg_id} decision={decision} "
            f"reason={opportunity.reason} lead={opportunity.lead_distance_m:.2f}m"
        )

    geojson_path = Path.cwd() / "multi_patch_demo.geojson"
    geojson_path.write_text(planner.export_geojson_text(), encoding="utf-8")
    print(f"\nSaved route map to: {geojson_path}")


def _mock_projected_targets() -> list[ProjectedTarget]:
    # Cluster 1: dense infected patch
    patch1 = [
        ProjectedTarget("d1", 22.57282, 88.36440, 0.88, 4),
        ProjectedTarget("d2", 22.57279, 88.36436, 0.82, 5),
        ProjectedTarget("d3", 22.57285, 88.36433, 0.80, 4),
    ]

    # Cluster 2: elongated patch along next strip
    patch2 = [
        ProjectedTarget("d4", 22.57310, 88.36498, 0.77, 3),
        ProjectedTarget("d5", 22.57313, 88.36505, 0.79, 4),
        ProjectedTarget("d6", 22.57305, 88.36502, 0.73, 3),
    ]

    # Cluster 3: isolated but high confidence patch
    patch3 = [ProjectedTarget("d7", 22.57342, 88.36555, 0.92, 4)]

    return patch1 + patch2 + patch3


if __name__ == "__main__":
    run_demo()
