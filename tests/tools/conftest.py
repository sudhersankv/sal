import pytest


@pytest.fixture(autouse=True)
def _offline_fixture_world(monkeypatch, tmp_path):
    """Fast + deterministic: fixture DB, no network, events to a tmp runs dir."""
    monkeypatch.setenv("SAL_TOOLS_OFFLINE", "1")
    monkeypatch.setenv("SAL_TOOLS_DATA", "fixtures")
    monkeypatch.setenv("SAL_EVENTS_POST", "0")
    monkeypatch.setenv("SAL_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SAL_RUN_ID", "test")
    for k in ("SAL_VARIANT", "SAL_GATE_ROUTING", "SAL_GATE_ROUTING_V2", "SPEND_CAP", "SAL_NO_BUY"):
        monkeypatch.delenv(k, raising=False)
    from tools import context, data, impl
    monkeypatch.setattr(impl, "VENDOR_URL", "http://127.0.0.1:9")
    data.reset_local()
    context.set_context(day=None, ts=None, run_id=None, variant=None)
    yield tmp_path
    context.set_context(day=None, ts=None, run_id=None, variant=None)
