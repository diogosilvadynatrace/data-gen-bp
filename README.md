# BindPlane Demo — Data Generator

Solução local para geração de métricas, logs e traces sintéticos com dados realistas (incluindo PII), permitindo demonstrar as capacidades do **BindPlane OP**: mascaramento de dados e redução de custos de telemetria.

---

## Como funciona

O projeto tem três camadas:

```
┌─────────────────────────────────────────────────────────────────┐
│  Generator (Python + OTel SDK)                                  │
│  Lê os arquivos YAML de scenarios/ e envia telemetria via OTLP  │
└────────────────────────┬────────────────────────────────────────┘
                         │ OTLP gRPC :4317
          ┌──────────────┴──────────────┐
          │                             │
    MODO BINDPLANE               MODO STANDALONE
    (perfil bindplane)           (perfil standalone)
          │                             │
 ┌────────▼────────┐          ┌─────────▼────────┐
 │ bindplane-agent │          │     otelcol       │
 │                 │          │  (raw.yaml ou     │
 │ Pipeline gerenc.│          │   bindplane-      │
 │ pela UI do      │          │   style.yaml)     │
 │ BindPlane OP    │          └─────────┬─────────┘
 └────────┬────────┘                    │
          │                             │
          └──────────────┬──────────────┘
                         │
┌────────────────────────▼────────────────────────────────────────┐
│  Backends locais (disponíveis nos dois modos)                    │
│  Prometheus · Loki · Tempo · Grafana (http://localhost:3000)    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Pré-requisitos

- Docker Desktop instalado e rodando
- `make` disponível (já vem no macOS)
- Conta no [BindPlane OP](https://app.bindplane.com) *(somente para o modo BindPlane)*

---

## Cenários de dados gerados

| Arquivo | Tipo | O que gera |
|---|---|---|
| `web_logs.yaml` | Logs | Logs de acesso web com email, IP, cartão de crédito |
| `financial_logs.yaml` | Logs | Transações financeiras com SSN, cartão, telefone |
| `iis_logs.yaml` | Logs | Logs de acesso IIS (W3C) com email, IP, user agent |
| `windows_event_logs.yaml` | Logs | Windows Event Log (Security, System, Application) com PII |
| `k8s_metrics.yaml` | Métricas | Métricas de containers Kubernetes com alta cardinalidade (label `pod`) |
| `checkout_traces.yaml` | Traces | Fluxo de checkout e-commerce com PII nos atributos dos spans |

Para adicionar um novo cenário: crie um arquivo `.yaml` em `generator/scenarios/` e execute `make restart-generator`.

### Habilitar/desabilitar sinais

Controle quais tipos de sinal são gerados via `.env`:

```env
ENABLE_LOGS=true
ENABLE_METRICS=true
ENABLE_TRACES=false   # desabilita geração de traces
```

Após alterar, aplique com:
```bash
make restart-generator
```

Cenários cujo tipo estiver desabilitado são ignorados na inicialização — nenhum dado daquele sinal é enviado ao agente. Para conferir o estado atual:

```bash
make list-scenarios
# Exemplo com ENABLE_TRACES=false:
#   [OFF]  checkout_traces   [traces]   E-commerce checkout flow...
#   [ON ]  financial_logs    [logs  ]   Financial/banking logs...
```

---

## Modo 1 — BindPlane UI (demo principal)

O pipeline completo é configurado e gerenciado pela interface do BindPlane. O agente local recebe a configuração remotamente via protocolo OpAMP — nenhum YAML de pipeline é necessário localmente.

### 1.1 Configuração inicial

**Crie o arquivo `.env`:**
```bash
make setup
```

**Preencha a chave do BindPlane em `.env`:**
```
BINDPLANE_SECRET_KEY=sua-chave-aqui
```
> Onde encontrar: [app.bindplane.com](https://app.bindplane.com) → **Agents** → **Install Agent** → **Docker** → copie o valor de `SECRET_KEY` do snippet.

**Inicie os serviços:**
```bash
make start
```

O agente `data-gen-demo-agent` aparece automaticamente na seção **Agents** do console BindPlane em alguns segundos com status verde.

---

### 1.2 Configurar Source no BindPlane UI

O gerador envia dados via OTLP gRPC para o agente. Configure a source assim:

1. No BindPlane, acesse **Sources** → **Add Source**
2. Selecione o tipo **`OTLP`**
3. Preencha os campos:

| Campo | Valor |
|---|---|
| Name | `otlp-data-gen` (ou qualquer nome) |
| GRPC Endpoint | `0.0.0.0:4317` |
| HTTP Endpoint | `0.0.0.0:4318` |

4. Clique em **Save**

> O gerador já está enviando para `bindplane-agent:4317`. Assim que a source for associada a um pipeline, os dados começam a fluir.

---

### 1.3 Configurar Destinations no BindPlane UI

#### Loki (logs)

1. Acesse **Destinations** → **Add Destination**
2. Selecione o tipo **`Loki`**
3. Preencha:

| Campo | Valor |
|---|---|
| Name | `loki-local` |
| Endpoint | `http://loki:3100/otlp` |

