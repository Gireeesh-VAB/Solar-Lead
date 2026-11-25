"""§16 Testing — GET /app/checks/{id}/obstacles (OBS-04).

The distinction this endpoint exists to preserve: a roof with no
obstacles and a roof nothing has ever looked at are NOT the same answer.
Obstacle detection (OBS-01/02) runs through a vision-LLM call that needs
an OPENAI_API_KEY; without one the pipeline reports insufficient_data and
finds nothing. Drawing that as "no obstacles — clear roof" would be a lie
of omission, and it is the customer's usable area that would be
overstated as a result.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from solarfit.db import get_session
from solarfit.engine.area import compute_usable_area_m2
from solarfit.main import app
from solarfit.providers.solar_api import MaskVectorization, SolarApiResult
from solarfit.repositories import sites as sites_repo

# A square roughly 4 m across, in the shape OBS-04 stores.
POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [78.48670, 17.38500],
            [78.48674, 17.38500],
            [78.48674, 17.38504],
            [78.48670, 17.38504],
            [78.48670, 17.38500],
        ]
    ],
}


@pytest.fixture
def client(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def auth(make_auth_header):
    return make_auth_header(role="customer", owner_org=None)


@pytest.fixture
def check_id(client, auth):
    """A real owned check — the endpoint is ownership-gated.

    The request body always supplies lat/lng, so create_site_core() takes
    the resolve_for_location branch, not resolve_for_address — both are
    faked here (previously only resolve_for_address was, so this test
    silently depended on a real Solar API call over the network to reach
    the boundary=None state it actually wants)."""
    fake_result = SolarApiResult(status="no_coverage", boundary=None)
    with (
        patch("solarfit.routers.sites.solar_api.resolve_for_address", return_value=fake_result),
        patch("solarfit.routers.sites.solar_api.resolve_for_location", return_value=fake_result),
        patch(
            "solarfit.routers.sites.solar_api.extract_roof_polygon_from_mask",
            return_value=MaskVectorization(polygon=None, competing_regions=0),
        ),
    ):
        response = client.post(
            "/app/checks",
            json={"address": "Somewhere, Hyderabad", "lat": 17.385, "lng": 78.4867},
            headers=auth,
        )
    return response.json()["id"]


def test_obstacles_requires_auth(client, check_id):
    assert client.get(f"/app/checks/{check_id}/obstacles").status_code == 401


def test_another_tenants_check_is_404(client, auth, check_id, make_auth_header):
    other = make_auth_header(role="customer", owner_org=None)
    assert client.get(f"/app/checks/{check_id}/obstacles", headers=other).status_code == 404


def test_no_detector_configured_is_reported_not_silently_empty(client, auth, check_id):
    """The regression this guards: an empty list rendered as a clear roof
    when detection has never run."""
    settings = MagicMock(openai_api_key="", yolo_model_dir="", obstacle_service_url="")
    with (
        patch.object(sites_repo, "applied_obstacles", return_value=[]),
        patch("solarfit.routers.app_checks.get_settings", return_value=settings),
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["obstacles"] == []
    assert body["detected"] is False  # nothing looked
    assert body["reason"]


def test_detector_configured_but_clear_roof_is_detected_true(client, auth, check_id):
    """The other half of the same distinction: a detector that ran and
    found nothing genuinely means a clear roof."""
    settings = MagicMock(openai_api_key="sk-real-key", yolo_model_dir="", obstacle_service_url="")
    with (
        patch.object(sites_repo, "applied_obstacles", return_value=[]),
        patch("solarfit.routers.app_checks.get_settings", return_value=settings),
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["obstacles"] == []
    assert body["detected"] is True
    assert body["reason"] is None


def test_applied_obstacles_are_returned_as_drawable_rings(client, auth, check_id):
    with patch.object(
        sites_repo, "applied_obstacles", return_value=[("obs-1", POLYGON, "water_tank", 0.95, "obstacle_detection")]
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["detected"] is True
    assert len(body["obstacles"]) == 1
    obstacle = body["obstacles"][0]
    assert obstacle["id"] == "obs-1"
    assert obstacle["type"] == "water_tank"
    assert obstacle["confidence"] == 0.95
    # Ring order is preserved and the lng/lat swap actually happened.
    assert len(obstacle["polygon"]) == 5
    assert obstacle["polygon"][0] == {"lat": 17.385, "lng": 78.4867}


def test_a_degenerate_polygon_is_dropped_not_drawn(client, auth, check_id):
    """Two points cannot be an area. Rendering it would put a stray line
    across the customer's roof."""
    degenerate = {"type": "Polygon", "coordinates": [[[78.4867, 17.385], [78.4868, 17.385]]]}
    with patch.object(sites_repo, "applied_obstacles", return_value=[("bad", degenerate, None, None, "obstacle_detection")]):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["obstacles"] == []


