.PHONY: lint test smoke compose-up compose-down

lint:
	python -m compileall backend/app sandbox-controller/app

test:
	python -m unittest discover -s backend/tests
	python -m unittest discover -s sandbox-controller/tests

smoke:
	docker compose config >/dev/null

compose-up:
	docker compose up --build

compose-down:
	docker compose down --remove-orphans
