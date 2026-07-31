import os
import secrets
import sqlite3
from datetime import datetime
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nihadbike.db")
SECRET_KEY_PATH = os.path.join(BASE_DIR, ".secret_key")

app = Flask(__name__)


def load_secret_key():
    if os.path.exists(SECRET_KEY_PATH):
        with open(SECRET_KEY_PATH, "r") as f:
            return f.read().strip()
    key = secrets.token_hex(32)
    with open(SECRET_KEY_PATH, "w") as f:
        f.write(key)
    return key


app.secret_key = load_secret_key()


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def column_exists(db, table, column):
    cols = [r["name"] for r in db.execute(f"PRAGMA table_info({table})")]
    return column in cols


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            model TEXT,
            cost REAL NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0,
            qty INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS purchases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            name TEXT NOT NULL,
            qty INTEGER NOT NULL,
            cost REAL NOT NULL,
            date TEXT NOT NULL,
            FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            total REAL NOT NULL,
            profit REAL NOT NULL,
            client_id INTEGER,
            client_name TEXT,
            FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS sale_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            item_id INTEGER,
            name TEXT NOT NULL,
            model TEXT,
            qty INTEGER NOT NULL,
            price REAL NOT NULL,
            cost REAL NOT NULL,
            FOREIGN KEY (sale_id) REFERENCES sales (id) ON DELETE CASCADE,
            FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'cashier',
            created_at TEXT NOT NULL
        );
        """
    )
    db.commit()

    # Migrate older databases that predate the clients feature.
    if not column_exists(db, "sales", "client_id"):
        db.execute("ALTER TABLE sales ADD COLUMN client_id INTEGER")
    if not column_exists(db, "sales", "client_name"):
        db.execute("ALTER TABLE sales ADD COLUMN client_name TEXT")
    db.commit()

    # First run: create a default admin account so there is always a way in.
    user_count = db.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if user_count == 0:
        first_username = "Nihad"
        first_password = "Nihad@1212"
        db.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (first_username, generate_password_hash(first_password), "admin", datetime.now().isoformat()),
        )
        db.commit()
        print("=" * 50)
        print("First run: created admin account")
        print(f"  Username: {first_username}")
        print(f"  Password: {first_password}")
        print("=" * 50)

    db.close()


def row_to_item(r):
    return {"id": r["id"], "name": r["name"], "model": r["model"] or "", "cost": r["cost"], "price": r["price"], "qty": r["qty"]}


def row_to_sale(r, lines):
    return {
        "id": r["id"],
        "date": r["date"],
        "total": r["total"],
        "profit": r["profit"],
        "clientId": r["client_id"],
        "clientName": r["client_name"] or "",
        "lines": [
            {"itemId": l["item_id"], "name": l["name"], "model": l["model"] or "", "qty": l["qty"], "price": l["price"], "cost": l["cost"]}
            for l in lines
        ],
    }


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"error": "login required"}), 401
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "admins only"}), 403
            return "غير مصرح لك بهذا الإجراء", 403
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None)
    username = (request.form.get("username") or "").strip()
    password = request.form.get("password") or ""
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username,)).fetchone()
    if user is None or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", error="اسم المستخدم أو كلمة المرور غير صحيحة")
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def index():
    return render_template("index.html", user={"username": session["username"], "role": session["role"]})


@app.route("/api/state")
@login_required
def api_state():
    db = get_db()
    is_admin = session.get("role") == "admin"
    items = [row_to_item(r) for r in db.execute("SELECT * FROM items ORDER BY name")]
    if not is_admin:
        for i in items:
            i["cost"] = None
    sales_rows = db.execute("SELECT * FROM sales ORDER BY id").fetchall()
    sales = []
    for s in sales_rows:
        lines = db.execute("SELECT * FROM sale_lines WHERE sale_id = ?", (s["id"],)).fetchall()
        sale = row_to_sale(s, lines)
        if not is_admin:
            sale["profit"] = None
            for l in sale["lines"]:
                l["cost"] = None
        sales.append(sale)
    purchases = [] if not is_admin else [dict(r) for r in db.execute("SELECT * FROM purchases ORDER BY id")]
    clients = [dict(r) for r in db.execute("SELECT * FROM clients ORDER BY name")]
    expenses = [] if not is_admin else [dict(r) for r in db.execute("SELECT * FROM expenses ORDER BY id")]
    return jsonify({
        "items": items, "sales": sales, "purchases": purchases, "clients": clients, "expenses": expenses,
        "currentUser": {"username": session["username"], "role": session["role"]},
    })


@app.route("/api/items", methods=["POST"])
@login_required
@admin_required
def add_item():
    data = request.get_json(force=True)
    db = get_db()
    cur = db.execute(
        "INSERT INTO items (name, model, cost, price, qty) VALUES (?, ?, ?, ?, ?)",
        (data["name"], data.get("model", ""), float(data["cost"]), float(data["price"]), int(data["qty"])),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid})


@app.route("/api/items/<int:item_id>", methods=["PUT"])
@login_required
@admin_required
def update_item(item_id):
    data = request.get_json(force=True)
    db = get_db()
    db.execute(
        "UPDATE items SET name=?, model=?, cost=?, price=?, qty=? WHERE id=?",
        (data["name"], data.get("model", ""), float(data["cost"]), float(data["price"]), int(data["qty"]), item_id),
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/items/<int:item_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_item(item_id):
    db = get_db()
    db.execute("DELETE FROM items WHERE id=?", (item_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/purchases", methods=["POST"])
@login_required
@admin_required
def add_purchase():
    data = request.get_json(force=True)
    db = get_db()
    qty = int(data["qty"])
    cost = float(data["cost"])
    now = datetime.now().isoformat()

    if data.get("mode") == "existing":
        item_id = int(data["itemId"])
        item = db.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if item is None:
            return jsonify({"error": "item not found"}), 404
        db.execute("UPDATE items SET qty = qty + ?, cost = ? WHERE id=?", (qty, cost, item_id))
        db.execute(
            "INSERT INTO purchases (item_id, name, qty, cost, date) VALUES (?, ?, ?, ?, ?)",
            (item_id, item["name"], qty, cost, now),
        )
        db.commit()
        return jsonify({"ok": True, "name": item["name"]})
    else:
        name = data["name"]
        model = data.get("model", "")
        price = float(data["price"])
        cur = db.execute(
            "INSERT INTO items (name, model, cost, price, qty) VALUES (?, ?, ?, ?, ?)",
            (name, model, cost, price, qty),
        )
        item_id = cur.lastrowid
        db.execute(
            "INSERT INTO purchases (item_id, name, qty, cost, date) VALUES (?, ?, ?, ?, ?)",
            (item_id, name, qty, cost, now),
        )
        db.commit()
        return jsonify({"ok": True, "name": name})


@app.route("/api/clients", methods=["GET"])
@login_required
def list_clients():
    db = get_db()
    clients = [dict(r) for r in db.execute("SELECT * FROM clients ORDER BY name")]
    return jsonify(clients)


@app.route("/api/clients", methods=["POST"])
@login_required
def add_client():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO clients (name, phone, created_at) VALUES (?, ?, ?)",
        (name, phone, datetime.now().isoformat()),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "name": name, "phone": phone})


@app.route("/api/clients/<int:client_id>", methods=["PUT"])
@login_required
@admin_required
def update_client(client_id):
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    phone = (data.get("phone") or "").strip()
    if not name:
        return jsonify({"error": "name required"}), 400
    db = get_db()
    db.execute("UPDATE clients SET name=?, phone=? WHERE id=?", (name, phone, client_id))
    db.execute("UPDATE sales SET client_name=? WHERE client_id=?", (name, client_id))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/clients/<int:client_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_client(client_id):
    db = get_db()
    db.execute("UPDATE sales SET client_id=NULL WHERE client_id=?", (client_id,))
    db.execute("DELETE FROM clients WHERE id=?", (client_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/expenses", methods=["POST"])
@login_required
@admin_required
def add_expense():
    data = request.get_json(force=True)
    description = (data.get("description") or "").strip()
    try:
        amount = float(data.get("amount"))
    except (TypeError, ValueError):
        amount = 0
    if not description or amount <= 0:
        return jsonify({"error": "description and a positive amount required"}), 400
    db = get_db()
    cur = db.execute(
        "INSERT INTO expenses (description, amount, date) VALUES (?, ?, ?)",
        (description, amount, datetime.now().isoformat()),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid})


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_expense(expense_id):
    db = get_db()
    db.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/sales", methods=["POST"])
@login_required
def add_sale():
    data = request.get_json(force=True)
    lines = data.get("lines", [])
    if not lines:
        return jsonify({"error": "empty cart"}), 400

    db = get_db()
    client_id = data.get("clientId") or None
    client_name = ""
    if client_id:
        client = db.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        if client is not None:
            client_name = client["name"]

    total = 0.0
    profit = 0.0
    resolved = []

    for line in lines:
        item = db.execute("SELECT * FROM items WHERE id=?", (line["itemId"],)).fetchone()
        if item is None:
            return jsonify({"error": f"item {line['itemId']} not found"}), 404
        qty = int(line["qty"])
        price = float(line["price"])
        if qty <= 0:
            return jsonify({"error": "quantity must be greater than 0"}), 400
        if qty > item["qty"]:
            return jsonify({"error": f"only {item['qty']} of {item['name']} in stock"}), 400
        line_total = price * qty
        line_profit = (price - item["cost"]) * qty
        total += line_total
        profit += line_profit
        resolved.append({"item": item, "qty": qty, "price": price})

    now = datetime.now().isoformat()
    cur = db.execute(
        "INSERT INTO sales (date, total, profit, client_id, client_name) VALUES (?, ?, ?, ?, ?)",
        (now, total, profit, client_id, client_name),
    )
    sale_id = cur.lastrowid

    for r in resolved:
        item = r["item"]
        db.execute(
            "INSERT INTO sale_lines (sale_id, item_id, name, model, qty, price, cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sale_id, item["id"], item["name"], item["model"], r["qty"], r["price"], item["cost"]),
        )
        db.execute("UPDATE items SET qty = qty - ? WHERE id=?", (r["qty"], item["id"]))

    db.commit()
    response_profit = profit if session.get("role") == "admin" else None
    return jsonify({"id": sale_id, "total": total, "profit": response_profit})


@app.route("/api/users", methods=["GET"])
@login_required
@admin_required
def list_users():
    db = get_db()
    users = [
        {"id": r["id"], "username": r["username"], "role": r["role"], "createdAt": r["created_at"]}
        for r in db.execute("SELECT * FROM users ORDER BY username")
    ]
    return jsonify(users)


@app.route("/api/users", methods=["POST"])
@login_required
@admin_required
def add_user():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = data.get("role") or "cashier"
    if role not in ("admin", "cashier"):
        role = "cashier"
    if not username or len(password) < 4:
        return jsonify({"error": "username and a password of at least 4 characters required"}), 400
    db = get_db()
    existing = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
    if existing is not None:
        return jsonify({"error": "username already taken"}), 400
    cur = db.execute(
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
        (username, generate_password_hash(password), role, datetime.now().isoformat()),
    )
    db.commit()
    return jsonify({"id": cur.lastrowid, "username": username, "role": role})


@app.route("/api/users/<int:user_id>", methods=["DELETE"])
@login_required
@admin_required
def delete_user(user_id):
    db = get_db()
    if user_id == session["user_id"]:
        return jsonify({"error": "cannot delete your own account while logged in"}), 400
    target = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if target is None:
        return jsonify({"error": "user not found"}), 404
    if target["role"] == "admin":
        admin_count = db.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin'").fetchone()["n"]
        if admin_count <= 1:
            return jsonify({"error": "cannot delete the last remaining admin"}), 400
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/users/<int:user_id>/password", methods=["PUT"])
@login_required
@admin_required
def reset_user_password(user_id):
    data = request.get_json(force=True)
    password = data.get("password") or ""
    if len(password) < 4:
        return jsonify({"error": "password must be at least 4 characters"}), 400
    db = get_db()
    db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(password), user_id))
    db.commit()
    return jsonify({"ok": True})


@app.route("/receipt/<int:sale_id>")
@login_required
def receipt(sale_id):
    db = get_db()
    sale = db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if sale is None:
        return "Sale not found", 404
    lines = db.execute("SELECT * FROM sale_lines WHERE sale_id=?", (sale_id,)).fetchall()
    sale_dict = row_to_sale(sale, lines)
    return render_template("receipt.html", sale=sale_dict)


init_db()

if __name__ == "__main__":
    print("Nihad Bike POS is running locally.")
    print("Open this address in your browser: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)