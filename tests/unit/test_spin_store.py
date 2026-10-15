import json
import threading

from src.vision.spin_store import SpinLocationStore, spin_key


def test_saved_location_is_returned_and_survives_a_new_instance(tmp_path):
    path = tmp_path / "cache" / "spin.json"
    SpinLocationStore(path).save("com|Sweet Bonanza|1.78", {"x": 0.8, "y": 0.65})

    assert SpinLocationStore(path).get("com|Sweet Bonanza|1.78") == {"x": 0.8, "y": 0.65}


def test_unknown_key_returns_none(tmp_path):
    assert SpinLocationStore(tmp_path / "spin.json").get("nope") is None


def test_invalidate_removes_only_that_entry(tmp_path):
    store = SpinLocationStore(tmp_path / "spin.json")
    store.save("a", {"x": 0.1, "y": 0.2})
    store.save("b", {"x": 0.3, "y": 0.4})

    store.invalidate("a")

    assert store.get("a") is None
    assert store.get("b") == {"x": 0.3, "y": 0.4}


def test_corrupt_file_is_treated_as_empty_and_recovers(tmp_path):
    path = tmp_path / "spin.json"
    path.write_text("{not json", encoding="utf-8")
    store = SpinLocationStore(path)

    assert store.get("a") is None
    store.save("a", {"x": 0.5, "y": 0.5})
    assert store.get("a") == {"x": 0.5, "y": 0.5}


def test_out_of_range_coordinates_are_never_stored(tmp_path):
    store = SpinLocationStore(tmp_path / "spin.json")
    store.save("bad", {"x": 1.4, "y": 0.5})
    store.save("neg", {"x": -0.1, "y": 0.5})

    assert store.get("bad") is None and store.get("neg") is None


def test_a_tampered_out_of_range_value_on_disk_is_ignored(tmp_path):
    path = tmp_path / "spin.json"
    path.write_text(json.dumps({"k": {"x": 9, "y": 0.5}}), encoding="utf-8")
    assert SpinLocationStore(path).get("k") is None


def test_concurrent_saves_from_parallel_agents_do_not_lose_entries(tmp_path):
    path = tmp_path / "spin.json"
    threads = [
        threading.Thread(target=lambda i=i: SpinLocationStore(path).save(f"k{i}", {"x": 0.1, "y": 0.2}))
        for i in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    store = SpinLocationStore(path)
    assert all(store.get(f"k{i}") is not None for i in range(8))


def test_key_depends_on_market_game_and_aspect_ratio():
    base = spin_key("com", "Sweet Bonanza", 770, 433)
    assert base == spin_key("com", "Sweet Bonanza", 771, 434)       # tiny layout jitter: same key
    assert base != spin_key("pe", "Sweet Bonanza", 770, 433)
    assert base != spin_key("com", "Gates of Olympus", 770, 433)
    assert base != spin_key("com", "Sweet Bonanza", 600, 600)       # different aspect ratio
