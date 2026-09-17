FROM node:24.13.0-bookworm-slim AS node
FROM ruby:3.4.4-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libpq-dev libvips-dev build-essential pkg-config git curl && rm -rf /var/lib/apt/lists/*
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx && npm install -g pnpm@10.2.0
ENV BUNDLE_PATH=/gems BUNDLE_JOBS=2 BUNDLE_RETRY=2 HUSKY=0 GRPC_RUBY_BUILD_PROCS=2 MAKEFLAGS=-j2
WORKDIR /app
COPY Gemfile Gemfile.lock ./
RUN gem install bundler -v 2.5.16 && bundle install
COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
