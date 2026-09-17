# Disposable development environment

Run these commands from the supplied `source/` directory. The parent directory
contains this attempt's `compose.yaml` and synthetic service configuration.
`BENCHMARK_FIXTURE.json` lists users and records; all fixture passwords are
`PocketBench123!`. See the supplied browser URL for the running app.

The app uses Rails development mode and Vite, so ordinary source changes reload.
For changes that require a restart or migration:

```sh
docker compose -f ../compose.yaml exec app bundle exec rails db:migrate
docker compose -f ../compose.yaml restart app
```

Run backend tests against a separate database and Redis namespace:

```sh
docker compose -f ../compose.yaml run --rm \
  -e RAILS_ENV=test -e POSTGRES_DATABASE=pocket_team_views_test \
  -e REDIS_URL=redis://redis:6379/1 \
  app bundle exec rails db:create db:schema:load
docker compose -f ../compose.yaml run --rm \
  -e RAILS_ENV=test -e POSTGRES_DATABASE=pocket_team_views_test \
  -e REDIS_URL=redis://redis:6379/1 \
  app bundle exec rspec spec/models/custom_filter_spec.rb
docker compose -f ../compose.yaml exec -e NODE_ENV=test app \
  pnpm test app/javascript/dashboard/components/specs/ChatListHeader.spec.js \
  --minWorkers=1 --maxWorkers=2
```

`CHECKS.json` lists the full required regression paths. Add your own tests without
weakening the fixed tests, their support code or lint/test configurations.
Start a worker when testing asynchronous creator deletion:

```sh
docker compose -f ../compose.yaml run --rm app bundle exec sidekiq -c 1
```

That command runs in the foreground; stop it when finished. It uses only this
attempt's database and Redis. Do not run `db:reset` on the populated development
database to make an upgrade work. The grader upgrades its own original data and
separately checks a fresh installation.

Before submission, write `BENCHMARK_NOTES.md` with your design, migrations,
verification results and limitations. Stage new implementation/test files and
notes (`git add -N path` is enough). Provide `UI-MAP.json` using the public
`UI-PROTOCOL.md` and example. Source collection ignores untracked files; the UI
map is supplied separately. Do not stage `.env`, runtime data or generated builds.

The production grader has its own clean database, non-root containers, prepared
dependencies and 5 GiB build container. It builds the SDK and Vite entrypoints
with the command in `CHECKS.json`, without an interactive dependency reinstall.
If locked dependencies change, a matching prepared image is needed before grading.
