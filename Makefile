.PHONY: help install-backend install-frontend setup-db run-backend run-frontend run-docker clean

help:
	@echo "Available commands:"
	@echo "  make install-backend  - Install Python dependencies"
	@echo "  make install-frontend - Install Node.js dependencies"
	@echo "  make setup-db         - Process GCIDE dictionary data"
	@echo "  make run-backend      - Run backend API server"
	@echo "  make run-frontend     - Run frontend dev server"
	@echo "  make run-docker       - Run with Docker Compose"
	@echo "  make clean            - Clean generated files"

install-backend:
	pip install -r requirements.txt

install-frontend:
	cd client && npm install

setup-db:
	python -m app.data.process_gcide --data-dir data/gcide_raw --db-path data/gcide.db

run-backend:
	uvicorn app.main:app --reload --port 8000

run-frontend:
	cd client && npm run dev

run-docker:
	docker-compose up --build

clean:
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf client/node_modules
	rm -rf client/dist
	rm -rf .venv venv

