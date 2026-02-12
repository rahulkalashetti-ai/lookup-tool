"""
ToolHub — Tool availability lookup (Infosec inventory, user lookup).
Run: flask --app app run
"""
import io
from pathlib import Path
from flask import Flask, request, redirect, url_for, session, render_template, flash, send_file
import pandas as pd

import config
from database import init_db, db, get_connection, get_latest_verified_path, get_inventory_version_history, get_cached_scan, save_scan_cache
from auth import verify_user, login_required, role_required, current_user
from audit import log as audit_log, get_logs
from storage import save_encrypted, load_encrypted, content_hash
from excel_utils import validate_inventory_excel, validate_scan_excel
from ai_scanner import run_scan, lookup_tool, lookup_suggestions
from export_results import export_excel, export_pdf

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024  # 25 MB

# --- Init ---
init_db()

# --- Auth routes ---
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", next=request.args.get("next", url_for("dashboard")))
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    user = verify_user(username, password)
    if not user:
        flash("Invalid username or password.", "error")
        return redirect(url_for("login"))
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["role"] = user["role"]
    audit_log("login", user["username"], "")
    next_url = request.form.get("next") or url_for("dashboard")
    return redirect(next_url)

@app.route("/logout")
def logout():
    if session.get("username"):
        audit_log("logout", session["username"], "")
    session.clear()
    return redirect(url_for("login"))

# --- Dashboard ---
@app.route("/")
def index():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    latest_path, ver = get_latest_verified_path()
    has_verified = latest_path is not None and latest_path.exists()
    return render_template(
        "dashboard.html",
        user=user,
        has_verified_inventory=has_verified,
        inventory_version=ver,
    )

# --- Infosec: upload verified inventory ---
@app.route("/infosec/upload", methods=["GET", "POST"])
@login_required
@role_required("infosec")
def infosec_upload():
    if request.method == "GET":
        return render_template("infosec_upload.html", user=current_user())
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("infosec_upload"))
    path = Path(config.UPLOAD_FOLDER) / file.filename
    file.save(path)
    ok, msg, df = validate_inventory_excel(path)
    if not ok:
        path.unlink(missing_ok=True)
        flash(msg, "error")
        return redirect(url_for("infosec_upload"))
    # Store encrypted, versioned
    with db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(MAX(version), 0) + 1 FROM inventory_versions")
        version = cur.fetchone()[0]
    stored_name = f"verified_v{version}.xlsx"
    stored_path = config.VERSION_FOLDER / stored_name
    save_encrypted(path.read_bytes(), stored_path)
    path.unlink(missing_ok=True)
    with db() as conn:
        conn.execute("""
            INSERT INTO inventory_versions (version, filename, stored_path, uploaded_by, row_count)
            VALUES (?, ?, ?, ?, ?)
        """, (version, file.filename, str(stored_path), session["username"], len(df)))
    audit_log("infosec_upload", session["username"], f"version={version} rows={len(df)}")
    flash(f"Verified inventory uploaded successfully (version {version}, {len(df)} rows).", "success")
    return redirect(url_for("infosec_versions"))

@app.route("/infosec/versions")
@login_required
@role_required("infosec")
def infosec_versions():
    history = get_inventory_version_history()
    return render_template("infosec_versions.html", user=current_user(), history=history)

@app.route("/infosec/logs")
@login_required
@role_required("infosec", "auditor", "admin")
def infosec_logs():
    logs = get_logs()
    return render_template("audit_log.html", user=current_user(), logs=logs)