def test_multiple_obstacles_all_come_back(client, auth, check_id):
    with patch.object(
        sites_repo,
        "applied_obstacles",
        return_value=[
            ("a", POLYGON, "hvac_unit", 0.8, "obstacle_detection"),
            ("b", POLYGON, "chimney", 0.7, "obstacle_detection"),
        ],
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert [o["id"] for o in body["obstacles"]] == ["a", "b"]


# ---------------------------------------------------------------------------
# POST/DELETE /app/checks/{id}/obstacles — the customer marking what's
# really on their own roof. Not a second obstacle system: it writes into
# the same applied_obstacle_ids/applied_obstacle_polygons provenance the
# OBS-04 auto-apply uses, so GET above returns detected + marked ones
# together with no special-casing.
# ---------------------------------------------------------------------------

# A ~22 m square roof, big enough that a 1.5 m marked obstacle is a
# plausible fraction of it (GEO-07's max_obstacle_area_fraction_of_boundary).
ROOF = [
    {"lat": 17.3849, "lng": 78.4866},
    {"lat": 17.3849, "lng": 78.4868},
    {"lat": 17.3851, "lng": 78.4868},
    {"lat": 17.3851, "lng": 78.4866},
]
ROOF_CENTRE = {"lat": 17.3850, "lng": 78.4867}


@pytest.fixture
def roofed_check_id(client, auth, check_id):
    response = client.put(
        f"/app/checks/{check_id}/boundary", json={"points": ROOF}, headers=auth
    )
    assert response.status_code == 200, response.text
    return check_id


def test_marking_an_obstacle_requires_auth(client, roofed_check_id):
    response = client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "water_tank", **ROOF_CENTRE},
    )
    assert response.status_code == 401


def test_marked_obstacle_is_returned_by_the_same_get(client, auth, roofed_check_id):
    created = client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "water_tank", **ROOF_CENTRE},
        headers=auth,
    )
    assert created.status_code == 201, created.text
    marked = created.json()
    assert marked["type"] == "water_tank"
    assert marked["source"] == "customer_marked"
    # A customer pointing at their own roof is a statement, not a
    # probabilistic detection — no confidence is invented for it.
    assert marked["confidence"] is None
    assert len(marked["polygon"]) == 5  # a closed square ring

    body = client.get(f"/app/checks/{roofed_check_id}/obstacles", headers=auth).json()
    assert body["detected"] is True
    assert [o["id"] for o in body["obstacles"]] == [marked["id"]]


def test_marking_an_obstacle_grows_the_exclusions(client, auth, roofed_check_id, db_session):
    before = sites_repo.get(db_session, roofed_check_id).exclusions
    client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "hvac_unit", **ROOF_CENTRE},
        headers=auth,
    )
    after = sites_repo.get(db_session, roofed_check_id).exclusions

    # This is what actually shrinks usable area: AREA-04 subtracts
    # site.exclusions from the boundary.
    assert after and after != before
    assert after["coordinates"]


def test_marking_an_obstacle_really_shrinks_the_usable_area(
    client, auth, roofed_check_id, db_session
):
    """The whole point of the feature, asserted end to end rather than
    reasoned about: the customer's tap has to reach AREA-04, which is the
    number that drives capacity, panel count and savings."""
    before = compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id))
    client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "water_tank", **ROOF_CENTRE},
        headers=auth,
    )
    after = compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id))

    # A 1.5 m square, buffered out by the pack's obstacle_setback_m — so
    # strictly more than the square's own 2.25 m², and nowhere near the
    # whole roof.
    assert after < before
    assert 2.25 < (before - after) < 0.25 * before