> **Atenção:** o endpoint deve ser exatamente `http://loki:3100/otlp`. O BindPlane adiciona `/v1/logs` automaticamente, formando o path completo `http://loki:3100/otlp/v1/logs` — que é o endpoint OTLP nativo do Loki 3.x. Usar apenas `http://loki:3100` resulta em HTTP 404 porque o Loki não expõe OTLP em `/v1/logs`.

4. Clique em **Save**

---

#### Prometheus (métricas)

O Prometheus exposto neste projeto aceita dados via **Remote Write** (push). Não use o tipo "Prometheus" — ele tenta expor um endpoint de scrape, o que conflita com a rede Docker.

1. Acesse **Destinations** → **Add Destination**
2. Selecione o tipo **`Prometheus Remote Write`**
3. Preencha:

| Campo | Valor |
|---|---|
| Name | `prometheus-local` |
| Endpoint | `http://prometheus:9090/api/v1/write` |

> **Atenção:** use o path completo `/api/v1/write`. Apenas `http://prometheus:9090` não funciona para remote write.

4. Clique em **Save**

---

#### Tempo (traces)

1. Acesse **Destinations** → **Add Destination**
2. Selecione o tipo **`OTLP`**
3. Preencha:

| Campo | Valor |
|---|---|
| Name | `tempo-local` |
| Protocol | `gRPC` |
| Endpoint | `tempo:4317` |
| TLS | desativado (insecure) |

> **Atenção:** para gRPC **não** adicione `http://` — o endpoint gRPC usa apenas `host:porta`. O prefixo `http://` é necessário somente para HTTP.

4. Clique em **Save**

---

#### Dynatrace (métricas, logs e traces)

O Dynatrace aceita telemetria via OTLP HTTP. Você precisará de um API Token com os escopos corretos.

**Pré-requisito — criar o API Token no Dynatrace:**
1. Acesse seu tenant Dynatrace → **Access Tokens** → **Generate new token**
2. Adicione os escopos:
   - `metrics.ingest`
   - `logs.ingest`
   - `openTelemetryTrace.ingest`
3. Copie o token gerado (`dt0c01.xxx...`)

**Configurar o destination no BindPlane:**

Use o tipo **`OTLP HTTP`** — ele funciona para todos os ambientes Dynatrace (SaaS, Sprint, Managed) sem risco de URL malformada.

1. Acesse **Destinations** → **Add Destination**
2. Selecione o tipo **`OTLP HTTP`**
3. Preencha:

| Campo | Valor |
|---|---|
| Name | `dynatrace` |
| Endpoint | `https://{seu-tenant}/api/v2/otlp` *(ver tabela abaixo)* |
| Header — Name | `Authorization` |
| Header — Value | `Api-Token dt0c01.xxxxxx...` |

