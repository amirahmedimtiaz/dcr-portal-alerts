"""Build the static GitHub Pages dashboard from the SQLite snapshot."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from database import Database
from dashboard_data import all_payloads


def build_site(output_dir: str | Path = "site", database_path: str | Path | None = None) -> Path:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    data_dir = output / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    database = Database(database_path or os.getenv("DATABASE_PATH", "portal.db"))
    payloads = all_payloads(database)
    for name, payload in payloads.items():
        (data_dir / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )

    template = Path("templates/index.html").read_text(encoding="utf-8")
    static_index = (
        template
        .replace("{{ url_for('static', filename='styles.css') }}", "styles.css")
        .replace("{{ url_for('static', filename='app.js') }}", "app.js")
        .replace("<script src=\"app.js\"></script>", "<script>window.DCR_STATIC_DATA = true;</script>\n  <script src=\"app.js\"></script>")
    )
    (output / "index.html").write_text(static_index, encoding="utf-8")
    shutil.copyfile("static/app.js", output / "app.js")
    shutil.copyfile("static/styles.css", output / "styles.css")
    (output / ".nojekyll").write_text("", encoding="utf-8")
    return output


if __name__ == "__main__":
    build_site()
    print("Static site written to site/")

