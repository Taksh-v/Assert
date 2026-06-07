from backend.core.retry import retry_sync


def test_retry_sync_succeeds_after_retries():
    calls = {"n": 0}

    @retry_sync(max_attempts=3, initial_delay=0.01)
    def flaky():
        calls["n"] += 1
        if calls["n"] < 2:
            raise ValueError("transient")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 2


def test_retry_sync_fails_after_max():
    @retry_sync(max_attempts=2, initial_delay=0.01)
    def always_fail():
        raise RuntimeError("bad")

    try:
        always_fail()
    except RuntimeError:
        pass
    else:
        raise AssertionError("Expected RuntimeError")