def test_a_tap_outside_the_roof_is_rejected(client, auth, roofed_check_id):
    response = client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "chimney", "lat": 17.4000, "lng": 78.5000},
        headers=auth,
    )
    assert response.status_code == 422


def test_removing_a_marked_obstacle_takes_it_back_out(client, auth, roofed_check_id):
    obstacle_id = client.post(
        f"/app/checks/{roofed_check_id}/obstacles",
        json={"type": "vent", **ROOF_CENTRE},
        headers=auth,
    ).json()["id"]

    deleted = client.delete(
        f"/app/checks/{roofed_check_id}/obstacles/{obstacle_id}", headers=auth
    )
    assert deleted.status_code == 204

    settings = MagicMock(openai_api_key="sk-real-key", yolo_model_dir="", obstacle_service_url="")
    with patch("solarfit.routers.app_checks.get_settings", return_value=settings):
        body = client.get(f"/app/checks/{roofed_check_id}/obstacles", headers=auth).json()
    assert body["obstacles"] == []


def test_a_customer_cannot_remove_an_ai_detected_obstacle(
    client, auth, roofed_check_id, db_session
):
    """OBS-06 reversal of a pipeline detection is an audited admin path
    (engine/obstacles.py::reject_applied_obstacle), not a customer tap."""
    detected_polygon = {
        "type": "Polygon",
        "coordinates": [
            [
                [78.48668, 17.38498],
                [78.48670, 17.38498],
                [78.48670, 17.38500],
                [78.48668, 17.38500],
                [78.48668, 17.38498],
            ]
        ],
    }
    sites_repo.new_geometry_version(
        db_session,
        roofed_check_id,
        exclusions={"type": "MultiPolygon", "coordinates": [detected_polygon["coordinates"]]},
        actor="system:obstacle_detection",
        source="obstacle_detection",
        applied_obstacle_ids=["ai-1"],
        applied_obstacle_polygons={
            "ai-1": {"polygon": detected_polygon, "type": "antenna", "confidence": 0.9}
        },
    )
    db_session.flush()

    response = client.delete(f"/app/checks/{roofed_check_id}/obstacles/ai-1", headers=auth)
    assert response.status_code == 403


def test_removing_an_unknown_obstacle_is_404(client, auth, roofed_check_id):
    response = client.delete(
        f"/app/checks/{roofed_check_id}/obstacles/not-a-real-id", headers=auth
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /app/checks/{id}/obstacles/detect - scan the roof the customer just
# selected. The scan runs in the Celery worker (where the detector models
# live); these tests fake that task and seed what it would have applied.
# ---------------------------------------------------------------------------

DETECTED_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [78.48668, 17.38498],
            [78.48670, 17.38498],
            [78.48670, 17.38500],
            [78.48668, 17.38500],
            [78.48668, 17.38498],
        ]
    ],
}


def _seed_detected(db_session, check_id, obstacle_id="det-1", source="cv_detector", confidence=0.52):
    sites_repo.new_geometry_version(
        db_session,
        check_id,
        exclusions={"type": "MultiPolygon", "coordinates": [DETECTED_POLYGON["coordinates"]]},
        actor="system:obstacle_detection",
        source="obstacle_detection",
        applied_obstacle_ids=[obstacle_id],
        applied_obstacle_polygons={
            obstacle_id: {
                "polygon": DETECTED_POLYGON,
                "type": "other",
                "confidence": confidence,
                "source": source,
            }
        },
    )
    db_session.flush()


def _fake_scan(result):
    task = MagicMock()
    task.delay.return_value.get.return_value = result
    return patch("solarfit.workers.celery_app.detect_site_obstacles_task", task), task


def test_scanning_requires_auth(client, check_id):
    assert client.post(f"/app/checks/{check_id}/obstacles/detect").status_code == 401


def test_scanning_another_tenants_check_is_404(client, check_id, make_auth_header):
    other = make_auth_header(role="customer", owner_org=None)
    assert client.post(f"/app/checks/{check_id}/obstacles/detect", headers=other).status_code == 404


