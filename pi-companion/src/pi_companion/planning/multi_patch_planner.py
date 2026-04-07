from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

from pi_companion.models import ProjectedTarget


@dataclass(slots=True)
class PlannerConfig:
    dedupe_radius_m: float = 3.0
    cluster_radius_m: float = 14.0
    min_points_per_cluster: int = 1
    min_leg_length_m: float = 18.0
    max_leg_length_m: float = 60.0
    pre_entry_distance_m: float = 22.0
    post_exit_distance_m: float = 22.0
    min_turn_radius_m: float = 40.0
    heading_alignment_deg: float = 35.0
    trigger_window_m: float = 2.5
    default_speed_mps: float = 14.0
    system_delay_s: float = 0.40


@dataclass(slots=True)
class PatchPoint:
    patch_id: str
    lat: float
    lon: float
    confidence: float
    age_frames: int
    first_seen_ms: int
    last_seen_ms: int
    hits: int = 1

    @property
    def priority_score(self) -> float:
        return self.confidence * (1.0 + min(self.hits, 10) * 0.05)


@dataclass(slots=True)
class PatchCluster:
    cluster_id: str
    patch_ids: list[str]
    centroid_lat: float
    centroid_lon: float
    radius_m: float
    mean_confidence: float
    priority_score: float


@dataclass(slots=True)
class SprayLeg:
    leg_id: str
    cluster_id: str
    heading_deg: float
    length_m: float
    entry_lat: float
    entry_lon: float
    spray_start_lat: float
    spray_start_lon: float
    spray_end_lat: float
    spray_end_lon: float
    exit_lat: float
    exit_lon: float
    priority_score: float


@dataclass(slots=True)
class AircraftPose:
    timestamp_ms: int
    lat: float
    lon: float
    heading_deg: float
    speed_mps: float


@dataclass(slots=True)
class SprayOpportunity:
    should_spray: bool
    reason: str
    leg_id: str | None
    target: ProjectedTarget | None
    lead_distance_m: float
    distance_to_target_m: float | None = None
    heading_error_deg: float | None = None


