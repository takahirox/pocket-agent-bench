"""Compile the reviewable catalog into native Harbor task directories."""

import hashlib
import json
import shutil
from pathlib import Path

from pocket_bench.execution import CONTRACT


def catalog(root):
    return json.loads((Path(root) / "suite/catalog.json").read_text())


def build(root):
    root = Path(root)
    tasks = root / "tasks"
    tasks.mkdir(exist_ok=True)
    for spec in catalog(root):
        task = tasks / spec["id"]
        for d in ("environment/input", "environment/src", "tests", "solution"):
            (task / d).mkdir(parents=True, exist_ok=True)
        for path, content in spec["files"].items():
            target = task / "environment" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
        (task / "instruction.md").write_text(
            spec["instruction"]
            + "\nWorkspace: /app. Python 3 standard library and Git are available.\n"
            + (CONTRACT if spec.get("api") else "")
        )
        metadata = {
            "category": spec["category"],
            "tags": spec["tags"],
            "source": "pocket-original",
            "human_reviewed": False,
            "capabilities": ["filesystem", "python"]
            + (["http-loopback"] if spec.get("api") else []),
            "network_enforcement": "compose-internal-model-proxy-v1",
            "execution_transport": "pocket-python-v1" if spec.get("api") else "none",
        }
        config = (
            'schema_version = "1.4"\n[task]\nname = "pocket/'
            + spec["id"]
            + '"\nversion = "1.1.0"\n'
            + "[metadata]\n"
            + "\n".join(
                f"{k} = {json.dumps(v) if not isinstance(v, bool) else str(v).lower()}"
                for k, v in metadata.items()
            )
            + '\n[agent]\nuser = "agent"\ntimeout_sec = 240.0\n'
            + '[verifier]\nuser = "root"\ntimeout_sec = 45.0\nenvironment_mode = "separate"\n[verifier.environment]\nnetwork_mode = "public"\ncpus = 2\nmemory_mb = 2048\n'
            + '[environment]\n# Egress is enforced by the internal Compose network and model-only proxy.\nnetwork_mode = "public"\ncpus = 2\nmemory_mb = 2048\nbuild_timeout_sec = 600.0\n'
        )
        (task / "task.toml").write_text(config)
        for name in ("mock_api.py", "bootstrap.py", "model_proxy.py", "smoke.py", "execution.py"):
            shutil.copy(Path(__file__).with_name(name), task / "environment" / name)
        (task / "environment/Dockerfile").write_text(
            'FROM pocket-agent-bench-runtime:0.1\nCOPY --chown=agent:agent input/ /app/input/\nCOPY --chown=agent:agent src/ /app/src/\nCOPY mock_api.py bootstrap.py smoke.py execution.py /opt/pocket/\nWORKDIR /app\nENTRYPOINT ["python", "/opt/pocket/bootstrap.py"]\n'
        )
        (task / "environment/Proxy.Dockerfile").write_text(
            'FROM python:3.12-slim-bookworm\nCOPY model_proxy.py /proxy.py\nUSER 65534\nCMD ["python", "-I", "/proxy.py"]\n'
        )
        (task / "environment/docker-compose.yaml").write_text("""services:
  main:
    networks: [task]
    # Let Codex create its nested read-only/workspace sandbox. No added capabilities.
    security_opt: [seccomp=unconfined]
    environment:
      HTTPS_PROXY: http://model-proxy:3128
      HTTP_PROXY: http://model-proxy:3128
      NO_PROXY: localhost,127.0.0.1
    depends_on: [model-proxy]
  model-proxy:
    build:
      context: .
      dockerfile: Proxy.Dockerfile
    networks: [task, model]
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
networks:
  task:
    internal: true
  model: {}
""")
        (task / "tests/spec.json").write_text(json.dumps(spec, indent=2) + "\n")
        shutil.copy(Path(__file__).with_name("grader.py"), task / "tests/grader.py")
        (task / "tests/test.sh").write_text(
            "#!/bin/sh\nset -eu\npython -I /tests/grader.py /tests/spec.json /app\n"
        )
        (task / "tests/Dockerfile").write_text(
            "FROM pocket-agent-bench-runtime:0.1\nCOPY grader.py spec.json test.sh /tests/\nRUN chmod 700 /tests\nWORKDIR /app\n"
        )
        (task / "tests/docker-compose.yaml").write_text(
            "services:\n  main:\n    network_mode: none\n"
        )
        # Oracle executes a reference implementation or a fixed independently reviewable expected artifact.
        if "solution" in spec:
            solution = (
                "from pathlib import Path\nPath('src/solution.py').write_text("
                + repr(spec["solution"])
                + ")\n"
            )
        else:
            solution = (
                "import json\nfrom pathlib import Path\nPath('output').mkdir(exist_ok=True)\nPath('output/result.json').write_text("
                + repr(json.dumps(spec["expected"]))
                + ")\n"
            )
        if spec.get("api"):
            calls = {
                "pagination": ["/items", "/items?page=2"],
                "retry": ["/value"] * 3,
                "approval": ["/request", "/approval"],
            }[spec["api"]]
            solution += (
                "import urllib.request,urllib.error\nfor path in "
                + repr(calls)
                + ":\n    try: urllib.request.urlopen('http://127.0.0.1:8080'+path).read()\n    except urllib.error.HTTPError: pass\n"
            )
        (task / "solution/solve.py").write_text(solution)
        (task / "solution/solve.sh").write_text(
            "#!/bin/sh\nset -eu\ncd /app\npython /solution/solve.py\n"
        )
    digest = hashlib.sha256(
        (root / "suite/catalog.json").read_bytes()
        + Path(__file__).with_name("grader.py").read_bytes()
        + Path(__file__).with_name("execution.py").read_bytes()
    ).hexdigest()
    (root / "suite/manifest.json").write_text(
        json.dumps(
            {
                "version": "1.1",
                "sha256": digest,
                "tasks": len(catalog(root)),
                "human_reviewed": False,
            },
            indent=2,
        )
        + "\n"
    )
    return tasks
