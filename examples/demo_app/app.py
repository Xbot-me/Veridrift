"""Deliberately problematic Flask application for Guardrail demonstration.

This application contains multiple production readiness issues that
Guardrail should detect through static analysis and runtime verification:

1. DB-001: Unbounded database queries (.all() without limit)
2. DB-002: N+1 query pattern (queries inside loops)
3. AMP-001: Tight polling interval (2 second sleep)
4. AMP-002: Retry without backoff
5. NET-001: Missing timeout on HTTP requests
6. NET-002: Unbounded retry loop
7. RES-001: Unclosed file handles
8. CFG-001: Debug mode enabled
9. CONC-001: Unbounded thread creation
"""

from flask import Flask, jsonify, request
import requests
import time
import threading
import sqlite3
import os

app = Flask(__name__)

# Simulated database connection
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")


def init_db():
    """Initialize SQLite database with schema and sample records if absent."""
    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, user_id INTEGER, amount REAL, status TEXT)")
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            [(f"User {i}", f"user{i}@example.com") for i in range(1, 101)],
        )
        cursor.executemany(
            "INSERT INTO orders (user_id, amount, status) VALUES (?, ?, ?)",
            [(i % 100 + 1, 19.99 * (i % 5 + 1), "completed") for i in range(1, 501)],
        )
        conn.commit()
    conn.close()


init_db()


def get_db():
    """Get database connection (simplified)."""
    conn = sqlite3.connect("app.db")
    return conn


@app.route("/")
@app.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "demo_app"})



# ─── DB-001: Unbounded query ────────────────────────────────────────────────
@app.route("/api/users")
def get_users():
    """Return all users without pagination — will fail at scale."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")  # DB-003: SELECT *
    users = cursor.fetchall()  # DB-001: No LIMIT
    conn.close()
    return jsonify(users)


# ─── DB-001 + DB-003: Another unbounded query ──────────────────────────────
@app.route("/api/orders")
def get_orders():
    """Return all orders — memory bomb on large datasets."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM orders")
    orders = cursor.fetchall()
    conn.close()
    return jsonify(orders)


# ─── DB-002: N+1 query pattern ─────────────────────────────────────────────
@app.route("/api/users/details")
def get_user_details():
    """Classic N+1: one query for users, then one per user for orders."""
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name FROM users")
    users = cursor.fetchall()

    results = []
    for user in users:
        # DB-002: Query inside loop!
        cursor.execute("SELECT * FROM orders WHERE user_id = ?", (user[0],))
        orders = cursor.fetchall()
        results.append({"user": user[1], "orders": len(orders)})

    conn.close()
    return jsonify(results)


# ─── DB-004: Large OFFSET pagination ───────────────────────────────────────
@app.route("/api/orders/page")
def get_orders_paginated():
    """Pagination using OFFSET — degrades at large page numbers."""
    page = int(request.args.get("page", 1))
    per_page = 50
    offset = (page - 1) * per_page

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT * FROM orders LIMIT {per_page} OFFSET {offset}"
    )
    orders = cursor.fetchall()
    conn.close()
    return jsonify(orders)


# ─── NET-001: Missing timeout on HTTP request ──────────────────────────────
@app.route("/api/external")
def call_external():
    """Call external API without timeout — will hang indefinitely."""
    result = requests.get("http://api.example.com/data")
    return jsonify(result.json())


# ─── NET-001 + AMP-003: Nested HTTP requests ──────────────────────────────
@app.route("/api/aggregate")
def aggregate_data():
    """Fan-out: calls multiple external APIs without timeout."""
    sources = [
        "http://api.example.com/users",
        "http://api.example.com/orders",
        "http://api.example.com/products",
        "http://api.example.com/inventory",
    ]
    results = []
    for url in sources:
        # NET-001: No timeout, AMP-003: HTTP in loop
        response = requests.get(url)
        results.append(response.json())
    return jsonify(results)


# ─── AMP-001: Tight polling interval ───────────────────────────────────────
def poll_status():
    """Poll external API every 2 seconds — traffic amplification risk."""
    while True:
        try:
            response = requests.get("http://api.example.com/status")
            process_status(response.json())
        except Exception:
            pass
        time.sleep(2)  # AMP-001: 2 second interval


def process_status(data):
    """Process status data."""
    pass


# ─── AMP-002: Retry without backoff ────────────────────────────────────────
def fetch_with_retry(url):
    """Retry without exponential backoff — will amplify failures."""
    max_retries = 10
    for attempt in range(max_retries):
        try:
            response = requests.get(url)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        time.sleep(1)  # Fixed 1s delay, no backoff
    return None


# ─── NET-002: Unbounded retry ──────────────────────────────────────────────
def fetch_critical_data(url):
    """Retry forever — will never give up."""
    while True:
        try:
            response = requests.get(url)
            return response.json()
        except Exception:
            time.sleep(1)


# ─── RES-001: Unclosed file handle ─────────────────────────────────────────
@app.route("/api/logs")
def get_logs():
    """Read logs without context manager — file descriptor leak."""
    f = open("/var/log/app.log", "r")
    content = f.read()
    # Missing f.close() — leak!
    return jsonify({"logs": content})


# ─── CONC-001: Unbounded thread creation ───────────────────────────────────
@app.route("/api/process-batch")
def process_batch():
    """Create a thread per item — unbounded resource usage."""
    items = request.json.get("items", [])
    threads = []
    for item in items:
        t = threading.Thread(target=process_item, args=(item,))
        t.start()
        threads.append(t)
    for t in threads:
        t.join()
    return jsonify({"processed": len(items)})


def process_item(item):
    """Process a single item (simulated)."""
    time.sleep(0.5)


# ─── CFG-001: Debug mode enabled ───────────────────────────────────────────
if __name__ == "__main__":
    # Start background polling thread
    poller = threading.Thread(target=poll_status, daemon=True)
    poller.start()

    port = int(os.environ.get("PORT", 5000))
    # Debug mode enabled in production!
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)