**Endpoint por tipo de ambiente:**

| Tipo | Endpoint |
|---|---|
| SaaS clássico | `https://{env-id}.live.dynatrace.com/api/v2/otlp` |
| Sprint / DynatraceLabs | `https://{hostname}.sprint.dynatracelabs.com/api/v2/otlp` |
| Managed (self-hosted) | `https://{activegate-host}:9999/e/{env-id}/api/v2/otlp` |

> **Importante:** não use o tipo "Dynatrace" do BindPlane para ambientes Sprint ou Managed — ele constrói o URL assumindo SaaS (`.live.dynatrace.com`) e gera endpoint inválido.

#### Diferença entre as duas APIs de ingestão de logs do Dynatrace

O Dynatrace oferece dois endpoints distintos para ingestão de logs:

| | `/api/v2/otlp/v1/logs` | `/api/v2/logs/ingest` |
|---|---|---|
| **Formato** | Protobuf binário (OpenTelemetry Protocol) | JSON proprietário Dynatrace |
| **Content-Type** | `application/x-protobuf` | `application/json` |
| **Padrão** | Aberto (OpenTelemetry) | Proprietário |
| **Campos** | `body`, `severity_number`, `resource.attributes`, `trace_id`, `span_id` | `content` (obrigatório) + atributos livres flat |
| **Correlação com traces** | Nativa (trace_id/span_id no protocolo) | Não |
| **Quem usa** | BindPlane, otelcol, SDKs OTel | Scripts, curl, Fluentd/Logstash com plugin Dynatrace |

**Para o BindPlane, use sempre `/api/v2/otlp`** — o exporter `OTLP HTTP` envia protobuf e não é compatível com a API clássica `/api/v2/logs/ingest` (que retornaria `415 Unsupported Media Type`).

4. Clique em **Save**

---

### 1.4 Criar e implantar o Pipeline

Com source e destinations criados, monte o pipeline:

1. Acesse **Pipelines** → **Add Pipeline**
2. Nomeie o pipeline (ex: `demo-pipeline`)
3. No editor visual:
   - Arraste a **Source** `otlp-data-gen` para o canvas
   - Arraste o(s) **Destination(s)** desejados
   - Conecte source → destination(s) com as setas
4. **(Opcional) Adicione Processors entre source e destination:**

| Processor | Para que serve |
|---|---|
| `Mask Sensitive Data` | Mascara emails, cartões, SSNs nos logs |
| `Remove Fields` | Remove label `pod` das métricas (reduz cardinalidade) |
| `Filter Logs` | Descarta logs DEBUG (reduz volume) |
| `Route by Type` | Envia logs → Loki, métricas → Prometheus, traces → Tempo |

> **Cobertura do preset "Credit Card" no BindPlane**
>
> O preset detecta números no formato das principais bandeiras ocidentais:
>
> | Bandeira | Prefixos | Dígitos |
> |---|---|---|
> | Visa | `4` | 13 ou 16 |
> | Mastercard | `51`–`55`, `2221`–`2720` | 16 |
> | Amex | `34`, `37` | 15 |
> | Discover | `6011`, `65` | 16 |
> | Diners | `300`–`305`, `36`, `38` | 14 |
>
> Bandeiras **não cobertas nativamente**: JCB (`2131`, `1800`, `3528`–`3589`), Maestro (`6304`, `6759`) e UnionPay (`62`).
> O gerador deste projeto sempre emite cartões no formato Visa de 16 dígitos (`XXXX-XXXX-XXXX-XXXX`) para garantir a detecção.

5. Clique em **Save & Deploy**
6. Selecione o agente `data-gen-demo-agent` → **Deploy**

Após o deploy, o agente reinicia o pipeline internamente. Para confirmar que funcionou:

