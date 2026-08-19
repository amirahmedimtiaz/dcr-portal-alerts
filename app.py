"""Fast local dashboard for stored Solar DCR Portal data."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template

from database import Database
from dashboard_data import metrics_payload, manufacturers_payload, summary_payload


load_dotenv()
app = Flask(__name__)
db = Database(os.getenv("DATABASE_PATH", "portal.db"))


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/summary")
def summary():
    return jsonify(summary_payload(db))


@app.get("/api/metrics")
def metrics():
    return jsonify(metrics_payload(db))


@app.get("/api/manufacturers")
def manufacturers():
    return jsonify(manufacturers_payload(db))


@app.get("/api/runs")
def runs():
    return jsonify({"runs": db.recent_runs()})


if __name__ == "__main__":
    app.run(
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )
