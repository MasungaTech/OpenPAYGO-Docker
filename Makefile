.PHONY: build up up_daemon down test

IMAGE_NAME := openpaygo-docker
CONTAINER_NAME := openpaygo-docker

build:
	docker build -t $(IMAGE_NAME) .

up:
	@if [ -d openpaygo.db ]; then \
		echo "Error: openpaygo.db exists as a directory. Removing it..."; \
		rm -rf openpaygo.db; \
	fi
	@touch openpaygo.db 2>/dev/null || true
	@if [ -f .env ]; then \
		docker run --rm -p 5001:8000 -v $(PWD)/openpaygo.db:/app/openpaygo.db --env-file .env --name $(CONTAINER_NAME) $(IMAGE_NAME); \
	else \
		echo "Warning: .env file not found. Copy example.env to .env and configure your environment variables."; \
		docker run --rm -p 5001:8000 -v $(PWD)/openpaygo.db:/app/openpaygo.db --name $(CONTAINER_NAME) $(IMAGE_NAME); \
	fi

up_daemon:
	@if [ -d openpaygo.db ]; then \
		echo "Error: openpaygo.db exists as a directory. Removing it..."; \
		rm -rf openpaygo.db; \
	fi
	@touch openpaygo.db 2>/dev/null || true
	@if [ -f .env ]; then \
		docker run -d -p 5001:8000 -v $(PWD)/openpaygo.db:/app/openpaygo.db --env-file .env --name $(CONTAINER_NAME) $(IMAGE_NAME); \
	else \
		echo "Warning: .env file not found. Copy example.env to .env and configure your environment variables."; \
		docker run -d -p 5001:8000 -v $(PWD)/openpaygo.db:/app/openpaygo.db --name $(CONTAINER_NAME) $(IMAGE_NAME); \
	fi

down:
	@docker stop $(CONTAINER_NAME) 2>/dev/null || true
	@docker rm $(CONTAINER_NAME) 2>/dev/null || true

test:
	docker run --rm -e SQLITE_FILE=/tmp/test_openpaygo.db $(IMAGE_NAME) pytest tests/

