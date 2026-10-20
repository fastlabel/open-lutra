.PHONY: build build-backend build-frontend push release deploy status console provision image-tag lint

# One key of .env. Keys are read one by one: including the whole .env would let its other keys
# (THING_GROUP, ...) override what the caller passes in the environment, such as the group the console
# deploys to. The SSO portal quotes the values.
dotenv = $(patsubst "%",%,$(shell sed -n 's/^$(1)=//p' .env 2>/dev/null | tail -n 1))

REGISTRY ?= local
# One tag for both images, derived from the last commit that changed what goes into them, so a commit
# that touches only the rest of this example needs no new push. Paths are relative to the repository root.
IMAGE_SOURCES = Dockerfile .dockerignore .env.example backend config frontend examples/greengrass/docker
IMAGE_COMMIT = $(shell git -C ../.. log -1 --format=%H -- $(IMAGE_SOURCES))
IMAGE_TAG ?= $(shell git -C ../.. describe --tags --always $(IMAGE_COMMIT))
PLATFORM ?= linux/amd64
COMPONENT_NAME ?= $(or $(call dotenv,COMPONENT_NAME),com.example.OpenLutra)
COMPONENT_PUBLISHER ?= $(or $(call dotenv,COMPONENT_PUBLISHER),Example)
STATUS_COMPONENT_NAME ?= $(COMPONENT_NAME)Status
LOG_MANAGER_VERSION ?= 2.3.14
CONSOLE_PORT ?= 8800

# AWS credentials. With AWS_VAULT_PROFILE (make deploy AWS_VAULT_PROFILE=x), the commands run under
# aws-vault; inside `aws-vault exec` its credentials are used as they are; otherwise an IAM user's
# keys in .env (see .env.example).
ifeq ($(AWS_VAULT)$(AWS_VAULT_PROFILE),)
dotenv_vars := $(foreach v,AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_REGION,$(if $(call dotenv,$(v)),$(v)))
ifneq ($(dotenv_vars),)
$(foreach v,$(dotenv_vars),$(eval $(v) := $(call dotenv,$(v))))
export $(dotenv_vars)
# boto3 reads only AWS_DEFAULT_REGION.
ifneq ($(filter AWS_REGION,$(dotenv_vars)),)
export AWS_DEFAULT_REGION ?= $(AWS_REGION)
endif
endif
endif
AWS_VAULT_EXEC = $(if $(AWS_VAULT_PROFILE),$(if $(AWS_VAULT),,aws-vault exec $(1) $(AWS_VAULT_PROFILE) --))

GREENGRASS_ENV = COMPONENT_NAME=$(COMPONENT_NAME) STATUS_COMPONENT_NAME=$(STATUS_COMPONENT_NAME) COMPONENT_PUBLISHER=$(COMPONENT_PUBLISHER) \
	LOG_MANAGER_VERSION=$(LOG_MANAGER_VERSION) COMPONENT_VERSION=$(COMPONENT_VERSION) IMAGE_TAG=$(IMAGE_TAG) PLATFORM=$(PLATFORM)

build: build-backend build-frontend

build-backend:
	docker build --platform $(PLATFORM) -t $(REGISTRY)/open-lutra-backend:$(IMAGE_TAG) ../..

build-frontend:
	docker build --platform $(PLATFORM) -f docker/frontend.Dockerfile -t $(REGISTRY)/open-lutra-frontend:$(IMAGE_TAG) ../..

push: REGISTRY = $(shell scripts/infra-output.sh ECR_REGISTRY registry)
push: build
	$(call AWS_VAULT_EXEC) aws ecr get-login-password | docker login --username AWS --password-stdin $(REGISTRY)
	docker push $(REGISTRY)/open-lutra-backend:$(IMAGE_TAG)
	docker push $(REGISTRY)/open-lutra-frontend:$(IMAGE_TAG)

release:
	$(call AWS_VAULT_EXEC) env $(GREENGRASS_ENV) greengrass/release.sh

deploy:
	$(call AWS_VAULT_EXEC) env $(GREENGRASS_ENV) greengrass/deploy.sh

status:
	$(call AWS_VAULT_EXEC) env $(GREENGRASS_ENV) greengrass/status.sh

# Under aws-vault it runs with --server, which keeps refreshing the credentials while the console is open.
# The shared AWS files are hidden because a [default] profile there would take precedence over the server.
console:
	@test -n "$(AWS_VAULT_PROFILE)$(AWS_VAULT)$(AWS_ACCESS_KEY_ID)" || { echo "put an IAM user's keys in .env (see .env.example), or pass AWS_VAULT_PROFILE=<aws-vault profile>" >&2; exit 1; }
	$(call AWS_VAULT_EXEC,--server) env -u AWS_PROFILE AWS_SHARED_CREDENTIALS_FILE=/dev/null AWS_CONFIG_FILE=/dev/null \
		COMPONENT_NAME=$(COMPONENT_NAME) uv run --project console uvicorn app.main:app --app-dir console --port $(CONSOLE_PORT)

provision:
	$(call AWS_VAULT_EXEC) env THING_NAME=$(THING_NAME) device/provision.sh

# The console shows the tag and the commit it comes from.
image-tag:
	@echo $(IMAGE_TAG)
	@git -C ../.. log -1 --format='%h %s' $(IMAGE_COMMIT)

lint:
	uv run --project console ruff check console
	uv run --project console ruff format --check console
	terraform fmt -check -recursive infra
