.PHONY: up down build test clean

up:
	docker compose up --build -d

down:
	docker compose down

build:
	docker compose build

test:
	cd backend && pytest tests -v

clean:
	docker compose down -v
