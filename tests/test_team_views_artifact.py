"""Exercise the candidate-transfer boundary, without starting candidate code."""

import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

HERE = Path(__file__).parents[1] / "experiments/chatwoot-team-views"
spec = importlib.util.spec_from_file_location("artifact", HERE / "artifact.py")
artifact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(artifact)


@pytest.mark.parametrize(
    "name",
    [
        ".",
        "../escape",
        "/absolute",
        "a/../b",
        "a//b",
        "a\\b",
        ".git/config",
        ".env",
        "nested/.env.local",
        "node_modules/a",
        "tmp/token",
    ],
)
def test_rejects_paths_outside_source_contract(name):
    with pytest.raises(ValueError):
        artifact.validate({name: (0o100644, b"data")})


@pytest.mark.parametrize(
    "entries",
    [
        {"link": (0o120000, b"../outside")},
        {"link": (0o120000, b"/outside")},
        {"link": (0o120000, b"missing")},
        {"a": (0o120000, b"b"), "b": (0o120000, b"a")},
        {"a": (0o100644, b"file"), "a/b": (0o100644, b"nested")},
    ],
)
def test_rejects_escaping_links_and_ambiguous_trees(entries):
    with pytest.raises(ValueError):
        artifact.validate(entries)


def test_round_trip_modes_content_and_internal_link(tmp_path):
    entries = {"bin/run": (0o100755, b"#!/bin/sh\n"), "doc/link": (0o120000, b"../bin/run")}
    path = tmp_path / "submission.zip"
    artifact.write_artifact(entries, path)
    assert artifact.read_artifact(path) == entries
    with pytest.raises(FileExistsError):
        artifact.write_artifact(entries, path)
    with tarfile.open(fileobj=io.BytesIO(artifact.volume_tar(entries))) as tar:
        assert tar.getmember("doc/link").issym()
        assert tar.getmember("bin/run").uid == 1000
        assert tar.getmember("bin/run").mode == 0o755


def test_rejects_tampered_content_even_if_zip_is_valid(tmp_path):
    original = tmp_path / "source.zip"
    altered = tmp_path / "altered.zip"
    artifact.write_artifact({"app.rb": (0o100644, b"good")}, original)
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(altered, "w") as target:
        target.writestr("manifest.json", source.read("manifest.json"))
        target.writestr("source/app.rb", b"evil")
    with pytest.raises(ValueError, match="manifest"):
        artifact.read_artifact(altered)


def test_rejects_archive_bomb_before_reading_payload(tmp_path, monkeypatch):
    path = tmp_path / "huge.zip"
    artifact.write_artifact({"app.rb": (0o100644, b"x" * 10000)}, path)
    monkeypatch.setattr(artifact, "MAX_FILE", 5000)
    with pytest.raises(ValueError, match="uncompressed"):
        artifact.read_artifact(path)


def test_source_collection_does_not_include_untracked_secrets(tmp_path, monkeypatch):
    (tmp_path / "app.rb").write_text("source")
    (tmp_path / ".env").write_text("synthetic-secret")
    (tmp_path / "hidden_test.rb").write_text("private")
    monkeypatch.setattr(
        artifact.subprocess, "check_output", lambda *a, **kw: b"app.rb\0deleted.rb\0"
    )
    assert artifact.collect(tmp_path) == {"app.rb": (0o100644, b"source")}


def test_directory_symlink_is_not_followed(tmp_path, monkeypatch):
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret").write_text("synthetic")
    (tmp_path / "alias").symlink_to(tmp_path / "outside", target_is_directory=True)
    monkeypatch.setattr(artifact.subprocess, "check_output", lambda *a, **kw: b"alias/secret\0")
    with pytest.raises(ValueError, match="Symlink in source"):
        artifact.collect(tmp_path)


def test_verifier_configuration_has_no_host_mounts_or_agent_credentials(monkeypatch):
    monkeypatch.setitem(sys.modules, "artifact", artifact)
    isolated_spec = importlib.util.spec_from_file_location("isolated", HERE / "isolated.py")
    isolated = importlib.util.module_from_spec(isolated_spec)
    isolated_spec.loader.exec_module(isolated)
    config = isolated.configuration(
        "pocket-tv-unit",
        33085,
        33341,
        dict.fromkeys(("app", "postgres", "redis", "proxy"), "sha256:test"),
    )
    for service in config["services"].values():
        for mount in service.get("volumes", []):
            assert mount.split(":")[0] in config["volumes"]
    app = config["services"]["app"]
    assert app["user"] == "1000:1000"
    assert app["cap_drop"] == ["ALL"]
    assert config["networks"]["default"]["internal"]
    assert "networks" not in app
    assert "baseline:/app" not in app["volumes"]
    assert "bench" not in json.dumps(app["volumes"])


@pytest.mark.parametrize("mutation", ["host_mount", "root_user", "external_network", "privileged"])
def test_runtime_audit_rejects_weakened_container_boundary(tmp_path, monkeypatch, mutation):
    monkeypatch.setitem(sys.modules, "artifact", artifact)
    module_spec = importlib.util.spec_from_file_location("isolated_audit", HERE / "isolated.py")
    isolated = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(isolated)
    project = "pocket-tv-audit"
    (tmp_path / "manifest.json").write_text(json.dumps({"project": project}))
    actual = {
        "user": "1000:1000",
        "privileged": False,
        "cap_drop": ["ALL"],
        "security": ["no-new-privileges:true"],
        "networks": {project + "_default": {}},
        "mounts": [{"Type": "volume", "Name": project + "_candidate"}],
    }
    if mutation == "host_mount":
        actual["mounts"][0] = {"Type": "bind", "Source": "/host"}
    elif mutation == "root_user":
        actual["user"] = "0:0"
    elif mutation == "external_network":
        actual["networks"]["bridge"] = {}
    else:
        actual["privileged"] = True

    def output(command, **kwargs):
        return json.dumps(actual) if "inspect" in command else "container-id"

    monkeypatch.setattr(isolated.subprocess, "check_output", output)
    with pytest.raises(RuntimeError, match="boundary"):
        isolated.audit(["docker", "compose"], tmp_path)
    assert not (tmp_path / "boundary-check.json").exists()
