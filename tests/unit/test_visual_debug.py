from src.browser.visual_debug import CURSOR_SCRIPT, read_visual_settings


def test_defaults_when_headed_show_the_cursor_without_slowing_down():
    v = read_visual_settings({}, headless=False)
    assert (v.slow_mo_ms, v.show_cursor, v.keep_open_s) == (0, True, 0)


def test_headless_never_shows_the_cursor_or_waits():
    v = read_visual_settings({"SHOW_CURSOR": "true", "KEEP_OPEN_S": "30"}, headless=True)
    assert v.show_cursor is False
    assert v.keep_open_s == 0


def test_env_overrides_are_applied_when_headed():
    v = read_visual_settings({"SLOW_MO_MS": "400", "SHOW_CURSOR": "false", "KEEP_OPEN_S": "20"}, headless=False)
    assert (v.slow_mo_ms, v.show_cursor, v.keep_open_s) == (400, False, 20)


def test_invalid_numbers_fall_back_to_zero():
    v = read_visual_settings({"SLOW_MO_MS": "fast", "KEEP_OPEN_S": "-5"}, headless=False)
    assert (v.slow_mo_ms, v.keep_open_s) == (0, 0)


def test_cursor_script_tracks_the_mouse_and_marks_clicks():
    assert "mousemove" in CURSOR_SCRIPT
    assert "mousedown" in CURSOR_SCRIPT
    assert "pointer-events" in CURSOR_SCRIPT  # must never intercept the bot's own clicks
