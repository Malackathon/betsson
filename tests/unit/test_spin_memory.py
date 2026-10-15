"""GameFlow remembers verified Spin locations and forgets stale ones."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.flows.game_flow import GameFlow
from src.network.models import SpinAttempt, SpinAttemptStatus
from src.vision.spin_store import SpinLocationStore, spin_key

COORDS = {"x": 0.8, "y": 0.65}


@pytest.fixture
def flow(tmp_path):
    f = GameFlow(playwright=None, market="com", agent_id="agent_com_s1", spin_store=SpinLocationStore(tmp_path / "s.json"))
    f._canvas = SimpleNamespace(iframe_rect=SimpleNamespace(width=770.4, height=433.3))
    f._game_name = "Sweet Bonanza"
    return f


def _key() -> str:
    return spin_key("com", "Sweet Bonanza", 770.4, 433.3)


def test_nothing_is_stored_until_a_spin_is_verified(flow):
    assert flow._stored_spin_coords() is None


def test_location_that_produced_a_spin_request_is_remembered(flow):
    flow._remember_spin(COORDS, SpinAttempt(SpinAttemptStatus.SETTLED), allow_invalidate=True)
    assert flow._stored_spin_coords() == COORDS


@pytest.mark.parametrize("status", [SpinAttemptStatus.PENDING, SpinAttemptStatus.REJECTED])
def test_any_spin_traffic_counts_as_verification(flow, status):
    flow._remember_spin(COORDS, SpinAttempt(status), allow_invalidate=True)
    assert flow._stored_spin_coords() == COORDS


def test_a_click_with_no_traffic_is_never_stored(flow):
    flow._remember_spin(COORDS, SpinAttempt(SpinAttemptStatus.NO_TRAFFIC), allow_invalidate=True)
    assert flow._stored_spin_coords() is None


def test_a_stored_location_that_stops_working_is_forgotten(flow):
    flow._remember_spin(COORDS, SpinAttempt(SpinAttemptStatus.SETTLED), allow_invalidate=True)

    flow._remember_spin(COORDS, SpinAttempt(SpinAttemptStatus.NO_TRAFFIC), allow_invalidate=True)

    assert flow._stored_spin_coords() is None


def test_silence_in_scenario_2_is_ambiguous_so_it_does_not_erase_a_good_location(flow):
    flow._remember_spin(COORDS, SpinAttempt(SpinAttemptStatus.SETTLED), allow_invalidate=True)

    flow._remember_spin(COORDS, SpinAttempt(SpinAttemptStatus.NO_TRAFFIC), allow_invalidate=False)

    assert flow._stored_spin_coords() == COORDS


def test_different_game_layouts_do_not_share_a_location(flow):
    flow._remember_spin(COORDS, SpinAttempt(SpinAttemptStatus.SETTLED), allow_invalidate=True)
    flow._game_name = "Gates of Olympus"
    assert flow._stored_spin_coords() is None
    assert _key().startswith("com|Sweet Bonanza")
