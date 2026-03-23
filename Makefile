.PHONY: help dev build up down logs test lint format migrate seed

help: ## Bu yardım mesajını göster
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Geliştirme ────────────────────────────────────
dev: ## Geliştirme ortamını başlat (hot-reload)
	docker compose -f docker-compose.dev.yml up

build: ## Tüm servisleri derle
	docker compose build

up: ## Prodüksiyon ortamını başlat
	docker compose up -d

down: ## Tüm servisleri durdur
	docker compose down

logs: ## Canlı logları izle
	docker compose logs -f backend

shell: ## Backend container'ına bağlan
	docker compose exec backend bash

# ── Database ──────────────────────────────────────
migrate: ## Alembic migration çalıştır
	docker compose exec backend alembic upgrade head

migrate-create: ## Yeni migration oluştur (MSG= ile mesaj ver)
	docker compose exec backend alembic revision --autogenerate -m "$(MSG)"

seed: ## Örnek veri yükle
	docker compose exec backend python scripts/seed_prompts.py

# ── Test ──────────────────────────────────────────
test: ## Tüm testleri çalıştır
	docker compose exec backend pytest tests/ -v --cov=app --cov-report=term-missing

test-unit: ## Sadece unit testleri
	docker compose exec backend pytest tests/unit/ -v

test-int: ## Sadece integration testleri
	docker compose exec backend pytest tests/integration/ -v

# ── Kod Kalitesi ──────────────────────────────────
lint: ## Kod kalitesi kontrol
	docker compose exec backend ruff check app/
	cd frontend && npx tsc --noEmit

format: ## Kodu otomatik formatla
	docker compose exec backend ruff format app/
	cd frontend && npx prettier --write src/

# ── Frontend ──────────────────────────────────────
fe-install: ## Frontend bağımlılıklarını kur
	cd frontend && npm install

fe-dev: ## Frontend geliştirme sunucusu
	cd frontend && npm run dev

fe-build: ## Frontend production derlemesi
	cd frontend && npm run build
