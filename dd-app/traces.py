import os
import time
import random
import logging
from ddtrace import tracer

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
log = logging.getLogger(__name__)

ENABLED = os.getenv('DD_TRACES_APP', 'false').lower() == 'true'

SCENARIOS = [
    ('checkout-service', 'POST /checkout',  0.08),
    ('user-service',     'GET /profile',    0.02),
    ('catalog-service',  'GET /products',   0.01),
    ('order-service',    'POST /orders',    0.05),
    ('payment-service',  'POST /pay',       0.12),
]

DB_STATEMENTS = [
    'SELECT * FROM users WHERE id = ?',
    'INSERT INTO orders (user_id, total) VALUES (?, ?)',
    'UPDATE inventory SET quantity = quantity - 1 WHERE product_id = ?',
    'SELECT p.* FROM products p JOIN categories c ON p.cat_id = c.id LIMIT 20',
]


def db_span(op='db.query', error_rate=0.02):
    with tracer.trace(op, service='postgresql') as s:
        s.set_tag('db.type', 'postgresql')
        s.set_tag('db.statement', random.choice(DB_STATEMENTS))
        if random.random() < error_rate:
            s.error = 1
            s.set_tag('error.message', 'connection timeout after 30s')
        time.sleep(random.uniform(0.005, 0.08))


def cache_span():
    with tracer.trace('cache.get', service='redis') as s:
        s.set_tag('cache.key', f'session:{random.randint(10000, 99999)}')
        s.set_tag('cache.hit', str(random.random() > 0.3))
        time.sleep(random.uniform(0.001, 0.005))


def run_scenario(service, resource, error_rate):
    method, path = resource.split(' ', 1)
    with tracer.trace('web.request', service=service, resource=resource) as s:
        s.set_tag('http.method', method)
        s.set_tag('http.url', path)
        s.set_tag('user.id', str(random.randint(1000, 9999)))

        if random.random() > 0.3:
            cache_span()

        db_span()

        if random.random() > 0.6:
            db_span('db.query.secondary')

        status = 500 if random.random() < error_rate else 200
        s.set_tag('http.status_code', str(status))
        if status == 500:
            s.error = 1
            s.set_tag('error.message', 'Internal Server Error')

        time.sleep(random.uniform(0.01, 0.05))


if not ENABLED:
    log.info('DD_TRACES_APP=false — idle, aguardando ativação do toggle')
    while True:
        time.sleep(30)

agent_host = os.getenv('DD_AGENT_HOST', 'datadog')
agent_port = os.getenv('DD_TRACE_AGENT_PORT', '8126')
log.info('Trace generator iniciado → %s:%s', agent_host, agent_port)

while True:
    scenario = random.choice(SCENARIOS)
    try:
        run_scenario(*scenario)
    except Exception as e:
        log.warning('erro ao gerar trace: %s', e)
    time.sleep(random.uniform(0.5, 2.0))
