from flask import Flask, render_template, jsonify, request
import os
import re
import glob
import yaml
import docker

app = Flask(__name__)

ENV_FILE      = os.getenv('ENV_FILE',      '/config/.env')
SCENARIOS_DIR = os.getenv('SCENARIOS_DIR', '/scenarios')
GENERATOR_CTR = os.getenv('GENERATOR_CONTAINER', 'data-gen-generator-1')
COMPOSE_PRJ   = os.getenv('COMPOSE_PROJECT',     'data-gen')

BACKEND_SERVICES = {
    'ENABLE_PROMETHEUS': 'prometheus',
    'ENABLE_LOKI':       'loki',
    'ENABLE_TEMPO':      'tempo',
    'ENABLE_GRAFANA':    'grafana',
    'ENABLE_SELFMON':    'selfmon',
    'ENABLE_MONGODB':    'mongodb',
}
SIGNAL_KEYS  = {'ENABLE_LOGS', 'ENABLE_METRICS', 'ENABLE_TRACES'}
BACKEND_KEYS = set(BACKEND_SERVICES.keys())


# ── .env helpers ──────────────────────────────────────────────────────────────

def read_env() -> dict:
    env = {}
    try:
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env


def write_env_var(key: str, value: str):
    try:
        with open(ENV_FILE) as f:
            content = f.read()
    except FileNotFoundError:
        content = ''
    pattern = rf'^{re.escape(key)}=.*$'
    if re.search(pattern, content, re.MULTILINE):
        content = re.sub(pattern, f'{key}={value}', content, flags=re.MULTILINE)
    else:
        content = content.rstrip('\n') + f'\n{key}={value}\n'
    with open(ENV_FILE, 'w') as f:
        f.write(content)


# ── Scenario helpers ──────────────────────────────────────────────────────────

def get_scenarios() -> list:
    paths = sorted(
        glob.glob(f'{SCENARIOS_DIR}/*.yaml') +
        glob.glob(f'{SCENARIOS_DIR}/*.yaml.disabled')
    )
    seen = {}
    for path in paths:
        base    = os.path.basename(path)
        enabled = base.endswith('.yaml')
        stem    = base.removesuffix('.yaml.disabled').removesuffix('.yaml')
        if stem in seen:
            continue
        try:
            with open(path) as f:
                cfg = yaml.safe_load(f)
            sc_type      = cfg.get('type', 'logs')
            description  = cfg.get('description', '')
            rate         = cfg.get('rate') or cfg.get('export_interval')
            service_name = (cfg.get('service') or {}).get('name', '')
        except Exception:
            sc_type = description = rate = service_name = None
        seen[stem] = {
            'file':         stem,
            'type':         sc_type or 'logs',
            'description':  description or '',
            'rate':         rate,
            'service_name': service_name or '',
            'enabled':      enabled,
        }
    return list(seen.values())


# ── Docker helpers ────────────────────────────────────────────────────────────

def _docker():
    return docker.DockerClient(base_url='unix://var/run/docker.sock')


def restart_generator() -> dict:
    try:
        c = _docker().containers.get(GENERATOR_CTR)
        c.restart(timeout=5)
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def toggle_backend(service: str, enable: bool) -> dict:
    name = f'{COMPOSE_PRJ}-{service}-1'
    try:
        c = _docker().containers.get(name)
        if enable:
            c.start()
        else:
            c.stop(timeout=5)
        return {'ok': True}
    except docker.errors.NotFound:
        if enable:
            return {'ok': False, 'error': f'Container {name} não encontrado. Execute make start com {service} habilitado.'}
        return {'ok': True}
    except Exception as e:
        return {'ok': False, 'error': str(e)}


def container_status(service: str) -> str:
    try:
        c = _docker().containers.get(f'{COMPOSE_PRJ}-{service}-1')
        return c.status
    except docker.errors.NotFound:
        return 'not_found'
    except Exception:
        return 'unknown'


def generator_status() -> str:
    try:
        return _docker().containers.get(GENERATOR_CTR).status
    except Exception:
        return 'unknown'


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/state')
def state():
    env = read_env()

    def benv(key, default='false'):
        return env.get(key, default).lower() == 'true'

    return jsonify({
        'generator_status': generator_status(),
        'signals': {k: benv(k, 'true') for k in sorted(SIGNAL_KEYS)},
        'backends': {
            k: {'enabled': benv(k, 'false'), 'container_status': container_status(svc)}
            for k, svc in BACKEND_SERVICES.items()
        },
        'scenarios': get_scenarios(),
    })


@app.route('/api/toggle/env', methods=['POST'])
def toggle_env():
    data  = request.get_json()
    key   = data.get('key', '')
    value = 'true' if data.get('value') else 'false'

    if key not in (SIGNAL_KEYS | BACKEND_KEYS):
        return jsonify({'ok': False, 'error': 'chave inválida'}), 400

    write_env_var(key, value)

    if key in SIGNAL_KEYS:
        result = restart_generator()
        return jsonify({**result, 'restarted': result['ok']})

    svc    = BACKEND_SERVICES[key]
    result = toggle_backend(svc, value == 'true')
    return jsonify({**result, 'restarted': False})


@app.route('/api/toggle/scenario', methods=['POST'])
def toggle_scenario():
    data   = request.get_json()
    name   = data.get('name', '')
    enable = bool(data.get('value'))

    if not re.match(r'^[\w-]+$', name):
        return jsonify({'ok': False, 'error': 'nome inválido'}), 400

    yaml_path     = f'{SCENARIOS_DIR}/{name}.yaml'
    disabled_path = f'{SCENARIOS_DIR}/{name}.yaml.disabled'

    try:
        if enable and os.path.exists(disabled_path):
            os.rename(disabled_path, yaml_path)
        elif not enable and os.path.exists(yaml_path):
            os.rename(yaml_path, disabled_path)
        result = restart_generator()
        return jsonify({**result, 'restarted': result['ok']})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
