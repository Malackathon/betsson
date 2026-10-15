from src.browser.session_watch import SessionWatch


class _Req:
    def __init__(self, method: str = "GET") -> None:
        self.method = method


class _Resp:
    def __init__(self, url: str, status: int, method: str = "GET") -> None:
        self.url, self.status, self.request = url, status, _Req(method)


class _Frame:
    def __init__(self, url: str, main: bool = True) -> None:
        self.url, self._main = url, main


class _FakePage:
    def __init__(self) -> None:
        self.handlers: dict[str, object] = {}
        self.main_frame = _Frame("https://www.betsson.es/casino")

    def on(self, event, handler) -> None:
        self.handlers[event] = handler

    def remove_listener(self, event, handler) -> None:
        self.handlers.pop(event, None)


def _watch() -> tuple[SessionWatch, _FakePage]:
    page = _FakePage()
    watch = SessionWatch()
    watch.attach(page)
    return watch, page


def test_query_strings_and_tokens_are_never_recorded():
    watch, page = _watch()
    page.handlers["response"](_Resp("https://www.betsson.es/api/auth?token=SECRET123&u=1", 401, "POST"))

    summary = watch.summary()
    assert "SECRET123" not in summary
    assert "POST 401 www.betsson.es/api/auth" in summary


def test_only_errors_are_recorded_for_responses():
    watch, page = _watch()
    page.handlers["response"](_Resp("https://www.betsson.es/api/ok", 200))
    page.handlers["response"](_Resp("https://www.betsson.es/api/bad", 403, "POST"))

    assert "api/ok" not in watch.summary()
    assert "403" in watch.summary()


def test_main_frame_navigations_are_recorded_but_subframes_are_ignored():
    watch, page = _watch()
    page.main_frame.url = "https://www.betsson.es/inicio?returnUrl=%2F"
    page.handlers["framenavigated"](page.main_frame)
    page.handlers["framenavigated"](_Frame("https://games.example/game?token=ABC", main=False))

    summary = watch.summary()
    assert "NAVIGATED www.betsson.es/inicio" in summary
    assert "games.example" not in summary
    assert "returnUrl" not in summary


def test_popups_are_recorded():
    watch, page = _watch()

    class _Popup:
        url = "https://games.example/launch?sid=ZZZ"

    page.handlers["popup"](_Popup())
    assert "POPUP games.example/launch" in watch.summary()
    assert "ZZZ" not in watch.summary()


def test_checkpoint_records_whether_the_session_is_still_logged_in():
    watch, _ = _watch()
    watch.checkpoint("after opening the game", logged_out=True)
    watch.checkpoint("casino loaded", logged_out=False)

    summary = watch.summary()
    assert "CHECKPOINT after opening the game: SESSION LOST (login button visible)" in summary
    assert "CHECKPOINT casino loaded: logged in" in summary


def test_buffer_keeps_only_the_most_recent_events():
    watch, page = _watch()
    for i in range(200):
        page.handlers["response"](_Resp(f"https://www.betsson.es/api/e{i}", 500))

    summary = watch.summary()
    assert "api/e199" in summary
    assert "api/e0 " not in summary and "api/e0\n" not in summary


def test_detach_removes_listeners():
    watch, page = _watch()
    watch.detach()
    assert page.handlers == {}
