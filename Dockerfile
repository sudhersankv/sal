# Sal dashboard: Vite build + FastAPI event server (replay mode by default)
FROM node:24-slim AS web
WORKDIR /app/ui/web
COPY ui/web/package.json ui/web/package-lock.json ./
RUN npm ci
COPY ui/web/ ./
COPY ui/fixtures/ /app/ui/fixtures/
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
COPY --from=web /app/ui/web/dist ui/web/dist
EXPOSE 8080
RUN chmod +x deploy/fly_start.sh && python -c "import claude_agent_sdk, pathlib; b=pathlib.Path(claude_agent_sdk.__file__).parent/'_bundled'; print('bundled claude:', sorted(p.name for p in b.iterdir()))"
RUN useradd --create-home --uid 10001 sal && chown -R sal:sal /app
USER sal
ENV HOME=/home/sal
CMD ["bash", "deploy/fly_start.sh"]
