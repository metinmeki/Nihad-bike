import os
import sqlite3
from datetime import datetime

from flask import Flask, g, jsonify, render_template, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "nihadbike.db")

app = Flask(__name__)


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


def init_db():
    db = sqlite3.connect(DB_PATH)
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

        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            total REAL NOT NULL,
            profit REAL NOT NULL
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
        """
    )
    db.commit()
    db.close()


def row_to_item(r):
    return {"id": r["id"], "name": r["name"], "model": r["model"] or "", "cost": r["cost"], "price": r["price"], "qty": r["qty"]}


def row_to_sale(r, lines):
    return {
        "id": r["id"],
        "date": r["date"],
        "total": r["total"],
        "profit": r["profit"],
        "lines": [
            {"itemId": l["item_id"], "name": l["name"], "model": l["model"] or "", "qty": l["qty"], "price": l["price"], "cost": l["cost"]}
            for l in lines
        ],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    db = get_db()
    items = [row_to_item(r) for r in db.execute("SELECT * FROM items ORDER BY name")]
    sales_rows = db.execute("SELECT * FROM sales ORDER BY id").fetchall()
    sales = []
    for s in sales_rows:
        lines = db.execute("SELECT * FROM sale_lines WHERE sale_id = ?", (s["id"],)).fetchall()
        sales.append(row_to_sale(s, lines))
    purchases = [dict(r) for r in db.execute("SELECT * FROM purchases ORDER BY id")]
    return jsonify({"items": items, "sales": sales, "purchases": purchases})


@app.route("/api/items", methods=["POST"])
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
def delete_item(item_id):
    db = get_db()
    db.execute("DELETE FROM items WHERE id=?", (item_id,))
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/purchases", methods=["POST"])
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


@app.route("/api/sales", methods=["POST"])
def add_sale():
    data = request.get_json(force=True)
    lines = data.get("lines", [])
    if not lines:
        return jsonify({"error": "empty cart"}), 400

    db = get_db()
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
    cur = db.execute("INSERT INTO sales (date, total, profit) VALUES (?, ?, ?)", (now, total, profit))
    sale_id = cur.lastrowid

    for r in resolved:
        item = r["item"]
        db.execute(
            "INSERT INTO sale_lines (sale_id, item_id, name, model, qty, price, cost) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (sale_id, item["id"], item["name"], item["model"], r["qty"], r["price"], item["cost"]),
        )
        db.execute("UPDATE items SET qty = qty - ? WHERE id=?", (r["qty"], item["id"]))

    db.commit()
    return jsonify({"id": sale_id, "total": total, "profit": profit})


@app.route("/receipt/<int:sale_id>")
def receipt(sale_id):
    lang = request.args.get("lang", "ar")
    db = get_db()
    sale = db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if sale is None:
        return "Sale not found", 404
    lines = db.execute("SELECT * FROM sale_lines WHERE sale_id=?", (sale_id,)).fetchall()
    sale_dict = row_to_sale(sale, lines)
    return render_template("receipt.html", sale=sale_dict, lang=lang)


if __name__ == "__main__":
    init_db()
    print("Nihad Bike POS is running locally.")
    print("Open this address in your browser: http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