# --- Tool lookup: user types tool name → Yes/No + status ---
@app.route("/lookup", methods=["GET", "POST"])
@login_required
def tool_lookup():
    user = current_user()
    latest_path, ver = get_latest_verified_path()
    if latest_path is None or not latest_path.exists():
        flash("No verified inventory available. Ask Infosec to upload one.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "GET":
        return render_template(
            "lookup.html",
            user=user,
            inventory_version=ver,
            result=None,
            query="",
            vendor_query="",
        )
    query = (request.form.get("tool_name") or "").strip()
    if not query:
        flash("Enter a tool name to search.", "error")
        return redirect(url_for("tool_lookup"))
    vendor_filter = (request.form.get("vendor") or "").strip()
    matches = lookup_tool(query, latest_path, vendor_filter=vendor_filter)
    suggestions = []
    if len(matches) == 0:
        suggestions = lookup_suggestions(query, latest_path)
    audit_log("lookup", session["username"], f"tool_name={query} matches={len(matches)}")
    return render_template(
        "lookup.html",
        user=user,
        inventory_version=ver,
        result={
            "found": len(matches) > 0,
            "matches": matches,
            "suggestions": suggestions,
        },
        query=query,
        vendor_query=vendor_filter,
    )

# --- General user: bulk scan (optional) ---
@app.route("/scan", methods=["GET", "POST"])
@login_required
def scan_upload():
    user = current_user()
    latest_path, ver = get_latest_verified_path()
    if latest_path is None or not latest_path.exists():
        flash("No verified inventory available. Ask Infosec to upload one.", "error")
        return redirect(url_for("dashboard"))
    if request.method == "GET":
        return render_template(
            "scan_upload.html",
            user=user,
            inventory_version=ver,
            max_scan_rows=config.MAX_SCAN_ROWS,
        )
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return redirect(url_for("scan_upload"))
    path = Path(config.UPLOAD_FOLDER) / file.filename
    file.save(path)
    ok, msg, user_df = validate_scan_excel(path)
    if not ok:
        path.unlink(missing_ok=True)
        flash(msg, "error")
        return redirect(url_for("scan_upload"))
    # Check cache (before deleting temp file we have user_df in memory)
    input_bytes = user_df.to_csv(index=False).encode()
    input_hash = content_hash(input_bytes)
    path.unlink(missing_ok=True)
    cached = get_cached_scan(input_hash)
    if cached and Path(cached["excel"]).exists():
        audit_log("scan", session["username"], "cache_hit")
        return redirect(url_for("scan_results", token=input_hash))
    # Run AI scan
    result_df = run_scan(user_df, latest_path)
    file_id = input_hash[:16]
    excel_path = config.RESULTS_FOLDER / f"result_{file_id}.xlsx"
    pdf_path = config.RESULTS_FOLDER / f"result_{file_id}.pdf"
    export_excel(result_df, excel_path)
    export_pdf(result_df, pdf_path)
    save_scan_cache(input_hash, str(excel_path), str(pdf_path))
    audit_log("scan", session["username"], f"rows={len(result_df)}")
    return redirect(url_for("scan_results", token=input_hash))

@app.route("/scan/results/<token>")
@login_required
def scan_results(token):
    cached = get_cached_scan(token)
    if not cached:
        flash("Results not found or expired.", "error")
        return redirect(url_for("scan_upload"))
    excel_path = Path(cached["excel"])
    pdf_path = Path(cached["pdf"])
    if not excel_path.exists():
        flash("Result file missing.", "error")
        return redirect(url_for("scan_upload"))
    return render_template(
        "scan_results.html",
        user=current_user(),
        token=token,
        has_excel=excel_path.exists(),
        has_pdf=pdf_path.exists(),
    )

@app.route("/scan/download/<token>/<format>")
@login_required
def scan_download(token, format):
    cached = get_cached_scan(token)
    if not cached or format not in ("excel", "pdf"):
        return "Not found", 404
    path = Path(cached["excel"] if format == "excel" else cached["pdf"])
    if not path.exists():
        return "File not found", 404
    return send_file(path, as_attachment=True, download_name=path.name)

# --- Audit log (auditor / admin) ---
@app.route("/audit")
@login_required
@role_required("infosec", "auditor", "admin")
def audit():
    logs = get_logs()
    return render_template("audit_log.html", user=current_user(), logs=logs)

# --- Admin: placeholder for rules/retrain (US-4) ---
@app.route("/admin")
@login_required
@role_required("admin")
def admin():
    return render_template("admin.html", user=current_user())

# --- Template download ---
@app.route("/template")
@login_required
def download_template():
    df = pd.DataFrame(columns=config.ALL_COLUMNS)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="tool_inventory_template.xlsx", mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    app.run(debug=True, port=5000)