def test_scanning_a_roof_with_no_outline_is_a_409(client, auth, check_id):
    assert client.post(f"/app/checks/{check_id}/obstacles/detect", headers=auth).status_code == 409


def test_a_scan_returns_the_detected_obstacles_ready_to_draw(client, auth, roofed_check_id, db_session):
    _seed_detected(db_session, roofed_check_id)
    patcher, task = _fake_scan({"status": "ok", "obstacles": []})

    with patcher:
        response = client.post(f"/app/checks/{roofed_check_id}/obstacles/detect", headers=auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["detected"] is True
    assert body["reason"] is None
    assert [o["id"] for o in body["obstacles"]] == ["det-1"]
    assert body["obstacles"][0]["source"] == "cv_detector"
    assert body["obstacles"][0]["confidence"] == pytest.approx(0.52)
    assert len(body["obstacles"][0]["polygon"]) >= 3
    task.delay.assert_called_once_with(roofed_check_id)


def test_a_clear_roof_scans_ok_with_no_obstacles(client, auth, roofed_check_id):
    patcher, _task = _fake_scan({"status": "ok", "obstacles": []})

    with patcher:
        body = client.post(f"/app/checks/{roofed_check_id}/obstacles/detect", headers=auth).json()

    assert body["detected"] is True
    assert body["obstacles"] == []


def test_a_worker_failure_is_reported_not_a_500(client, auth, roofed_check_id, db_session):
    """The customer must never be blocked because the worker is down -
    they get "detection unavailable" plus whatever is already applied."""
    _seed_detected(db_session, roofed_check_id, source="customer_marked", obstacle_id="mine")
    task = MagicMock()
    task.delay.return_value.get.side_effect = TimeoutError("worker down")

    with patch("solarfit.workers.celery_app.detect_site_obstacles_task", task):
        response = client.post(f"/app/checks/{roofed_check_id}/obstacles/detect", headers=auth)

    assert response.status_code == 200
    body = response.json()
    assert body["detected"] is False
    assert body["reason"] is not None
    assert [o["id"] for o in body["obstacles"]] == ["mine"]


def test_detector_not_configured_says_so(client, auth, roofed_check_id):
    patcher, _task = _fake_scan({"status": "not_configured", "obstacles": []})

    with patcher:
        body = client.post(f"/app/checks/{roofed_check_id}/obstacles/detect", headers=auth).json()

    assert body["detected"] is False
    assert "not configured" in body["reason"]


def test_a_customer_can_remove_a_model_detection_that_is_wrong(client, auth, roofed_check_id, db_session):
    _seed_detected(db_session, roofed_check_id)

    response = client.delete(f"/app/checks/{roofed_check_id}/obstacles/det-1", headers=auth)

    assert response.status_code == 204
    body = client.get(f"/app/checks/{roofed_check_id}/obstacles", headers=auth).json()
    assert body["obstacles"] == []


def test_a_removed_detection_is_still_in_the_sites_history(roofed_check_id, db_session):
    """So a re-scan can tell it was removed on purpose and not bring it back
    (engine.obstacles.apply_or_flag compares against this)."""
    _seed_detected(db_session, roofed_check_id)
    sites_repo.new_geometry_version(
        db_session,
        roofed_check_id,
        exclusions={"type": "MultiPolygon", "coordinates": []},
        actor="x",
        source="customer_unmarked_obstacle",
        applied_obstacle_ids=["det-1"],
        applied_obstacle_polygons={"det-1": {"removed": True}},
    )
    db_session.flush()

    assert sites_repo.applied_obstacles(db_session, roofed_check_id) == []
    assert sites_repo.ever_applied_obstacle_polygons(db_session, roofed_check_id) == [DETECTED_POLYGON]


def test_a_yolo_model_folder_alone_counts_as_detection_being_configured(client, auth, check_id):
    """Detection no longer depends on an OpenAI key: the YOLO ensemble is
    enough, and a clear roof it scanned is genuinely clear."""
    settings = MagicMock(openai_api_key="", yolo_model_dir="models/obstacles", obstacle_service_url="")
    with (
        patch.object(sites_repo, "applied_obstacles", return_value=[]),
        patch("solarfit.routers.app_checks.get_settings", return_value=settings),
    ):
        body = client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()

    assert body["detected"] is True
    assert body["reason"] is None


# ---------------------------------------------------------------------------
# Review flow: a model detection is `pending` - it counts toward nothing
# (not panel placement, not shading, not usable area) until the customer
# Confirms it. Edit = confirm with a corrected type/outline. Ignore keeps it
# out for good.
# ---------------------------------------------------------------------------

from solarfit.domain.assessment import Obstacle
from solarfit.repositories import obstacle_candidates as candidates_repo


def _seed_candidate(db_session, check_id, *, confidence=0.84, polygon=None):
    obstacle = Obstacle(
        type="other",
        bounding_polygon=polygon or DETECTED_POLYGON,
        confidence=confidence,
        source="cv_detector",
    )
    candidates_repo.add_candidates(db_session, check_id, [obstacle])
    db_session.flush()
    return obstacle.id


def _get(client, auth, check_id):
    return client.get(f"/app/checks/{check_id}/obstacles", headers=auth).json()


def test_a_pending_detection_is_listed_for_review_and_applied_to_nothing(
    client, auth, roofed_check_id, db_session
):
    before_area = compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id))
    before_exclusions = sites_repo.get(db_session, roofed_check_id).exclusions
    oid = _seed_candidate(db_session, roofed_check_id, confidence=0.84)

    body = _get(client, auth, roofed_check_id)

    assert body["obstacles"] == []  # nothing applied
    assert [o["id"] for o in body["pending"]] == [oid]
    pending = body["pending"][0]
    assert pending["number"] == 1
    assert pending["confidence"] == pytest.approx(0.84)
    assert pending["source"] == "cv_detector"
    assert len(pending["polygon"]) >= 3
    # ...and it genuinely touches nothing: same exclusions, same usable area.
    site = sites_repo.get(db_session, roofed_check_id)
    assert site.exclusions == before_exclusions
    assert compute_usable_area_m2(site) == before_area