```bash
make logs-agent
# Procure por: "OTEL Collector restarted" e "Everything is ready"
```

---

### 1.5 Parar

```bash
make stop
```

> O agente mantém a identidade entre `make stop` / `make start` — ele sempre reaparece no BindPlane como o mesmo agente (`data-gen-demo-agent`), sem duplicatas.

---

## Modo 2 — Standalone (sem BindPlane)

Útil para mostrar o "antes" — dados brutos sem processamento — e comparar com o "depois" aplicando as mesmas regras que o BindPlane aplicaria, mas via YAML local.

### Iniciar

```bash
make start-standalone
```

### Alternar entre raw e processed

```bash
make raw        # sem processamento — PII visível, alta cardinalidade, todos os logs
make processed  # mascaramento + redução de custo ativados
```

**O que o modo `processed` faz:**

| O quê | Antes | Depois |
|---|---|---|
| Emails nos logs | `joao@empresa.com` | `[EMAIL]` |
| Cartões de crédito | `4532 1234 5678 9012` | `[CARD]` |
| SSN | `123-45-6789` | `[SSN]` |
| Telefones | `(11) 99999-9999` | `[PHONE]` |
| Label `pod` nas métricas | 2.400+ séries | ~45 séries (−95%) |
| Métrica `container_network_*` | Presente | Removida |
| Logs DEBUG | Presentes | Descartados |

As regras estão definidas em `collector/bindplane-style.yaml` e são exatamente as mesmas que o BindPlane aplicaria via UI no modo 1.

### Parar

```bash
make stop
```

---

## Referência de comandos

```bash
make setup               # Cria .env a partir de .env.example (executar uma vez)

make start               # Modo BindPlane — agent + backends
make start-standalone    # Modo standalone — OTel Collector local + backends

make raw                 # [standalone] Pipeline sem processamento
make processed           # [standalone] Mascaramento + redução de custo

make stop                # Para todos os serviços
make clean               # Para e remove volumes (reseta estado do agente)

make restart-generator   # Reinicia gerador (carrega novos cenários)
make list-scenarios      # Lista cenários disponíveis

make logs                # Logs do gerador de dados
make logs-agent          # Logs do BindPlane agent
make logs-collector      # Logs do OTel Collector (modo standalone)
make status              # Status de todos os serviços
```

### MongoDB

```bash
# Subir MongoDB + workload
docker compose --profile mongodb up -d --build

# Ver path do arquivo de log (para configurar File Log source no BindPlane)
docker inspect data-gen-mongodb-1 --format '{{.LogPath}}'

# Acompanhar logs em tempo real
docker logs -f data-gen-mongodb-1

# Acompanhar workload (operações geradas)
docker logs -f data-gen-mongo-workload-1

# Ativar workloads — edite .env e reinicie o workload:
#   MONGO_WORKLOAD_SLOW_QUERIES=true    → componente QUERY
#   MONGO_WORKLOAD_COMMANDS=true        → componente COMMAND
#   MONGO_WORKLOAD_AUTH_FAILURES=true   → componente ACCESS
docker compose --profile mongodb up -d mongo-workload

# Conectar via mongosh
mongosh "mongodb://admin:demo1234@localhost:27017"

# Verificar verbosity atual
mongosh "mongodb://admin:demo1234@localhost:27017" --eval \
  "db.adminCommand({getParameter: 1, logLevel: 1})" --quiet
```

---

## URLs locais

| Serviço | URL |
|---|---|
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |
| Loki | http://localhost:3100 |
| Tempo | http://localhost:3200 |
| BindPlane UI | https://app.bindplane.com |

---

## Coleta de logs de containers Docker

O BindPlane Agent coleta logs de outros containers (ex: MongoDB) via **File Log source**, lendo os arquivos JSON que o Docker cria em:

```
/var/lib/docker/containers/<container-id>/<container-id>-json.log
```

Para obter o path do container desejado:

```bash
docker inspect <container-name> --format '{{.LogPath}}'
```

