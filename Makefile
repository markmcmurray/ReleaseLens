.PHONY: setup demo eval lint test langfuse-up langfuse-down

setup:
	uv sync --all-extras

demo:
	uv run releaselens run --pep-ids 658,691,740

eval:
	uv run releaselens eval

lint:
	uv run ruff check .
	uv run ruff format --check .

test:
	uv run pytest

langfuse-up:
	cd infra/langfuse && [ -f .env ] || cp .env.example .env
	cd infra/langfuse && docker compose up -d

langfuse-down:
	cd infra/langfuse && docker compose down
