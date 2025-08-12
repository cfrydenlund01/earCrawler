from pathlib import Path

import pytest

import earCrawler.kg.fuseki as fuseki


def test_build_fuseki_cmd_windows_paths(tmp_path, monkeypatch):
    jena_home = tmp_path / "tools" / "jena"
    server = jena_home / "bat" / "fuseki-server.bat"
    server.parent.mkdir(parents=True)
    server.write_text("")
    monkeypatch.setattr(fuseki, "ensure_jena", lambda download=True: jena_home)
    monkeypatch.setattr(fuseki, "fuseki_server_path", lambda: server)
    cmd = fuseki.build_fuseki_cmd(tmp_path / "db", "/ear", 3030)
    assert Path(cmd[0]).resolve() == server.resolve()
    assert "--loc" in cmd
    assert cmd[-1] == "/ear"


class DummyProc:
    pid = 123

    def __init__(self, *a, **kw):
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = 0

    def wait(self, timeout=None):  # pragma: no cover - not used
        return self.returncode


def test_start_fuseki_dry_waits_and_times_out(tmp_path, monkeypatch):
    jena_home = tmp_path / "tools" / "jena"
    (jena_home / "bin").mkdir(parents=True)
    (jena_home / "bin" / "fuseki-server").write_text("")
    monkeypatch.setattr(fuseki, "ensure_jena", lambda download=True: jena_home)

    monkeypatch.setattr(fuseki.subprocess, "Popen", lambda *a, **k: DummyProc())

    def bad_get(*a, **k):
        raise fuseki.requests.RequestException("fail")

    monkeypatch.setattr(fuseki.requests, "get", bad_get)

    times = iter([0, 0.6, 1.2])
    monkeypatch.setattr(fuseki.time, "time", lambda: next(times))
    monkeypatch.setattr(fuseki.time, "sleep", lambda _t: None)

    with pytest.raises(RuntimeError):
        fuseki.start_fuseki(tmp_path / "db", timeout_s=1)


def test_start_fuseki_no_wait_returns_popen(tmp_path, monkeypatch):
    jena_home = tmp_path / "tools" / "jena"
    (jena_home / "bin").mkdir(parents=True)
    (jena_home / "bin" / "fuseki-server").write_text("")
    monkeypatch.setattr(fuseki, "ensure_jena", lambda download=True: jena_home)

    sentinel = object()
    monkeypatch.setattr(fuseki.subprocess, "Popen", lambda *a, **k: sentinel)

    def raiser(*a, **k):  # pragma: no cover - should not run
        raise AssertionError("HTTP call made")

    monkeypatch.setattr(fuseki.requests, "get", raiser)

    proc = fuseki.start_fuseki(tmp_path / "db", wait=False)
    assert proc is sentinel