### Por que `user: root` + `cap_drop: ALL` + `cap_add: DAC_READ_SEARCH`

Os arquivos de log do Docker são de propriedade do `root` com permissão `640`. A imagem do BindPlane Agent roda por padrão como `uid=10005(otel)` — um usuário não-root.

No Linux, capabilities adicionadas via `cap_add` só se tornam **efetivas** quando o processo inicia como root. Para um processo não-root, ficam no bounding set mas nunca são ativadas. Por isso a combinação correta é:

```yaml
# docker-compose.yml — BindPlane Agent
user: root        # necessário para as capabilities serem efetivas
cap_drop:
  - ALL           # descarta TODAS as capabilities de root
cap_add:
  - DAC_READ_SEARCH  # restitui apenas: ler arquivos sem checar ownership
```

| Abordagem | Acesso concedido | Recomendado |
|---|---|---|
| `user: root` sozinho | Todos os ~40 privilégios de root | ❌ Excessivo |
| `privileged: true` | Acesso total ao kernel | ❌ Nunca usar |
| `cap_add` sem `user: root` | Capability no bounding set, **nunca efetiva** para não-root | ❌ Não funciona |
| `user: root` + `cap_drop: ALL` + `cap_add: DAC_READ_SEARCH` | Somente leitura de arquivos sem checar ownership | ✅ Mínimo necessário |

Esse padrão se aplica a qualquer coletor de logs em Docker (Fluent Bit, Vector, OTel Collector) que precise ler arquivos de log de outros containers no mesmo host.

---

## Troubleshooting

| Sintoma | Causa | Solução |
|---|---|---|
| Generator: `StatusCode.UNAVAILABLE` | Nenhum pipeline com OTLP source implantado no agente | Configure e faça deploy do pipeline no BindPlane UI |
| Generator: `StatusCode.UNIMPLEMENTED` | Pipeline ativo mas sem receiver para aquele tipo de sinal | Normal se o pipeline cobre apenas logs, por exemplo |
| Agente não aparece no BindPlane | `BINDPLANE_SECRET_KEY` incorreta ou agente não iniciou | Verifique com `make logs-agent` |
| Agente aparece como novo a cada restart | Volume não estava persistindo `/etc/otel` | Execute `make clean` e depois `make start` para recriar com a configuração correta |
| Loki: `HTTP Status Code 404` | Endpoint incompleto — falta `/otlp` | Corrigir no BindPlane UI: `http://loki:3100/otlp` |
| Loki: `unsupported protocol scheme` | Endpoint sem `http://` | Adicionar `http://`: usar `http://loki:3100/otlp` |
| Prometheus: `bind: cannot assign requested address` | Usando tipo "Prometheus" em vez de "Prometheus Remote Write" | Trocar o tipo do destination no BindPlane UI |
| Tempo: falha de conexão gRPC | Endpoint com `http://` para gRPC | Remover o prefixo: usar `tempo:4317` sem scheme |
| File Log não coleta logs de containers | Agente sem permissão para ler `/var/lib/docker/containers` | Confirmar `cap_add: [DAC_READ_SEARCH]` no agente e volume montado |

---

## Estrutura do projeto

```
data-gen/
├── generator/
│   ├── generator.py          # Script Python — lê cenários e envia OTLP
│   ├── requirements.txt
│   └── scenarios/            # ← adicione novos cenários aqui
│       ├── web_logs.yaml
│       ├── financial_logs.yaml
│       ├── k8s_metrics.yaml
│       └── checkout_traces.yaml
├── collector/
│   ├── raw.yaml              # Pipeline sem processamento (modo standalone)
│   └── bindplane-style.yaml  # Mascaramento + cost reduction (modo standalone)
├── monitoring/               # Configs de Prometheus, Tempo, Grafana
├── docker-compose.yml
├── Makefile
└── .env.example              # Template de credenciais
```
