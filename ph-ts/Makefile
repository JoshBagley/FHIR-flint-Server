.PHONY: help start stop restart logs test clean migrate

help:
	@echo "Available commands:"
	@echo "  make start          - Start all services"
	@echo "  make stop           - Stop all services"
	@echo "  make restart        - Restart all services"
	@echo "  make logs           - View logs"
	@echo "  make test           - Run tests"
	@echo "  make migrate        - Run migrations"
	@echo "  make clean          - Clean up resources"

start:
	docker-compose up -d

stop:
	docker-compose down

restart:
	docker-compose restart

logs:
	docker-compose logs -f

test:
	docker-compose exec backend pytest tests/ -v

migrate:
	docker-compose exec backend alembic upgrade head

clean:
	docker-compose down -v
	rm -rf data/
