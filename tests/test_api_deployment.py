"""Deployment recipe safety; does not create resources or require credentials."""

import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def run_start(tmp_path, **env):
    fake = tmp_path / "uvicorn"
    fake.write_text("#!/bin/sh\nprintf '%s\\n' \"$@\"\numask\n")
    fake.chmod(0o700)
    return subprocess.run(
        ["sh", str(ROOT / "scripts/start-api.sh")],
        env={"PATH": str(tmp_path) + os.pathsep + os.defpath, **env},
        capture_output=True,
        text=True,
    )


def test_api_start_respects_port_and_single_worker(tmp_path):
    result = run_start(tmp_path, PORT="10000", FORWARDED_ALLOW_IPS="10.1.2.3")
    assert result.returncode == 0
    args = result.stdout.splitlines()
    assert args[args.index("--port") + 1] == "10000"
    assert args[args.index("--workers") + 1] == "1"
    assert args[args.index("--forwarded-allow-ips") + 1] == "10.1.2.3"
    assert args[-1].endswith("77")


def test_api_start_defaults_to_loopback_proxy_only(tmp_path):
    result = run_start(tmp_path)
    assert result.returncode == 0
    assert "127.0.0.1" in result.stdout.splitlines()


@pytest.mark.parametrize("port", ["0", "65536", "not-a-port", "80;echo unsafe"])
def test_api_start_rejects_invalid_port(tmp_path, port):
    assert run_start(tmp_path, PORT=port).returncode != 0


def test_api_start_rejects_wildcard_proxy_trust(tmp_path):
    assert run_start(tmp_path, FORWARDED_ALLOW_IPS="*").returncode != 0


def test_render_recipe_keeps_state_and_disables_automatic_activation():
    service = yaml.safe_load((ROOT / "render.yaml").read_text())["services"][0]
    assert service["branch"] == "feature/kuwaiti-video-lessons"
    assert service["autoDeployTrigger"] == "off"
    assert service["numInstances"] == 1
    assert "maxShutdownDelaySeconds" not in service  # Render disks do not allow it.
    assert service["disk"]["mountPath"] == "/data"
    assert service["disk"]["sizeGB"] == 5
    variables = {v["key"]: v for v in service["envVars"]}
    assert variables["NAWAB_ENABLE_AI"]["value"] == "false"
    assert variables["NAWAB_REQUIRE_HTTPS"]["value"] == "true"
    assert variables["NAWAB_DB_PATH"]["value"].startswith("/data/")
    for secret in ("NAWAB_PASSWORD", "NAWAB_TOKEN_SECRET"):
        assert variables[secret] == {"key": secret, "sync": False}
    assert "GEMINI_API_KEY" not in variables
    assert "OPENAI_API_KEY" not in variables
