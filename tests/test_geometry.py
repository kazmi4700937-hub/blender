"""Tests for the geometry provider switch. No network and no API key are used."""

import json

import pytest

from orchestrator.geometry import GeometryError, GeometryRequest, get_provider, provider_name
from orchestrator.geometry.tripo import TripoProvider


class FakeResponse:
    def __init__(self, payload=None, status=200, content=b""):
        self._payload = payload
        self.status_code = status
        self.content = content

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """Plays the part of the Tripo API. Records every call so tests can check what was sent."""

    def __init__(self, riggable=True, fail_generation=False):
        self.calls = []
        self.riggable = riggable
        self.fail_generation = fail_generation
        self.tasks = {}
        self.polls = 0

    def post(self, url, json=None, files=None, headers=None, timeout=None):
        self.calls.append(("POST", url, json))
        if url.endswith("/files"):
            return FakeResponse({"code": 0, "data": {"file_token": "file_1"}})
        task_id = f"task_{len(self.tasks) + 1}"
        if url.endswith("/generation/image-to-model"):
            out = {"model_url": "https://cdn.example/model.glb"}
            self.tasks[task_id] = {"status": "failed" if self.fail_generation else "success",
                                   "error_code": 2001, "error_message": "bad image", "output": out,
                                   "credits_consumed": 30}
        elif url.endswith("/animations/rig-check"):
            self.tasks[task_id] = {"status": "success", "credits_consumed": 0,
                                   "output": {"riggable": self.riggable, "rig_type": "biped"}}
        elif url.endswith("/animations/rig"):
            self.tasks[task_id] = {"status": "success", "credits_consumed": 25,
                                   "output": {"model_url": "https://cdn.example/rigged.glb"}}
        return FakeResponse({"code": 0, "data": {"task_id": task_id}})

    def get(self, url, headers=None, timeout=None):
        self.calls.append(("GET", url, None))
        if "/tasks/" in url:
            self.polls += 1
            task_id = url.rsplit("/", 1)[1]
            task = dict(self.tasks[task_id])
            if self.polls == 1:          # first poll: still running, to exercise the wait loop
                task = {"status": "running"}
            return FakeResponse({"code": 0, "data": {"task_id": task_id, **task}})
        return FakeResponse(content=b"GLBDATA")


def make_image(tmp_path):
    path = tmp_path / "front.png"
    path.write_bytes(b"\x89PNG fake")
    return str(path)


def make_provider(session, cfg=None):
    return TripoProvider(cfg or {}, session=session, sleep=lambda s: None)


def test_default_provider_is_manual(monkeypatch):
    monkeypatch.delenv("GEOMETRY_PROVIDER", raising=False)
    assert provider_name({}) == "manual"
    assert provider_name({"geometry": {"provider": "tripo"}}) == "tripo"
    monkeypatch.setenv("GEOMETRY_PROVIDER", "manual")
    assert provider_name({"geometry": {"provider": "tripo"}}) == "manual"


def test_unknown_provider_lists_choices():
    with pytest.raises(GeometryError) as exc:
        get_provider("nope", cfg={})
    assert "manual" in str(exc.value) and "tripo" in str(exc.value)


def test_manual_provider_copies_model(tmp_path):
    src = tmp_path / "mine.glb"
    src.write_bytes(b"abc")
    req = GeometryRequest(image_paths=[], output_dir=str(tmp_path / "out"), options={"model_path": str(src)})
    res = get_provider("manual", cfg={}).generate(req)
    assert res.mesh_path.endswith("generated.glb")
    assert open(res.mesh_path, "rb").read() == b"abc"
    assert res.rigged_path is None


def test_manual_provider_errors_are_readable(tmp_path):
    prov = get_provider("manual", cfg={})
    with pytest.raises(GeometryError, match="needs a finished model"):
        prov.generate(GeometryRequest(image_paths=[], output_dir=str(tmp_path)))
    with pytest.raises(GeometryError, match="not found"):
        prov.generate(GeometryRequest([], str(tmp_path), options={"model_path": str(tmp_path / "x.glb")}))
    bad = tmp_path / "x.txt"
    bad.write_text("x")
    with pytest.raises(GeometryError, match="Unsupported"):
        prov.generate(GeometryRequest([], str(tmp_path), options={"model_path": str(bad)}))


def test_tripo_needs_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("TRIPO_API_KEY", raising=False)
    prov = make_provider(FakeSession())
    with pytest.raises(GeometryError, match="TRIPO_API_KEY"):
        prov.generate(GeometryRequest([make_image(tmp_path)], str(tmp_path / "out")))


def test_tripo_generate_without_rig(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPO_API_KEY", "k")
    session = FakeSession()
    res = make_provider(session).generate(GeometryRequest([make_image(tmp_path)], str(tmp_path / "out")))
    assert open(res.mesh_path, "rb").read() == b"GLBDATA"
    assert res.rigged_path is None
    assert res.credits_used == 30
    posts = [c for c in session.calls if c[0] == "POST"]
    assert posts[1][1].endswith("/generation/image-to-model")
    assert posts[1][2] == {"input": "file_1"}      # the placeholder was filled with the upload token
    assert session.polls >= 2                       # it waited for the running task


def test_tripo_generate_with_rig_uses_rig_check(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPO_API_KEY", "k")
    session = FakeSession()
    res = make_provider(session, {"rig": {"rig_type": "auto", "spec": "tripo", "out_format": "glb"}}).generate(
        GeometryRequest([make_image(tmp_path)], str(tmp_path / "out"), rig=True))
    assert res.rigged_path.endswith("rigged.glb")
    assert res.credits_used == 55
    rig_post = [c for c in session.calls if c[1].endswith("/animations/rig")][0]
    assert rig_post[2] == {"input": "task_1", "rig_type": "biped", "spec": "tripo", "out_format": "glb"}
    assert any("not a Rigify rig" in n for n in res.notes)


def test_tripo_rig_skipped_when_not_riggable(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPO_API_KEY", "k")
    session = FakeSession(riggable=False)
    res = make_provider(session).generate(GeometryRequest([make_image(tmp_path)], str(tmp_path / "out"), rig=True))
    assert res.rigged_path is None
    assert any("cannot be rigged" in n for n in res.notes)
    assert not any(c[1].endswith("/animations/rig") for c in session.calls)


def test_tripo_failed_task_shows_reason(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPO_API_KEY", "k")
    prov = make_provider(FakeSession(fail_generation=True))
    prov.timeout_seconds = 30
    with pytest.raises(GeometryError, match="bad image"):
        prov.generate(GeometryRequest([make_image(tmp_path)], str(tmp_path / "out")))


def test_tripo_error_response_shows_message(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPO_API_KEY", "k")

    class Rejecting(FakeSession):
        def post(self, url, json=None, files=None, headers=None, timeout=None):
            return FakeResponse({"code": 2010, "message": "insufficient credits"}, status=403)

    with pytest.raises(GeometryError, match="insufficient credits"):
        make_provider(Rejecting()).generate(GeometryRequest([make_image(tmp_path)], str(tmp_path / "out")))