class MultiPatchPlanner:
    def __init__(self, config: PlannerConfig | None = None) -> None:
        self.config = config or PlannerConfig()
        self._patch_counter = 0
        self._patches: dict[str, PatchPoint] = {}
        self._clusters: list[PatchCluster] = []
        self._legs: list[SprayLeg] = []
        self._completed_legs: set[str] = set()

    def ingest_targets(self, targets: list[ProjectedTarget], timestamp_ms: int) -> int:
        created = 0
        for target in targets:
            existing = self._find_existing_patch(target)
            if existing is not None:
                existing.last_seen_ms = timestamp_ms
                existing.hits += 1
                existing.age_frames = max(existing.age_frames, target.age_frames)
                existing.confidence = round(0.7 * existing.confidence + 0.3 * target.confidence, 4)
            else:
                created += 1
                self._patch_counter += 1
                patch_id = f"patch_{self._patch_counter:03d}"
                self._patches[patch_id] = PatchPoint(
                    patch_id=patch_id,
                    lat=target.lat,
                    lon=target.lon,
                    confidence=target.confidence,
                    age_frames=target.age_frames,
                    first_seen_ms=timestamp_ms,
                    last_seen_ms=timestamp_ms,
                )
        return created

    def build_clusters(self) -> list[PatchCluster]:
        ordered = sorted(
            self._patches.values(), key=lambda patch: patch.priority_score, reverse=True
        )
        remaining = {patch.patch_id: patch for patch in ordered}
        clusters: list[PatchCluster] = []
        cluster_index = 0

        while remaining:
            seed = next(iter(remaining.values()))
            member_ids = [seed.patch_id]
            del remaining[seed.patch_id]

            centroid_lat = seed.lat
            centroid_lon = seed.lon
            changed = True
            while changed:
                changed = False
                for patch_id, patch in list(remaining.items()):
                    if haversine_m(centroid_lat, centroid_lon, patch.lat, patch.lon) <= self.config.cluster_radius_m:
                        member_ids.append(patch_id)
                        del remaining[patch_id]
                        centroid_lat, centroid_lon = _centroid(
                            [(self._patches[mid].lat, self._patches[mid].lon) for mid in member_ids]
                        )
                        changed = True

            if len(member_ids) < self.config.min_points_per_cluster:
                continue

            cluster_index += 1
            member_points = [self._patches[mid] for mid in member_ids]
            radius_m = max(
                haversine_m(centroid_lat, centroid_lon, point.lat, point.lon)
                for point in member_points
            ) if member_points else 0.0
            mean_confidence = sum(point.confidence for point in member_points) / max(
                len(member_points), 1
            )
            priority_score = sum(point.priority_score for point in member_points)

            clusters.append(
                PatchCluster(
                    cluster_id=f"cluster_{cluster_index:03d}",
                    patch_ids=member_ids,
                    centroid_lat=centroid_lat,
                    centroid_lon=centroid_lon,
                    radius_m=radius_m,
                    mean_confidence=mean_confidence,
                    priority_score=priority_score,
                )
            )

        self._clusters = sorted(
            clusters, key=lambda cluster: cluster.priority_score, reverse=True
        )
        return list(self._clusters)

    def plan_route(self, start_lat: float, start_lon: float, start_heading_deg: float) -> list[SprayLeg]:
        if not self._clusters:
            self.build_clusters()

        candidate_legs = [
            self._cluster_to_leg(cluster, start_heading_deg)
            for cluster in self._clusters
            if cluster.cluster_id not in self._completed_legs
        ]

        ordered: list[SprayLeg] = []
        current_lat = start_lat
        current_lon = start_lon
        current_heading = start_heading_deg
        remaining = {leg.leg_id: leg for leg in candidate_legs}

        while remaining:
            next_leg = min(
                remaining.values(),
                key=lambda leg: self._leg_cost(
                    leg,
                    current_lat,
                    current_lon,
                    current_heading,
                ),
            )
            ordered.append(next_leg)
            del remaining[next_leg.leg_id]
            current_lat = next_leg.exit_lat
            current_lon = next_leg.exit_lon
            current_heading = next_leg.heading_deg

        self._legs = ordered
        return list(self._legs)

    def active_leg(self) -> SprayLeg | None:
        for leg in self._legs:
            if leg.leg_id not in self._completed_legs:
                return leg
        return None

    def select_spray_target(
        self,
        pose: AircraftPose,
        targets: list[ProjectedTarget],
    ) -> SprayOpportunity:
        leg = self.active_leg()
        lead_distance = pose.speed_mps * self.config.system_delay_s

        if leg is None:
            return SprayOpportunity(
                should_spray=False,
                reason="no_active_leg",
                leg_id=None,
                target=None,
                lead_distance_m=lead_distance,
            )

        cluster = self._cluster_by_id(leg.cluster_id)
        if cluster is None:
            return SprayOpportunity(
                should_spray=False,
                reason="cluster_missing",
                leg_id=leg.leg_id,
                target=None,
                lead_distance_m=lead_distance,
            )

        leg_targets = [
            target
            for target in targets
            if haversine_m(cluster.centroid_lat, cluster.centroid_lon, target.lat, target.lon)
            <= max(cluster.radius_m + self.config.cluster_radius_m * 0.6, self.config.cluster_radius_m)
        ]

        if not leg_targets:
            self._maybe_complete_leg(pose, leg)
            return SprayOpportunity(
                should_spray=False,
                reason="no_targets_for_leg",
                leg_id=leg.leg_id,
                target=None,
                lead_distance_m=lead_distance,
            )

        best_target: ProjectedTarget | None = None
        best_delta = float("inf")
        best_dist = None
        best_heading_err = None

        for target in leg_targets:
            dist_m = haversine_m(pose.lat, pose.lon, target.lat, target.lon)
            bearing = bearing_deg(pose.lat, pose.lon, target.lat, target.lon)
            heading_err = abs(angle_diff_deg(pose.heading_deg, bearing))
            if heading_err > self.config.heading_alignment_deg:
                continue

            delta = abs(dist_m - lead_distance)
            if delta < best_delta:
                best_delta = delta
                best_target = target
                best_dist = dist_m
                best_heading_err = heading_err

        if best_target is not None and best_delta <= self.config.trigger_window_m:
            return SprayOpportunity(
                should_spray=True,
                reason="within_lead_window",
                leg_id=leg.leg_id,
                target=best_target,
                lead_distance_m=lead_distance,
                distance_to_target_m=best_dist,
                heading_error_deg=best_heading_err,
            )

        self._maybe_complete_leg(pose, leg)

        if best_target is None:
            return SprayOpportunity(
                should_spray=False,
                reason="heading_misaligned_or_behind",
                leg_id=leg.leg_id,
                target=None,
                lead_distance_m=lead_distance,
            )

        return SprayOpportunity(
            should_spray=False,
            reason="outside_trigger_window",
            leg_id=leg.leg_id,
            target=best_target,
            lead_distance_m=lead_distance,
            distance_to_target_m=best_dist,
            heading_error_deg=best_heading_err,
        )

    def mark_leg_completed(self, leg_id: str) -> None:
        self._completed_legs.add(leg_id)

    def export_geojson(self) -> dict:
        features: list[dict] = []

        for patch in self._patches.values():
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "kind": "patch",
                        "patch_id": patch.patch_id,
                        "confidence": patch.confidence,
                        "hits": patch.hits,
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [patch.lon, patch.lat],
                    },
                }
            )

        for cluster in self._clusters:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "kind": "cluster",
                        "cluster_id": cluster.cluster_id,
                        "priority_score": round(cluster.priority_score, 3),
                        "radius_m": round(cluster.radius_m, 2),
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [cluster.centroid_lon, cluster.centroid_lat],
                    },
                }
            )

        for leg in self._legs:
            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "kind": "spray_leg",
                        "leg_id": leg.leg_id,
                        "cluster_id": leg.cluster_id,
                        "heading_deg": round(leg.heading_deg, 2),
                        "priority_score": round(leg.priority_score, 3),
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [
                            [leg.entry_lon, leg.entry_lat],
                            [leg.spray_start_lon, leg.spray_start_lat],
                            [leg.spray_end_lon, leg.spray_end_lat],
                            [leg.exit_lon, leg.exit_lat],
                        ],
                    },
                }
            )

        return {"type": "FeatureCollection", "features": features}

    def export_geojson_text(self) -> str:
        return json.dumps(self.export_geojson(), indent=2)

    def summary(self) -> dict[str, float | int | str | None]:
        active = self.active_leg()
        return {
            "patch_count": len(self._patches),
            "cluster_count": len(self._clusters),
            "leg_count": len(self._legs),
            "completed_leg_count": len(self._completed_legs),
            "active_leg": active.leg_id if active is not None else None,
        }

    def _find_existing_patch(self, target: ProjectedTarget) -> PatchPoint | None:
        for patch in self._patches.values():
            if haversine_m(patch.lat, patch.lon, target.lat, target.lon) <= self.config.dedupe_radius_m:
                return patch
        return None

    def _cluster_to_leg(self, cluster: PatchCluster, reference_heading_deg: float) -> SprayLeg:
        heading = reference_heading_deg
        length_m = clamp(
            2.0 * cluster.radius_m + 14.0,
            self.config.min_leg_length_m,
            self.config.max_leg_length_m,
        )

        spray_start_lat, spray_start_lon = destination_point_m(
            cluster.centroid_lat,
            cluster.centroid_lon,
            (heading + 180.0) % 360.0,
            length_m / 2.0,
        )
        spray_end_lat, spray_end_lon = destination_point_m(
            cluster.centroid_lat,
            cluster.centroid_lon,
            heading,
            length_m / 2.0,
        )
        entry_lat, entry_lon = destination_point_m(
            spray_start_lat,
            spray_start_lon,
            (heading + 180.0) % 360.0,
            self.config.pre_entry_distance_m,
        )
        exit_lat, exit_lon = destination_point_m(
            spray_end_lat,
            spray_end_lon,
            heading,
            self.config.post_exit_distance_m,
        )

        return SprayLeg(
            leg_id=f"leg_{cluster.cluster_id}",
            cluster_id=cluster.cluster_id,
            heading_deg=heading,
            length_m=length_m,
            entry_lat=entry_lat,
            entry_lon=entry_lon,
            spray_start_lat=spray_start_lat,
            spray_start_lon=spray_start_lon,
            spray_end_lat=spray_end_lat,
            spray_end_lon=spray_end_lon,
            exit_lat=exit_lat,
            exit_lon=exit_lon,
            priority_score=cluster.priority_score,
        )

    def _leg_cost(
        self,
        leg: SprayLeg,
        current_lat: float,
        current_lon: float,
        current_heading_deg: float,
    ) -> float:
        distance_m = haversine_m(current_lat, current_lon, leg.entry_lat, leg.entry_lon)
        heading_to_entry = bearing_deg(current_lat, current_lon, leg.entry_lat, leg.entry_lon)
        heading_delta = abs(angle_diff_deg(current_heading_deg, heading_to_entry))
        turn_cost = (heading_delta / 180.0) * self.config.min_turn_radius_m
        priority_bonus = min(leg.priority_score, 25.0) * 2.0
        return distance_m + turn_cost - priority_bonus

    def _cluster_by_id(self, cluster_id: str) -> PatchCluster | None:
        for cluster in self._clusters:
            if cluster.cluster_id == cluster_id:
                return cluster
        return None

    def _maybe_complete_leg(self, pose: AircraftPose, leg: SprayLeg) -> None:
        if haversine_m(pose.lat, pose.lon, leg.exit_lat, leg.exit_lon) <= 8.0:
            self.mark_leg_completed(leg.leg_id)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r * c


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)

    y = math.sin(dlambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda)
    angle = math.degrees(math.atan2(y, x))
    return (angle + 360.0) % 360.0


def destination_point_m(lat: float, lon: float, bearing: float, distance_m: float) -> tuple[float, float]:
    r = 6_371_000.0
    brng = math.radians(bearing)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)
    d_r = distance_m / r

    phi2 = math.asin(
        math.sin(phi1) * math.cos(d_r)
        + math.cos(phi1) * math.sin(d_r) * math.cos(brng)
    )
    lambda2 = lambda1 + math.atan2(
        math.sin(brng) * math.sin(d_r) * math.cos(phi1),
        math.cos(d_r) - math.sin(phi1) * math.sin(phi2),
    )

    return math.degrees(phi2), math.degrees(lambda2)


def angle_diff_deg(a: float, b: float) -> float:
    diff = (b - a + 180.0) % 360.0 - 180.0
    return diff


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    lat = sum(point[0] for point in points) / len(points)
    lon = sum(point[1] for point in points) / len(points)
    return lat, lon