def test_detections_are_numbered_in_a_stable_order(client, auth, roofed_check_id, db_session):
    other_polygon = {
        "type": "Polygon",
        "coordinates": [
            [[78.48676, 17.38506], [78.48678, 17.38506], [78.48678, 17.38508], [78.48676, 17.38508], [78.48676, 17.38506]]
        ],
    }
    first = _seed_candidate(db_session, roofed_check_id)
    second = _seed_candidate(db_session, roofed_check_id, confidence=0.72, polygon=other_polygon)

    pending = _get(client, auth, roofed_check_id)["pending"]

    assert [(o["id"], o["number"]) for o in pending] == [(first, 1), (second, 2)]


def test_confirming_applies_it_and_really_shrinks_the_usable_area(
    client, auth, roofed_check_id, db_session
):
    before = compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id))
    oid = _seed_candidate(db_session, roofed_check_id)

    response = client.post(f"/app/checks/{roofed_check_id}/obstacles/{oid}/confirm", headers=auth)

    assert response.status_code == 200, response.text
    assert response.json()["id"] == oid
    assert response.json()["number"] == 1
    assert compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id)) < before
    body = _get(client, auth, roofed_check_id)
    assert body["pending"] == []
    assert [(o["id"], o["number"], o["source"]) for o in body["obstacles"]] == [(oid, 1, "cv_detector")]


def test_editing_then_confirming_applies_the_customers_type_and_outline(
    client, auth, roofed_check_id, db_session
):
    oid = _seed_candidate(db_session, roofed_check_id)
    bigger = [
        {"lat": 17.38496, "lng": 78.48666},
        {"lat": 17.38496, "lng": 78.48672},
        {"lat": 17.38502, "lng": 78.48672},
        {"lat": 17.38502, "lng": 78.48666},
    ]

    response = client.post(
        f"/app/checks/{roofed_check_id}/obstacles/{oid}/confirm",
        json={"type": "water_tank", "polygon": bigger},
        headers=auth,
    )

    assert response.status_code == 200, response.text
    applied = _get(client, auth, roofed_check_id)["obstacles"][0]
    assert applied["type"] == "water_tank"
    lats = [p["lat"] for p in applied["polygon"]]
    assert max(lats) - min(lats) == pytest.approx(0.00006, abs=1e-6)  # the edited, larger shape


