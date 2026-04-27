.PHONY: lint test smoke e2e-mock e2e-task compose-up compose-down

lint:
	python -m compileall backend/app sandbox-controller/app

test:
	python -m unittest discover -s backend/tests
	python -m unittest discover -s sandbox-controller/tests

smoke:
	docker compose config >/dev/null

e2e-mock:
	python scripts/e2e_mock.py

e2e-task:
	python scripts/e2e_task.py

compose-up:
	docker compose up --build

compose-down:
	docker compose down --remove-orphans
