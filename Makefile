COMPOSE = docker-compose -f infrastructure/docker-compose.yml
APP_SERVICE = app
RABBIT_SERVICE = rabbitmq

.PHONY: build up down shell deps cli test logs

build:
	$(COMPOSE) build $(APP_SERVICE)

up:
	$(COMPOSE) up -d $(RABBIT_SERVICE) $(APP_SERVICE)

down:
	$(COMPOSE) down

shell:
	$(COMPOSE) exec $(APP_SERVICE) bash -lc "cd /workspace && set -a; [ -f .env ] && source .env; set +a; exec bash"

deps:
	$(COMPOSE) exec $(APP_SERVICE) bash -lc "cd /workspace && poetry install -E openai"

cli:
	$(COMPOSE) exec $(APP_SERVICE) bash -lc 'cd /workspace && set -a; [ -f .env ] && source .env; set +a; if [[ "$$RABBITMQ_URL" == *localhost* || "$$RABBITMQ_URL" == *127.0.0.1* || "$$RABBITMQ_URL" == *::1* ]]; then export RABBITMQ_URL=amqp://user:password@rabbitmq:5672/; fi; for i in {1..30}; do code=$$(curl -s -o /dev/null -w "%{http_code}" http://rabbitmq:15672/api/overview || true); if [[ "$$code" == "200" || "$$code" == "401" ]]; then ready=1; break; fi; sleep 1; done; if [[ -z "$$ready" ]]; then echo "RabbitMQ not ready at rabbitmq:15672"; exit 1; fi; PYTHONPATH=. poetry run python3 apps/cli/cli.py --timeout 120'

test:
	$(COMPOSE) exec $(APP_SERVICE) bash -lc "cd /workspace && poetry run pytest -q"

logs:
	$(COMPOSE) logs -f $(RABBIT_SERVICE)