def test_an_edited_outline_off_the_roof_is_refused(client, auth, roofed_check_id, db_session):
    oid = _seed_candidate(db_session, roofed_check_id)
    elsewhere = [
        {"lat": 17.4000, "lng": 78.5000},
        {"lat": 17.4000, "lng": 78.5002},
        {"lat": 17.4002, "lng": 78.5002},
    ]

    response = client.post(
        f"/app/checks/{roofed_check_id}/obstacles/{oid}/confirm",
        json={"polygon": elsewhere},
        headers=auth,
    )

    assert response.status_code == 422
    assert [o["id"] for o in _get(client, auth, roofed_check_id)["pending"]] == [oid]  # still pending


def test_ignoring_dismisses_it_and_changes_nothing_else(client, auth, roofed_check_id, db_session):
    before = compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id))
    oid = _seed_candidate(db_session, roofed_check_id)

    response = client.post(f"/app/checks/{roofed_check_id}/obstacles/{oid}/ignore", headers=auth)

    assert response.status_code == 204
    body = _get(client, auth, roofed_check_id)
    assert body["pending"] == [] and body["obstacles"] == []
    assert compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id)) == before
    # kept (as ignored) so a re-scan can recognise and skip it
    assert [r.status for r in candidates_repo.list_for_site(db_session, roofed_check_id)] == ["ignored"]


def test_a_detection_can_only_be_reviewed_once(client, auth, roofed_check_id, db_session):
    oid = _seed_candidate(db_session, roofed_check_id)
    client.post(f"/app/checks/{roofed_check_id}/obstacles/{oid}/ignore", headers=auth)

    assert client.post(f"/app/checks/{roofed_check_id}/obstacles/{oid}/confirm", headers=auth).status_code == 409
    assert client.post(f"/app/checks/{roofed_check_id}/obstacles/{oid}/ignore", headers=auth).status_code == 409


def test_reviewing_an_unknown_detection_is_404(client, auth, roofed_check_id):
    for action in ("confirm", "ignore"):
        response = client.post(f"/app/checks/{roofed_check_id}/obstacles/not-real/{action}", headers=auth)
        assert response.status_code == 404


def test_reviewing_requires_auth_and_ownership(client, roofed_check_id, db_session, make_auth_header):
    oid = _seed_candidate(db_session, roofed_check_id)
    other = make_auth_header(role="customer", owner_org=None)

    for action in ("confirm", "ignore"):
        url = f"/app/checks/{roofed_check_id}/obstacles/{oid}/{action}"
        assert client.post(url).status_code == 401
        assert client.post(url, headers=other).status_code == 404


def test_taking_back_a_confirmed_detection_keeps_it_from_resurfacing(
    client, auth, roofed_check_id, db_session
):
    oid = _seed_candidate(db_session, roofed_check_id)
    client.post(f"/app/checks/{roofed_check_id}/obstacles/{oid}/confirm", headers=auth)

    assert client.delete(f"/app/checks/{roofed_check_id}/obstacles/{oid}", headers=auth).status_code == 204

    body = _get(client, auth, roofed_check_id)
    assert body["obstacles"] == [] and body["pending"] == []
    assert [r.status for r in candidates_repo.list_for_site(db_session, roofed_check_id)] == ["ignored"]


def test_pending_detections_alone_make_detection_count_as_having_run(client, auth, roofed_check_id, db_session):
    """A roof whose only finding is a pending detection must not read as
    "no detector configured / nothing looked"."""
    _seed_candidate(db_session, roofed_check_id)
    settings = MagicMock(openai_api_key="", yolo_model_dir="", obstacle_service_url="")

    with patch("solarfit.routers.app_checks.get_settings", return_value=settings):
        body = _get(client, auth, roofed_check_id)

    assert body["detected"] is True
    assert len(body["pending"]) == 1


# ---------------------------------------------------------------------------
# Drawing an obstacle the models MISSED: POST /app/checks/{id}/obstacles/draw
# ---------------------------------------------------------------------------

