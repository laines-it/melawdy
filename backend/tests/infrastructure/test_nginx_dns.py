import json
from pathlib import Path
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[3]
SERVER = """
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

class Handler(BaseHTTPRequestHandler):
    def respond(self):
        size = int(self.headers.get('Content-Length', '0'))
        body = self.rfile.read(size).decode() if size else ''
        data = json.dumps({'backend': os.environ['BACKEND_NAME'], 'path': self.path,
                           'method': self.command, 'body': body}).encode()
        self.send_response(201 if self.command == 'POST' else 200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = respond
    do_POST = respond

HTTPServer(('0.0.0.0', 8000), Handler).serve_forever()
"""


def docker(*arguments):
    result = subprocess.run(["docker", *arguments], text=True, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def wait_for_backend(url, expected, payload=None):
    deadline = time.monotonic() + 30
    last_error = None
    while time.monotonic() < deadline:
        try:
            request = Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=2) as response:
                result = json.load(response)
                if result["backend"] == expected:
                    return response.status, result
                last_error = result
        except (HTTPError, URLError, TimeoutError, OSError) as error:
            last_error = error
        time.sleep(0.5)
    raise AssertionError(f"Nginx did not resolve backend {expected}: {last_error}")


@pytest.mark.parametrize("search_domain", [None, "melawdy.svc.cluster.local"])
def test_nginx_recovers_after_api_ip_changes_without_web_restart(search_domain):
    prefix = f"melawdy-dns-test-{uuid4().hex[:12]}"
    image = f"{prefix}:web"
    network = f"{prefix}-network"
    frontend = f"{prefix}-web"
    first = f"{prefix}-first"
    second = f"{prefix}-second"
    alias = f"api.{search_domain}" if search_domain else "api"
    try:
        docker("build", "-t", image, str(ROOT / "web"))
        docker("network", "create", network)
        docker("run", "-d", "--name", first, "--network", network, "--network-alias", alias,
               "-e", "BACKEND_NAME=first", "python:3.12-slim", "python", "-u", "-c", SERVER)
        dns_options = ["--dns-search", search_domain] if search_domain else []
        docker("run", "-d", "--name", frontend, "--network", network, *dns_options,
               "-p", "127.0.0.1::80", image)
        host = docker("port", frontend, "80/tcp")
        base = f"http://{host}"
        path = "/api/v1/status?query=%D0%BC%D1%83%D0%B7%D1%8B%D0%BA%D0%B0&limit=2"
        assert wait_for_backend(base + path, "first")[1]["path"] == path
        started = docker("inspect", "--format", "{{.State.StartedAt}}", frontend)
        first_ip = docker("inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", first)
        docker("run", "-d", "--name", second, "--network", network, "--network-alias", alias,
               "-e", "BACKEND_NAME=second", "python:3.12-slim", "python", "-u", "-c", SERVER)
        second_ip = docker("inspect", "--format", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", second)
        assert first_ip != second_ip
        docker("rm", "-f", first)
        assert wait_for_backend(base + path, "second")[1]["path"] == path
        for endpoint in ["login", "register", "change-password"]:
            body = b'{"test":"request"}'
            status, result = wait_for_backend(base + f"/api/v1/auth/{endpoint}", "second", body)
            assert status == 201
            assert result["method"] == "POST"
            assert result["body"] == body.decode()
            assert result["path"] == f"/api/v1/auth/{endpoint}"
        assert docker("inspect", "--format", "{{.State.StartedAt}}", frontend) == started
        docker("exec", frontend, "nginx", "-t")
    finally:
        subprocess.run(["docker", "rm", "-f", frontend, first, second], capture_output=True, timeout=30)
        subprocess.run(["docker", "network", "rm", network], capture_output=True, timeout=30)
        subprocess.run(["docker", "image", "rm", image], capture_output=True, timeout=30)
