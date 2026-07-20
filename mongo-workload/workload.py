#!/usr/bin/env python3
import os, time, random, threading, logging
import pymongo

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
log = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI", "mongodb://admin:demo1234@mongodb:27017")

def _bool(k): return os.getenv(k, "false").lower() == "true"

SLOW_QUERIES  = _bool("MONGO_WORKLOAD_SLOW_QUERIES")
COMMANDS      = _bool("MONGO_WORKLOAD_COMMANDS")
AUTH_FAILURES = _bool("MONGO_WORKLOAD_AUTH_FAILURES")


def connect(uri, retries=15):
    for _ in range(retries):
        try:
            c = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000)
            c.admin.command("ping")
            log.info("Connected to MongoDB")
            return c
        except Exception as e:
            log.warning(f"Waiting for MongoDB… ({e})")
            time.sleep(3)
    raise RuntimeError("Could not connect to MongoDB after retries")


# ── Workload: slow queries ────────────────────────────────────────────────────
# Gera: componente QUERY com slow op entries
# Como: define slowOpThresholdMs=0 (loga TUDO) e roda full collection scans

def workload_slow_queries(client, stop):
    db = client.demo_slow
    client.admin.command("setParameter", 1, slowOpThresholdMs=0)
    client.admin.command("setLogLevel", 1, component="query")

    db.products.drop()
    db.products.insert_many([
        {"name": f"product_{i}",
         "price": round(random.uniform(1, 1000), 2),
         "category": random.choice(["electronics", "clothing", "food", "sports"])}
        for i in range(2000)
    ])
    log.info("[slow_queries] seeded 2000 docs — logging all queries (threshold=0ms)")

    while not stop.is_set():
        list(db.products.find({"price": {"$gt": random.uniform(1, 999)}}))
        list(db.products.find({"category": random.choice(["electronics", "clothing", "food", "sports"])}))
        list(db.products.find({"name": {"$regex": f"product_{random.randint(1, 2000)}"}}))
        time.sleep(2)


# ── Workload: commands ────────────────────────────────────────────────────────
# Gera: componente COMMAND com insert/find/update/delete
# Como: verbosity=1 no componente command + operações CRUD contínuas

def workload_commands(client, stop):
    db = client.demo_commands
    client.admin.command("setLogLevel", 1, component="command")
    log.info("[commands] COMMAND verbosity=1 — logging all CRUD operations")

    i = 0
    while not stop.is_set():
        uid = f"user_{random.randint(1, 50)}"
        db.events.insert_one({
            "type": random.choice(["login", "purchase", "view", "logout"]),
            "user": uid, "ts": time.time(), "seq": i,
        })
        db.events.find_one({"user": uid})
        db.users.update_one({"_id": uid}, {"$inc": {"visits": 1}}, upsert=True)
        if random.random() < 0.1:
            db.events.delete_many({"seq": {"$lt": i - 100}})
        i += 1
        time.sleep(1)


# ── Workload: auth failures ───────────────────────────────────────────────────
# Gera: componente ACCESS com "Authentication failed" entries
# Como: tentativas de conexão com senha errada a cada 5s

def workload_auth_failures(stop):
    bad_uri = MONGO_URI.replace(":demo1234@", ":wrongpassword@")
    log.info("[auth_failures] generating AUTH failure events every 5s")
    while not stop.is_set():
        try:
            c = pymongo.MongoClient(bad_uri, serverSelectionTimeoutMS=2000)
            c.admin.command("ping")
        except Exception:
            pass
        time.sleep(5)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    active = {
        "slow_queries":  SLOW_QUERIES,
        "commands":      COMMANDS,
        "auth_failures": AUTH_FAILURES,
    }
    enabled = [k for k, v in active.items() if v]

    if not enabled:
        log.info("No workloads enabled — set MONGO_WORKLOAD_* flags and restart.")
        log.info("  MONGO_WORKLOAD_SLOW_QUERIES=true   → slow query log entries (QUERY component)")
        log.info("  MONGO_WORKLOAD_COMMANDS=true       → CRUD operation logs (COMMAND component)")
        log.info("  MONGO_WORKLOAD_AUTH_FAILURES=true  → auth failure events (ACCESS component)")
        while True:
            time.sleep(60)

    log.info(f"Active workloads: {', '.join(enabled)}")

    client = connect(MONGO_URI) if (SLOW_QUERIES or COMMANDS) else None
    stop   = threading.Event()
    threads = []

    if SLOW_QUERIES:
        t = threading.Thread(target=workload_slow_queries, args=(client, stop), daemon=True, name="slow_queries")
        t.start(); threads.append(t)
    if COMMANDS:
        t = threading.Thread(target=workload_commands, args=(client, stop), daemon=True, name="commands")
        t.start(); threads.append(t)
    if AUTH_FAILURES:
        t = threading.Thread(target=workload_auth_failures, args=(stop,), daemon=True, name="auth_failures")
        t.start(); threads.append(t)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        for t in threads:
            t.join(timeout=5)


if __name__ == "__main__":
    main()
