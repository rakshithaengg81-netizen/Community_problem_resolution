
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "community_platform_secret"

# Database connection
def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn
# AUTOMATIC COMPLAINT PRIORITY

def determine_priority(category, description):

    text = (category + " " + description).lower()

    high_keywords = [
        "emergency",
        "dangerous",
        "accident",
        "overflowing",
        "flood",
        "fire",
        "electric shock",
        "broken manhole",
        "sewage"
    ]

    low_keywords = [
        "minor",
        "small issue",
        "cosmetic",
        "slight"
    ]

    for word in high_keywords:
        if word in text:
            return "High"

    for word in low_keywords:
        if word in text:
            return "Low"

    return "Medium"
# Create database tables
def create_tables():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            description TEXT,
            location TEXT,
            priority TEXT DEFAULT 'Medium',
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        conn = get_db()

        try:
            conn.execute(
                "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
                (name, email, password)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Email already registered"

        conn.close()
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["name"] = user["name"]
            return redirect(url_for("dashboard"))

        return "Invalid email or password"

    return render_template("login.html")


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db()

    complaints = conn.execute(
        "SELECT * FROM complaints WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],)
    ).fetchall()

    total = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()[0]

    pending = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE user_id = ? AND status = 'Pending'",
        (session["user_id"],)
    ).fetchone()[0]

    in_progress = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE user_id = ? AND status = 'In Progress'",
        (session["user_id"],)
    ).fetchone()[0]

    resolved = conn.execute(
        "SELECT COUNT(*) FROM complaints WHERE user_id = ? AND status = 'Resolved'",
        (session["user_id"],)
    ).fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        complaints=complaints,
        name=session["name"],
        total=total,
        pending=pending,
        in_progress=in_progress,
        resolved=resolved
    )

@app.route("/report", methods=["GET", "POST"])
def report():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        category = request.form["category"]
        description = request.form["description"]
        location = request.form["location"]
        priority = determine_priority(category, description)
        conn = get_db()
        conn.execute("""
    INSERT INTO complaints
    (user_id, category, description, location, priority)
    VALUES (?, ?, ?, ?, ?)
""", (
    session["user_id"],
    category,
    description,
    location,
    priority
))

        conn.commit()
        conn.close()

        return redirect(url_for("dashboard"))

    return render_template("report.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ADMIN LOGIN

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        # Demo admin credentials
        if email == "admin@gmail.com" and password == "admin123":

            session["admin"] = True

            return redirect(url_for("admin_dashboard"))

        return "Invalid admin credentials"

    return render_template("admin_login.html")


# ADMIN DASHBOARD

# ADMIN DASHBOARD

@app.route("/admin")
def admin_dashboard():

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    search = request.args.get("search", "")
    status = request.args.get("status", "")
    priority = request.args.get("priority", "")

    query = """
        SELECT complaints.*, users.name, users.email
        FROM complaints
        JOIN users ON complaints.user_id = users.id
        WHERE 1=1
    """

    values = []

    if search:
        query += """
            AND (
                complaints.category LIKE ?
                OR complaints.location LIKE ?
                OR complaints.description LIKE ?
            )
        """
        values.extend([f"%{search}%"] * 3)

    if status:
        query += " AND complaints.status = ?"
        values.append(status)

    if priority:
        query += " AND complaints.priority = ?"
        values.append(priority)

    query += " ORDER BY complaints.id DESC"

    conn = get_db()
    complaints = conn.execute(query, values).fetchall()
    conn.close()

    return render_template(
        "admin.html",
        complaints=complaints,
        search=search,
        selected_status=status,
        selected_priority=priority
    )


# UPDATE COMPLAINT STATUS

@app.route("/update-status/<int:complaint_id>", methods=["POST"])
def update_status(complaint_id):

    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    status = request.form["status"]

    if status not in ["Pending", "In Progress", "Resolved"]:
        return "Invalid status", 400

    conn = get_db()

    conn.execute(
        "UPDATE complaints SET status = ? WHERE id = ?",
        (status, complaint_id)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("admin_dashboard"))


# ADMIN LOGOUT

@app.route("/admin-logout")
def admin_logout():

    session.pop("admin", None)

    return redirect(url_for("home"))

if __name__ == "__main__":
    create_tables()
    app.run(debug=True)
