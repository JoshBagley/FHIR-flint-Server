.PHONY: help start start-obs start-full stop restart rebuild logs test clean migrate

help:
	@echo "Available commands:"
	@echo "  make start          - Start core services"
	@echo "  make start-obs      - Start core + observability (Prometheus, Grafana, Loki, Promtail) + tools (Adminer)"
	@echo "  make start-full     - Start all services including pgAdmin and Kibana"
	@echo "  make stop           - Stop all services (all profiles)"
	@echo "  make restart        - Restart all services (all profiles)"
	@echo "  make logs           - View logs (all services)"
	@echo "  make test           - Run tests"
	@echo "  make rebuild        - Rebuild and restart backend and frontend"
	@echo "  make migrate        - Run migrations"
	@echo "  make clean          - Stop and remove all data volumes"

start:
	docker compose up -d

start-obs:
	docker compose --profile observability --profile tools up -d

start-full:
	docker compose --profile observability --profile tools --profile admin up -d

rebuild:
	docker compose up -d --build backend frontend

stop:
	docker compose --profile observability --profile tools --profile admin down

restart:
	docker compose --profile observability --profile tools --profile admin restart

logs:
	docker compose logs -f

test:
	docker compose exec backend pytest tests/ -v

migrate:
	docker compose exec backend alembic upgrade head

clean:
	docker compose --profile observability --profile tools --profile admin down -v
	rm -rf data/
