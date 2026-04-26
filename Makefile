.PHONY: setup demo eval lint test

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
