from __future__ import annotations

"""Helpers for launching a local Apache Jena Fuseki server."""

from pathlib import Path
import os
import subprocess
import time
import contextlib
import socket
from typing import Optional

import requests

from earCrawler.utils.fuseki_tools import ensure_fuseki


def fuseki_server_path() -> Path:
    """Return the absolute path to the Fuseki server executable.

    On Windows the batch file is at the root of the extracted Fuseki archive,
    while on POSIX systems it lives alongside the other launch scripts.
    """

    fuseki_home = ensure_fuseki(download=True)
    if os.name == "nt":
        exe = fuseki_home / "fuseki-server.bat"
    else:
        exe = fuseki_home / "fuseki-server"
    return exe.resolve()


def build_fuseki_cmd(
    db_dir: Path, dataset: str, port: int, java_opts: Optional[str] = None
) -> list[str]:
    """Build the Fuseki server command line.

    Parameters are passed as CLI arguments; any ``java_opts`` should be handled
    by setting the ``FUSEKI_JAVA_OPTS`` environment variable when launching the
    process.
    """

    server = fuseki_server_path()
    cmd = [
        str(server),
        "--port",
        str(port),
        "--loc",
        str(Path(db_dir).resolve()),
        dataset,
    ]
    return cmd


def _port_in_use(port: int) -> bool:
    """Return ``True`` if ``port`` on localhost is listening.

    Some test environments (notably those using the ``pytest-socket`` plugin)
    disallow any use of :mod:`socket`.  In those cases attempting to open a
    socket raises an exception.  Rather than letting that bubble up and fail the
    test suite we treat the port as free, which is sufficient for our use in
    unit tests.
    """

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            return sock.connect_ex(("localhost", port)) == 0
    except Exception:  # pragma: no cover - best effort for constrained envs
        return False


def start_fuseki(
    db_dir: Path,
    dataset: str = "/ear",
    port: int = 3030,
    wait: bool = True,
    timeout_s: int = 30,
    java_opts: Optional[str] = None,
) -> subprocess.Popen:
    """Start a local Fuseki process serving ``db_dir`` on ``port``.

    If ``wait`` is True the function blocks until ``/$/ping`` responds or the
    timeout elapses. A ``RuntimeError`` is raised on failure or when the port is
    already in use.
    """

    if _port_in_use(port):
        raise RuntimeError(f"Port {port} already in use")

    cmd = build_fuseki_cmd(db_dir, dataset, port, java_opts)
    env = os.environ.copy()
    if java_opts:
        env["FUSEKI_JAVA_OPTS"] = java_opts

    server_path = Path(cmd[0])
    proc = subprocess.Popen(cmd, env=env, shell=False, cwd=server_path.parent)

    if not wait:
        return proc

    try:
        wait_until_ready(port, timeout_s=timeout_s, proc=proc)
    except Exception as exc:  # pragma: no cover - error path
        proc.terminate()
        raise RuntimeError(f"Fuseki failed to start: {exc}") from exc

    return proc


def wait_until_ready(port: int, timeout_s: int = 30, proc: subprocess.Popen | None = None) -> None:
    """Poll ``/$/ping`` until Fuseki responds or timeout elapses."""

    deadline = time.time() + timeout_s
    delay = 0.1
    url = f"http://localhost:{port}/$/ping"
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError("Fuseki process exited prematurely")
        try:
            resp = requests.get(url, timeout=2)
            if resp.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(delay)
        delay = min(delay * 1.5, 1.0)
    raise RuntimeError("Fuseki server did not become ready in time")


@contextlib.contextmanager
def running_fuseki(
    db_dir: Path,
    dataset: str = "/ear",
    port: int = 3030,
    java_opts: Optional[str] = None,
):
    """Context manager to start and terminate Fuseki."""

    proc = start_fuseki(db_dir, dataset=dataset, port=port, wait=True, java_opts=java_opts)
    try:
        yield proc
    finally:  # pragma: no branch - cleanup
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
