.PHONY: help setup start start-standalone stop clean \
        raw processed restart-generator list-scenarios \
        logs logs-agent logs-collector status

SHELL := /bin/bash
GREEN  := \033[0;32m
YELLOW := \033[1;33m
CYAN   := \033[0;36m
RED    := \033[0;31m
RESET  := \033[0m

# Profiles de monitoramento opcionais: lidos do .env para o modo BindPlane.
# Standalone sempre sobe todos os backends locais.
_MON_PROFILES := $(shell \
  p=""; \
  grep -qs '^ENABLE_PROMETHEUS=true' .env 2>/dev/null && p="$$p --profile prometheus"; \
  grep -qs '^ENABLE_LOKI=true'       .env 2>/dev/null && p="$$p --profile loki"; \
  grep -qs '^ENABLE_TEMPO=true'      .env 2>/dev/null && p="$$p --profile tempo"; \
  grep -qs '^ENABLE_GRAFANA=true'    .env 2>/dev/null && p="$$p --profile grafana"; \
  printf '%s' "$$p" \
)
_ALL_MON := --profile prometheus --profile loki --profile tempo --profile grafana

# ────────────────────────────────────────────────────────────────────────────

help: ## Mostra este help
	@echo ""
	@echo "  BindPlane Demo — Data Generator"
	@echo ""
	@printf "  $(CYAN)%-28s$(RESET) %s\n" "Comando" "Descrição"
	@printf "  %-28s %s\n"               "-------" "---------"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-28s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# ── Setup inicial ─────────────────────────────────────────────────────────────

setup: ## Cria .env a partir de .env.example (executar uma vez)
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(GREEN)✓ .env criado$(RESET)"; \
		echo "  $(YELLOW)→ Preencha BINDPLANE_SECRET_KEY em .env antes de 'make start'$(RESET)"; \
		echo "    Onde encontrar: BindPlane Console → Agents → Install Agent → Docker"; \
	else \
		echo "$(CYAN)ℹ  .env já existe$(RESET)"; \
	fi

# ── Modo BindPlane (principal) ────────────────────────────────────────────────

start: setup ## Inicia com BindPlane Agent — pipeline gerenciado pela UI do BindPlane
	@mkdir -p bindplane-agent-data
	@# Na primeira execução (ou após make clean), extrai o config.yaml padrão da imagem
	@if [ ! -f bindplane-agent-data/config.yaml ]; then \
		echo "$(YELLOW)→ Extraindo config.yaml padrão da imagem do agente...$(RESET)"; \
		docker run --rm --entrypoint="" ghcr.io/observiq/bindplane-agent:latest \
			cat /etc/otel/config.yaml > bindplane-agent-data/config.yaml; \
	fi
	@# Proteção: manager.yaml sem config.yaml causa crash — limpa estado inconsistente
	@if [ -f bindplane-agent-data/manager.yaml ] && [ ! -f bindplane-agent-data/config.yaml ]; then \
		echo "$(YELLOW)⚠  Estado inconsistente detectado — removendo manager.yaml órfão$(RESET)"; \
		rm -f bindplane-agent-data/manager.yaml; \
	fi
	@if grep -q 'your-secret-key-here' .env 2>/dev/null; then \
		echo ""; \
		echo "$(RED)✗  BINDPLANE_SECRET_KEY não configurada$(RESET)"; \
		echo ""; \
		echo "   1. Acesse: BindPlane Console → Agents → Install Agent → Docker"; \
		echo "   2. Copie o valor de SECRET_KEY do snippet de instalação"; \
		echo "   3. Cole em .env: BINDPLANE_SECRET_KEY=<sua-chave>"; \
		echo ""; \
		exit 1; \
	fi
	@sed -i '' 's|^OTLP_ENDPOINT=.*|OTLP_ENDPOINT=bindplane-agent:4317|' .env
	docker compose --profile bindplane $(_MON_PROFILES) up -d --build
	@echo ""
	@echo "$(GREEN)✓ Demo rodando com BindPlane Agent!$(RESET)"
	@echo ""
	@echo "  $(CYAN)BindPlane UI$(RESET)   →  https://app.bindplane.com"
	@if grep -qs '^ENABLE_GRAFANA=true' .env 2>/dev/null; then \
		echo "  $(CYAN)Grafana$(RESET)        →  http://localhost:3000"; \
	fi
	@if grep -qs '^ENABLE_PROMETHEUS=true' .env 2>/dev/null; then \
		echo "  $(CYAN)Prometheus$(RESET)     →  http://localhost:9090"; \
	fi
	@if grep -qs '^ENABLE_TEMPO=true' .env 2>/dev/null; then \
		echo "  $(CYAN)Tempo$(RESET)          →  http://localhost:3200"; \
	fi
	@echo ""
	@echo "  Configure mascaramento e filtros diretamente na UI do BindPlane."
	@echo "  O agente '$(shell grep BINDPLANE_AGENT_NAME .env | cut -d= -f2)' deve aparecer em: Agents"
	@echo ""

# ── Modo standalone (sem BindPlane) ──────────────────────────────────────────

start-standalone: setup ## Inicia sem BindPlane — usa OTel Collector local com config YAML
	@test -f collector/active.yaml || cp collector/raw.yaml collector/active.yaml
	@grep -q '^OTLP_ENDPOINT=' .env || echo 'OTLP_ENDPOINT=otelcol:4317' >> .env
	@sed -i '' 's|^OTLP_ENDPOINT=.*|OTLP_ENDPOINT=otelcol:4317|' .env
	docker compose --profile standalone $(_ALL_MON) up -d --build
	@echo ""
	@echo "$(GREEN)✓ Demo rodando em modo standalone$(RESET)"
	@echo ""
	@echo "  $(CYAN)Grafana$(RESET)        →  http://localhost:3000"
	@echo "  $(CYAN)Prometheus$(RESET)     →  http://localhost:9090"
	@echo ""
	@echo "  $(YELLOW)make raw$(RESET)       → Sem processamento (PII visível, alta cardinalidade)"
	@echo "  $(YELLOW)make processed$(RESET) → Mascaramento + redução de custo ativados"
	@echo ""

raw: ## [standalone] Pipeline sem processamento — mostra dados brutos com PII
	cp collector/raw.yaml collector/active.yaml
	docker compose --profile standalone restart otelcol
	@echo "$(GREEN)✓ Modo RAW ativo — dados sem processamento$(RESET)"

processed: ## [standalone] Pipeline com mascaramento + redução de custo
	cp collector/bindplane-style.yaml collector/active.yaml
	docker compose --profile standalone restart otelcol
	@echo "$(GREEN)✓ Modo PROCESSED ativo:$(RESET)"
	@echo "   • Emails, cartões, SSNs, telefones mascarados nos logs"
	@echo "   • Label 'pod' (alta cardinalidade) removida das métricas"
	@echo "   • Métrica container_network_* filtrada"
	@echo "   • Logs DEBUG descartados"

# ── Stop / Clean ──────────────────────────────────────────────────────────────

stop: ## Para todos os serviços
	docker compose --profile bindplane --profile standalone $(_ALL_MON) down

clean: ## Para e remove volumes e estado do agente (agente reaparece como novo no BindPlane)
	docker compose --profile bindplane --profile standalone $(_ALL_MON) down -v
	rm -f collector/active.yaml
	rm -rf bindplane-agent-data/

# ── Generator ─────────────────────────────────────────────────────────────────

restart-generator: ## Reinicia o gerador (carrega novos arquivos de cenário)
	docker compose restart generator

list-scenarios: ## Lista cenários disponíveis
	docker compose exec generator python generator.py --list

# ── Logs / Status ─────────────────────────────────────────────────────────────

logs: ## Acompanha logs do gerador de dados
	docker compose logs -f generator

logs-agent: ## Acompanha logs do BindPlane Agent (modo bindplane)
	docker compose --profile bindplane logs -f bindplane-agent

logs-collector: ## Acompanha logs do OTel Collector (modo standalone)
	docker compose --profile standalone logs -f otelcol

status: ## Mostra status de todos os serviços
	docker compose --profile bindplane --profile standalone $(_ALL_MON) ps