# A ~3.3 m square well inside ROOF, as the customer would drag it out on the map.
DRAWN = [
    {"lat": 17.38497, "lng": 78.48664},
    {"lat": 17.38497, "lng": 78.48667},
    {"lat": 17.38500, "lng": 78.48667},
    {"lat": 17.38500, "lng": 78.48664},
]


def _draw(client, auth, check_id, polygon=DRAWN, type_="water_tank"):
    return client.post(
        f"/app/checks/{check_id}/obstacles/draw", json={"type": type_, "polygon": polygon}, headers=auth
    )


def test_drawing_an_obstacle_requires_auth(client, roofed_check_id):
    response = client.post(
        f"/app/checks/{roofed_check_id}/obstacles/draw", json={"type": "vent", "polygon": DRAWN}
    )
    assert response.status_code == 401


def test_a_drawn_obstacle_keeps_the_customers_own_outline_and_is_numbered(client, auth, roofed_check_id):
    response = _draw(client, auth, roofed_check_id)

    assert response.status_code == 201, response.text
    drawn = response.json()
    assert drawn["type"] == "water_tank" and drawn["source"] == "customer_drawn"
    assert drawn["confidence"] is None  # a customer's own outline is a statement, not a probability
    assert drawn["number"] == 1
    assert len(drawn["polygon"]) == 5  # the four corners, closed
    lats = [p["lat"] for p in drawn["polygon"]]
    assert max(lats) - min(lats) == pytest.approx(0.00003, abs=1e-7)  # NOT a fixed 1.5 m square

    listed = _get(client, auth, roofed_check_id)["obstacles"]
    assert [(o["id"], o["number"], o["source"]) for o in listed] == [(drawn["id"], 1, "customer_drawn")]


def test_a_drawn_obstacle_really_shrinks_the_usable_area(client, auth, roofed_check_id, db_session):
    before = compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id))
    _draw(client, auth, roofed_check_id)
    after = compute_usable_area_m2(sites_repo.get(db_session, roofed_check_id))

    # ~3.3 m x 3.3 m = ~11 m2, plus the pack's setback buffer around it.
    assert after < before and (before - after) > 9


def test_a_drawn_obstacle_is_stored_as_a_confirmed_candidate_for_training(
    client, auth, roofed_check_id, db_session
):
    obstacle_id = _draw(client, auth, roofed_check_id).json()["id"]

    confirmed = candidates_repo.list_for_site(db_session, roofed_check_id, status=candidates_repo.STATUS_CONFIRMED)
    assert [(str(c.id), c.source, c.type) for c in confirmed] == [(obstacle_id, "customer_drawn", "water_tank")]


def test_numbering_continues_after_detections(client, auth, roofed_check_id, db_session):
    _seed_candidate(db_session, roofed_check_id)  # a detection is #1 ...
    drawn = _draw(client, auth, roofed_check_id).json()
    assert drawn["number"] == 2  # ... so the drawn one is #2


def test_an_outline_off_the_roof_is_refused(client, auth, roofed_check_id):
    elsewhere = [
        {"lat": 17.4000, "lng": 78.5000},
        {"lat": 17.4000, "lng": 78.5002},
        {"lat": 17.4002, "lng": 78.5002},
    ]
    assert _draw(client, auth, roofed_check_id, elsewhere).status_code == 422


def test_an_outline_sticking_out_past_the_roof_edge_is_clipped_to_the_roof(client, auth, roofed_check_id):
    straddling = [  # half of it past the roof's east edge (lng 78.4868)
        {"lat": 17.38497, "lng": 78.48677},
        {"lat": 17.38497, "lng": 78.48683},
        {"lat": 17.38500, "lng": 78.48683},
        {"lat": 17.38500, "lng": 78.48677},
    ]
    response = _draw(client, auth, roofed_check_id, straddling)

    assert response.status_code == 201, response.text
    assert max(p["lng"] for p in response.json()["polygon"]) <= 78.4868 + 1e-9


