#!/usr/bin/env python3
"""Prepare an isolated, explicitly named Chatwoot qualification workspace."""

import argparse
import json
import re
import secrets
import shutil
import subprocess
from pathlib import Path

COMMIT = "5b7038b950b763e230df2d544df9b87b8752fef3"
HERE = Path(__file__).resolve().parent


def prepare(args):
    dest = args.destination.resolve()
    if dest.exists():
        raise SystemExit(
            "Destination already exists; choose a fresh directory (no implicit reset)."
        )
    if not re.fullmatch(r"pocket-tv-[a-z0-9-]+", args.project):
        raise SystemExit(
            "Project must start with pocket-tv- and use lowercase letters/digits/hyphens."
        )
    if (
        not all(1024 <= p <= 65535 for p in (args.port, args.vite_port))
        or args.port == args.vite_port
    ):
        raise SystemExit("Choose two distinct unprivileged ports.")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_./:@-]+", args.image):
        raise SystemExit("Invalid dependency image reference.")
    dest.mkdir(parents=True)
    subprocess.run(
        [
            "git",
            "clone",
            "--no-hardlinks",
            "--no-checkout",
            str(args.source.resolve()),
            str(dest / "source"),
        ],
        check=True,
    )
    subprocess.run(["git", "-C", str(dest / "source"), "checkout", "--detach", COMMIT], check=True)
    for name in ("Dockerfile", "nginx.conf", "fixture.rb"):
        shutil.copy2(HERE / name, dest / name)
    (dest / "nginx.conf").write_text(
        (dest / "nginx.conf").read_text().replace("33336", str(args.vite_port))
    )
    proc = dest / "source" / "Procfile.worktree"
    proc.write_text(
        "backend: bundle exec rails server -b 0.0.0.0 -p 3000\n"
        f"vite: VITE_RUBY_HOST=0.0.0.0 pnpm exec vite --port {args.vite_port}\n"
    )
    env = dest / ".env"
    env.touch(mode=0o600)
    env.write_text(f"""RAILS_ENV=development
NODE_ENV=development
DISABLE_ENTERPRISE=true
POSTGRES_HOST=postgres
POSTGRES_USERNAME=pocket
POSTGRES_PASSWORD=pocket-local-only
POSTGRES_DATABASE=pocket_team_views
REDIS_URL=redis://redis:6379
SECRET_KEY_BASE={secrets.token_hex(64)}
FRONTEND_URL=http://localhost:{args.port}
VITE_RUBY_HOST=localhost
VITE_RUBY_PORT={args.vite_port}
ACTIVE_STORAGE_SERVICE=local
DISABLE_SPRING=1
RAILS_LOG_TO_STDOUT=true
LOG_LEVEL=warn
ENABLE_ACCOUNT_SIGNUP=false
DISABLE_TELEMETRY=true
""")
    (dest / "compose.yaml").write_text(f"""name: {args.project}
x-app: &app
  image: {args.image}
  build:
    context: ./source
    dockerfile: ../Dockerfile
  working_dir: /app
  env_file: .env
  volumes:
    - ./source:/app
    - node_modules:/app/node_modules
    - ./fixture.rb:/bench/fixture.rb:ro
  depends_on:
    postgres:
      condition: service_healthy
    redis:
      condition: service_healthy
services:
  app:
    <<: *app
    command: bundle exec foreman start -f Procfile.worktree
    mem_limit: 3g
  proxy:
    image: nginx:1.28-alpine
    ports: ["127.0.0.1:{args.port}:3000", "127.0.0.1:{args.vite_port}:{args.vite_port}"]
    volumes: ["./nginx.conf:/etc/nginx/conf.d/default.conf:ro"]
    networks: [default, ingress]
    depends_on: [app]
    mem_limit: 128m
  postgres:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: pocket
      POSTGRES_PASSWORD: pocket-local-only
      POSTGRES_DB: pocket_team_views
    volumes: ["postgres:/var/lib/postgresql/data"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U pocket -d pocket_team_views"]
      interval: 3s
      retries: 20
    mem_limit: 512m
  redis:
    image: redis:7.4-alpine
    command: redis-server --save "" --appendonly no
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 3s
      retries: 20
    mem_limit: 128m
volumes:
  node_modules:
  postgres:
networks:
  default:
    internal: true
  ingress: {{}}
""")
    manifest = {
        "schema_version": 1,
        "task_version": "0.1-draft",
        "fixture_version": 1,
        "source_commit": COMMIT,
        "project": args.project,
        "port": args.port,
        "vite_port": args.vite_port,
        "dependency_image": args.image,
        "purpose": "maintainer qualification, not an evaluated agent run",
    }
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(dest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, required=True, help="Existing local upstream git clone"
    )
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--port", type=int, default=33081)
    parser.add_argument("--vite-port", type=int, default=33337)
    parser.add_argument("--image", default="pocket-team-views-dependencies:5b7038b")
    prepare(parser.parse_args())
