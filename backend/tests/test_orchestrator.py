from backend.reasoning.orchestrator import Planner, Dispatcher, Orchestrator


def test_orchestrator_dispatches_and_collects_results():
    class AgentA:
        def __call__(self, inp):
            return f"A:{inp}"

    class AgentB:
        def __call__(self, inp):
            return f"B:{inp}"

    planner = Planner()
    agents = {"agent_a": AgentA(), "agent_b": AgentB()}
    dispatcher = Dispatcher(agents)
    orch = Orchestrator(planner, dispatcher)

    res = orch.orchestrate("hello")

    assert "agent_a" in res and "agent_b" in res
    assert res["agent_a"] == ["A:hello"]
    assert res["agent_b"] == ["B:hello"]