def test_crossing_or_tiny_outlines_are_refused(client, auth, roofed_check_id):
    bow_tie = [  # corners in the wrong order: the edges cross
        {"lat": 17.38497, "lng": 78.48664},
        {"lat": 17.38500, "lng": 78.48667},
        {"lat": 17.38497, "lng": 78.48667},
        {"lat": 17.38500, "lng": 78.48664},
    ]
    speck = [{"lat": 17.38497, "lng": 78.48664}, {"lat": 17.384971, "lng": 78.48664}, {"lat": 17.384971, "lng": 78.486641}]
    assert _draw(client, auth, roofed_check_id, bow_tie).status_code == 422
    assert _draw(client, auth, roofed_check_id, speck).status_code == 422


def test_fewer_than_three_corners_is_refused(client, auth, roofed_check_id):
    assert _draw(client, auth, roofed_check_id, DRAWN[:2]).status_code == 422


def test_drawing_on_a_roof_with_no_outline_is_a_409(client, auth, check_id):
    assert _draw(client, auth, check_id).status_code == 409


def test_a_refused_outline_leaves_nothing_behind(client, auth, roofed_check_id, db_session):
    before = sites_repo.get(db_session, roofed_check_id).exclusions
    _draw(client, auth, roofed_check_id, [{"lat": 17.4, "lng": 78.5}, {"lat": 17.4, "lng": 78.5002}, {"lat": 17.4002, "lng": 78.5002}])

    assert sites_repo.get(db_session, roofed_check_id).exclusions == before
    assert candidates_repo.list_for_site(db_session, roofed_check_id) == []


def test_a_customer_can_remove_an_obstacle_they_drew(client, auth, roofed_check_id, db_session):
    obstacle_id = _draw(client, auth, roofed_check_id).json()["id"]

    assert client.delete(f"/app/checks/{roofed_check_id}/obstacles/{obstacle_id}", headers=auth).status_code == 204

    settings = MagicMock(openai_api_key="sk-real-key", yolo_model_dir="", obstacle_service_url="")
    with patch("solarfit.routers.app_checks.get_settings", return_value=settings):
        assert _get(client, auth, roofed_check_id)["obstacles"] == []
    # Taken back = as good as ignored: the candidate is kept (a re-scan won't resurface it) and training reads it as "not an obstacle".
    candidate = candidates_repo.list_for_site(db_session, roofed_check_id)[0]
    assert candidate.status == candidates_repo.STATUS_IGNORED


# ---------------------------------------------------------------------------
# The "What type of obstacle is this?" picker: every type it offers must be accepted.
# ---------------------------------------------------------------------------

PICKER_TYPES = [
    "water_tank", "staircase", "hvac_unit", "lift_room", "chimney", "solar_water_heater",
    "parapet", "electrical_equipment", "existing_solar_panel", "tree", "walkway", "other",
]


@pytest.mark.parametrize("obstacle_type", PICKER_TYPES)
def test_confirming_a_detection_accepts_every_type_in_the_picker(
    client, auth, roofed_check_id, db_session, obstacle_type
):
    oid = _seed_candidate(db_session, roofed_check_id)

    response = client.post(
        f"/app/checks/{roofed_check_id}/obstacles/{oid}/confirm", json={"type": obstacle_type}, headers=auth
    )

    assert response.status_code == 200, response.text
    assert response.json()["type"] == obstacle_type
    assert [o["type"] for o in _get(client, auth, roofed_check_id)["obstacles"]] == [obstacle_type]


@pytest.mark.parametrize("obstacle_type", PICKER_TYPES)
def test_drawing_accepts_every_type_in_the_picker(client, auth, roofed_check_id, obstacle_type):
    response = _draw(client, auth, roofed_check_id, type_=obstacle_type)

    assert response.status_code == 201, response.text
    assert response.json()["type"] == obstacle_type


def test_an_unknown_obstacle_type_is_refused(client, auth, roofed_check_id, db_session):
    oid = _seed_candidate(db_session, roofed_check_id)
    confirm = client.post(
        f"/app/checks/{roofed_check_id}/obstacles/{oid}/confirm", json={"type": "spaceship"}, headers=auth
    )
    assert confirm.status_code == 422
    assert _draw(client, auth, roofed_check_id, type_="spaceship").status_code == 422
    assert [o["id"] for o in _get(client, auth, roofed_check_id)["pending"]] == [oid]  # still waiting for a valid answer
