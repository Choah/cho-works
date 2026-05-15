from __future__ import annotations

import os
import socket
import subprocess
import time
import urllib.request


def test_wheel_install_runs_cli_and_serves_static_asset(tmp_path):
    dist_dir = tmp_path / "dist"
    venv_dir = tmp_path / "venv"
    db_path = tmp_path / "data" / "cho.sqlite3"

    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(dist_dir)],
        check=True,
        text=True,
        capture_output=True,
    )
    wheel = next(dist_dir.glob("cho_works-*.whl"))

    subprocess.run(["uv", "venv", str(venv_dir)], check=True, text=True, capture_output=True)
    subprocess.run(
        ["uv", "pip", "install", "--python", str(venv_dir / "bin" / "python"), str(wheel)],
        check=True,
        text=True,
        capture_output=True,
    )

    env = {**os.environ, "CHO_WORKS_DB_PATH": str(db_path)}
    cho = venv_dir / "bin" / "cho"
    result = subprocess.run(
        [str(cho), "init"],
        check=True,
        text=True,
        capture_output=True,
        env=env,
    )

    assert db_path.exists()
    assert "Cho Works 준비 완료" in result.stdout

    port = _free_port()
    server = subprocess.Popen(
        [str(venv_dir / "bin" / "cho-web"), "--host", "127.0.0.1", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        content = _read_url(f"http://127.0.0.1:{port}/static/img/parrot-companion.png")
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

    assert content.startswith(b"\x89PNG")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _read_url(url: str, timeout: float = 10.0) -> bytes:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                return response.read()
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise AssertionError(f"Timed out waiting for {url}: {last_error}")
