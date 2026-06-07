from backend.connectors.wrappers.skill_wrapper import skill_wrapper, _IDEMPOTENCY


def test_skill_wrapper_idempotency():
    @skill_wrapper("test_skill", idempotent=True)
    def echo_skill(params, idempotency_key=None):
        return {"echo": params}

    # Clean store
    _IDEMPOTENCY.seen.clear()

    r1 = echo_skill(params={"x": 1}, idempotency_key="k1")
    r2 = echo_skill(params={"x": 1}, idempotency_key="k1")
    assert r1 == r2
    assert _IDEMPOTENCY.get("k1") == r1
