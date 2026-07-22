from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import random
import datetime

app = Flask(__name__)
app.secret_key = "parkflow_secret_key"

DATABASE = "database/parking.db"

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs("database", exist_ok=True)
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='users';
    """)
    table = cursor.fetchone()
    if table is None:
        with open("database/schema.sql", "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        with open("database/seed.sql", "r", encoding="utf-8") as f:
            conn.executescript(f.read())
        conn.commit()
        print("[DB] Database created successfully.")
    
    # Run migrations for new features
    try:
        # Check if settings table has stripe columns
        cursor.execute("PRAGMA table_info(settings);")
        columns = [col[1] for col in cursor.fetchall()]
        if 'stripe_publishable_key' not in columns:
            cursor.execute("ALTER TABLE settings ADD COLUMN stripe_publishable_key TEXT DEFAULT 'pk_test_placeholder';")
            cursor.execute("ALTER TABLE settings ADD COLUMN stripe_secret_key TEXT DEFAULT 'sk_test_placeholder';")
            cursor.execute("ALTER TABLE settings ADD COLUMN enable_stripe INTEGER DEFAULT 0;")
            conn.commit()
            print("[DB Migration] Added Stripe columns to settings.")
    except Exception as e:
        print(f"[DB Migration Error] Settings columns check: {e}")

    try:
        # Create services table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                description TEXT,
                icon TEXT DEFAULT 'fa-concierge-bell',
                status TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','INACTIVE'))
            );
        """)
        conn.commit()
        
        # Seed services if empty
        cursor.execute("SELECT COUNT(*) FROM services;")
        if cursor.fetchone()[0] == 0:
            services_seed = [
                ('Lavage Complet', 50.0, 'Lavage intérieur et extérieur de la voiture', 'fa-soap', 'ACTIVE'),
                ('Lavage Simple', 30.0, 'Lavage extérieur uniquement', 'fa-water', 'ACTIVE'),
                ('Café Premium', 15.0, 'Café chaud servi à l\'accueil', 'fa-mug-hot', 'ACTIVE'),
                ('Recharge Électrique', 100.0, 'Recharge complète sur borne rapide', 'fa-charging-station', 'ACTIVE'),
                ('Service Bagages', 20.0, 'Transport et assistance bagages', 'fa-suitcase', 'ACTIVE')
            ]
            cursor.executemany("""
                INSERT INTO services (name, price, description, icon, status)
                VALUES (?, ?, ?, ?, ?);
            """, services_seed)
            conn.commit()
            print("[DB Seed] Seeded default services.")
    except Exception as e:
        print(f"[DB Migration Error] Services table check: {e}")

    try:
        # Create parking_services table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS parking_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parking_session_id INTEGER NOT NULL,
                service_id INTEGER NOT NULL,
                price REAL NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(parking_session_id) REFERENCES parking_sessions(id) ON DELETE CASCADE,
                FOREIGN KEY(service_id) REFERENCES services(id)
            );
        """)
        conn.commit()
    except Exception as e:
        print(f"[DB Migration Error] Parking Services table check: {e}")

    try:
        # Create stripe_payments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stripe_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parking_session_id INTEGER NOT NULL,
                payment_intent_id TEXT NOT NULL UNIQUE,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                payment_method_type TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(parking_session_id) REFERENCES parking_sessions(id) ON DELETE CASCADE
            );
        """)
        conn.commit()
    except Exception as e:
        print(f"[DB Migration Error] Stripe Payments table check: {e}")

    conn.close()


init_db()

# ==========================================
#  1. التوجيه التلقائي للوڭين
# ==========================================
@app.route("/")
def home():
    return redirect(url_for("login"))

# ==========================================
#  2. صفحة تسجيل الدخول (Login)
# ==========================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user" in session:
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        auth_input = request.form.get("username")
        password = request.form.get("password")
        remember = request.form.get("remember")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM users 
            WHERE username = ? OR email = ?
        """, (auth_input, auth_input))
        user = cursor.fetchone()
        conn.close()
        
        if user and check_password_hash(user["password"], password):
            if user["status"] == "INACTIVE":
                flash("Votre compte est désactivé. Veuillez contacter l'administrateur.", "danger")
                return redirect(url_for("login"))
                
            session.clear()
            session.permanent = True if remember else False
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            session["fullname"] = user["fullname"]
            session["photo"] = user["photo"] or "default_avatar.png"
            session["user"] = user["username"] # to keep compatibility with other routes
            
            # Record log
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, ?, ?)
                """, (user["id"], "LOGIN", f"Utilisateur {user['username']} s'est connecté"))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Log Error: {str(e)}")
                
            flash("Connexion réussie !", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Nom d'utilisateur/Email ou mot de passe incorrect.", "danger")
            return redirect(url_for("login"))
            
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if "user" in session:
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        fullname = request.form.get("fullname")
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas.", "danger")
            return redirect(url_for("register"))
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if user already exists
        cursor.execute("SELECT * FROM users WHERE username = ? OR email = ?", (username, email))
        existing_user = cursor.fetchone()
        
        if existing_user:
            conn.close()
            flash("Ce nom d'utilisateur ou email est déjà utilisé.", "danger")
            return redirect(url_for("register"))
            
        hashed_password = generate_password_hash(password)
        
        try:
            cursor.execute("""
                INSERT INTO users (fullname, username, email, password, role, status)
                VALUES (?, ?, ?, ?, 'AGENT', 'ACTIVE')
            """, (fullname, username, email, hashed_password))
            
            user_id = cursor.lastrowid
            
            # Record log
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'REGISTER', ?)
            """, (user_id, f"Nouvel utilisateur enregistré: {username}"))
            
            conn.commit()
            conn.close()
            
            flash("Votre compte a été créé avec succès ! Connectez-vous.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            conn.close()
            flash(f"Une erreur est survenue lors de l'enregistrement : {str(e)}", "danger")
            return redirect(url_for("register"))
            
    return render_template("register.html")

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if "user" in session:
        return redirect(url_for("dashboard"))
        
    if request.method == "POST":
        email = request.form.get("email")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        
        if not user:
            conn.close()
            flash("Aucun compte n'est associé à cette adresse email.", "danger")
            return redirect(url_for("forgot_password"))
            
        code = str(random.randint(100000, 999999))
        expires_at = (datetime.datetime.now() + datetime.timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO password_resets (email, code, expires_at)
            VALUES (?, ?, ?)
        """, (email, code, expires_at))
        conn.commit()
        conn.close()
        
        flash(f"Code de vérification envoyé ! [Code de test : {code}]", "success")
        return redirect(url_for("reset_password", email=email))
        
    return render_template("forgot_password.html")

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if "user" in session:
        return redirect(url_for("dashboard"))
        
    email = request.args.get("email") or request.form.get("email")
    if not email:
        flash("Adresse email manquante.", "danger")
        return redirect(url_for("forgot_password"))
        
    if request.method == "POST":
        code = request.form.get("code")
        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")
        
        if password != confirm_password:
            flash("Les mots de passe ne correspondent pas.", "danger")
            return redirect(url_for("reset_password", email=email))
            
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM password_resets 
            WHERE email = ? AND code = ? 
            ORDER BY created_at DESC LIMIT 1
        """, (email, code))
        reset_entry = cursor.fetchone()
        
        if not reset_entry:
            conn.close()
            flash("Code de vérification invalide.", "danger")
            return redirect(url_for("reset_password", email=email))
            
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if reset_entry["expires_at"] < now_str:
            cursor.execute("DELETE FROM password_resets WHERE email = ?", (email,))
            conn.commit()
            conn.close()
            flash("Le code de vérification a expiré. Veuillez en demander un nouveau.", "danger")
            return redirect(url_for("forgot_password"))
            
        hashed_password = generate_password_hash(password)
        cursor.execute("UPDATE users SET password = ? WHERE email = ?", (hashed_password, email))
        
        cursor.execute("SELECT id, username FROM users WHERE email = ?", (email,))
        user = cursor.fetchone()
        if user:
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'PASSWORD_RESET', ?)
            """, (user["id"], f"Réinitialisation de mot de passe réussie pour {user['username']}"))
            
        cursor.execute("DELETE FROM password_resets WHERE email = ?", (email,))
        
        conn.commit()
        conn.close()
        
        flash("Votre mot de passe a été réinitialisé avec succès. Veuillez vous connecter.", "success")
        return redirect(url_for("login"))
        
    return render_template("reset_password.html", email=email)

# ==========================================
#  3. صفحة إدخال السيارات (الرئيسية مورا اللوڭين)
# ==========================================
@app.route("/parking/entry", methods=["GET", "POST"])
def parking_entry():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print_session = None
    print_ticket_id = request.args.get("print_ticket_id")
    if print_ticket_id:
        # Fetch ticket info
        cursor.execute("""
            SELECT parking_sessions.*, vehicles.matricule, vehicles.owner_name, vehicles.phone,
            brands.name as brand_name, colors.name as color_name, vehicle_types.name as type_name,
            parking_places.place_number, zones.name as zone_name
            FROM parking_sessions
            JOIN vehicles ON parking_sessions.vehicle_id = vehicles.id
            LEFT JOIN brands ON vehicles.brand_id = brands.id
            LEFT JOIN colors ON vehicles.color_id = colors.id
            LEFT JOIN vehicle_types ON vehicles.vehicle_type_id = vehicle_types.id
            JOIN parking_places ON parking_sessions.place_id = parking_places.id
            JOIN zones ON parking_places.zone_id = zones.id
            WHERE parking_sessions.id = ?
        """, (print_ticket_id,))
        print_session = cursor.fetchone()
        
    if request.method == "POST":
        matricule = request.form.get("matricule").strip().upper()
        vehicle_type_id = request.form.get("vehicle_type_id")
        brand_id = request.form.get("brand_id")
        color_id = request.form.get("color_id")
        owner_name = request.form.get("owner_name")
        phone = request.form.get("phone")
        
        parking_type_id = request.form.get("parking_type_id")
        duration = request.form.get("duration")
        place_id = request.form.get("place_id")
        
        if not place_id:
            flash("Aucune place sélectionnée ou disponible.", "danger")
            return redirect(url_for("parking_entry"))
            
        try:
            # 1. Upsert Vehicle
            cursor.execute("SELECT id FROM vehicles WHERE matricule = ?", (matricule,))
            vehicle_row = cursor.fetchone()
            if vehicle_row:
                vehicle_id = vehicle_row["id"]
                cursor.execute("""
                    UPDATE vehicles 
                    SET brand_id = ?, color_id = ?, vehicle_type_id = ?, owner_name = ?, phone = ?
                    WHERE id = ?
                """, (brand_id, color_id, vehicle_type_id, owner_name, phone, vehicle_id))
            else:
                cursor.execute("""
                    INSERT INTO vehicles (matricule, brand_id, color_id, vehicle_type_id, owner_name, phone)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (matricule, brand_id, color_id, vehicle_type_id, owner_name, phone))
                vehicle_id = cursor.lastrowid
                
            # 2. Check if already inside
            cursor.execute("""
                SELECT id FROM parking_sessions 
                WHERE vehicle_id = ? AND status = 'INSIDE'
            """, (vehicle_id,))
            already_inside = cursor.fetchone()
            if already_inside:
                flash(f"Le véhicule {matricule} est déjà stationné à l'intérieur du parking.", "danger")
                conn.close()
                return redirect(url_for("parking_entry"))
                
            # 3. Calculate expected exit
            now = datetime.datetime.now()
            if duration == "under_24h":
                expected = now + datetime.timedelta(hours=12)
            elif duration == "24h":
                expected = now + datetime.timedelta(hours=24)
            elif duration == "over_24h":
                expected = now + datetime.timedelta(hours=48)
            else:  # long_term
                expected = now + datetime.timedelta(days=7)
                
            now_str = now.strftime("%Y-%m-%d %H:%M:%S")
            expected_str = expected.strftime("%Y-%m-%d %H:%M:%S")
            
            # 4. Insert Session
            cursor.execute("""
                INSERT INTO parking_sessions (vehicle_id, place_id, guard_id, entry_datetime, expected_exit_datetime, status, payment_status)
                VALUES (?, ?, ?, ?, ?, 'INSIDE', 'NON_PAYE')
            """, (vehicle_id, place_id, session.get("user_id"), now_str, expected_str))
            session_id = cursor.lastrowid
            
            # 4b. Insert Selected Services
            selected_services = request.form.getlist("services")
            for svc_id in selected_services:
                cursor.execute("SELECT price FROM services WHERE id = ?", (svc_id,))
                svc = cursor.fetchone()
                if svc:
                    cursor.execute("""
                        INSERT INTO parking_services (parking_session_id, service_id, price)
                        VALUES (?, ?, ?)
                    """, (session_id, svc_id, svc["price"]))
            
            # 5. Update Spot Status
            cursor.execute("UPDATE parking_places SET status = 'OCCUPIED' WHERE id = ?", (place_id,))
            
            # 6. Log activity
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'ENTRY', ?)
            """, (session.get("user_id"), f"Véhicule {matricule} entré à la place ID {place_id} (Ticket TK-{session_id:06d})"))
            
            conn.commit()
            flash("Entrée enregistrée avec succès !", "success")
            conn.close()
            return redirect(url_for("parking_entry", print_ticket_id=session_id))
            
        except Exception as e:
            conn.close()
            flash(f"Erreur lors de l'enregistrement de l'entrée : {str(e)}", "danger")
            return redirect(url_for("parking_entry"))
            
    # Load dropdowns
    cursor.execute("SELECT * FROM brands ORDER BY name ASC")
    brands = cursor.fetchall()
    
    cursor.execute("SELECT * FROM colors ORDER BY name ASC")
    colors = cursor.fetchall()
    
    cursor.execute("SELECT * FROM vehicle_types ORDER BY name ASC")
    vehicle_types = cursor.fetchall()
    
    cursor.execute("SELECT * FROM parking_types ORDER BY name ASC")
    parking_types = cursor.fetchall()
    
    cursor.execute("SELECT * FROM services WHERE status = 'ACTIVE' ORDER BY name ASC")
    services = cursor.fetchall()
    
    conn.close()
    return render_template(
        "parking/entry.html", 
        username=session["user"],
        brands=brands,
        colors=colors,
        vehicle_types=vehicle_types,
        parking_types=parking_types,
        services=services,
        print_session=print_session
    )


@app.route("/api/propose-spot")
def propose_spot():
    parking_type_id = request.args.get("parking_type_id")
    if not parking_type_id:
        return jsonify({"success": False, "message": "Type de parking manquant"})
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT parking_places.id, parking_places.place_number, zones.name as zone_name
        FROM parking_places
        JOIN zones ON parking_places.zone_id = zones.id
        WHERE parking_places.parking_type_id = ? AND parking_places.status = 'FREE' AND zones.status = 'ACTIVE'
        ORDER BY zones.name ASC, parking_places.place_number ASC
        LIMIT 1
    """, (parking_type_id,))
    spot = cursor.fetchone()
    conn.close()
    
    if spot:
        return jsonify({
            "success": True,
            "spot_id": spot["id"],
            "place_number": spot["place_number"],
            "zone_name": spot["zone_name"]
        })
    else:
        return jsonify({
            "success": False,
            "message": "Aucune place libre disponible pour ce type de parking"
        })

@app.route("/api/available-spots")
def available_spots():
    parking_type_id = request.args.get("parking_type_id")
    if not parking_type_id:
        return jsonify([])
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT parking_places.id, parking_places.place_number, zones.name as zone_name
        FROM parking_places
        JOIN zones ON parking_places.zone_id = zones.id
        WHERE parking_places.parking_type_id = ? AND parking_places.status = 'FREE' AND zones.status = 'ACTIVE'
        ORDER BY zones.name ASC, parking_places.place_number ASC
    """, (parking_type_id,))
    spots = cursor.fetchall()
    conn.close()
    
    spots_list = []
    for s in spots:
        spots_list.append({
            "id": s["id"],
            "place_number": s["place_number"],
            "zone_name": s["zone_name"]
        })
    return jsonify(spots_list)

# ==========================================
#  4. باقي صفحات الـ Sidebar (روابط جاهزة للربط)
# ==========================================
@app.route("/dashboard")
def dashboard():
    if "user" not in session: 
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Total places
    cursor.execute("SELECT COUNT(*) FROM parking_places")
    total_places = cursor.fetchone()[0] or 0
    
    # 2. Available places
    cursor.execute("SELECT COUNT(*) FROM parking_places WHERE status = 'FREE'")
    available_places = cursor.fetchone()[0] or 0
    
    # 3. Occupied places
    cursor.execute("SELECT COUNT(*) FROM parking_places WHERE status = 'OCCUPIED'")
    occupied_places = cursor.fetchone()[0] or 0
    
    # 4. Entries today
    cursor.execute("SELECT COUNT(*) FROM parking_sessions WHERE date(entry_datetime) = date('now')")
    entries_today = cursor.fetchone()[0] or 0
    
    # 5. Exits today
    cursor.execute("SELECT COUNT(*) FROM parking_sessions WHERE date(exit_datetime) = date('now')")
    exits_today = cursor.fetchone()[0] or 0
    
    # 6. Revenue today
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE date(payment_date) = date('now')")
    revenue_today = cursor.fetchone()[0] or 0
    
    # Get active currency from settings
    cursor.execute("SELECT currency FROM settings ORDER BY id DESC LIMIT 1")
    settings_res = cursor.fetchone()
    currency = settings_res["currency"] if settings_res else "MAD"
    
    # Recent Activities
    cursor.execute("""
        SELECT logs.action, logs.details, logs.created_at, users.username 
        FROM logs 
        LEFT JOIN users ON logs.user_id = users.id 
        ORDER BY logs.created_at DESC LIMIT 8
    """)
    recent_activities = cursor.fetchall()
    
    # Chart Data: Occupancy by zone
    cursor.execute("""
        SELECT zones.name, COUNT(parking_places.id) as total,
        SUM(CASE WHEN parking_places.status = 'OCCUPIED' THEN 1 ELSE 0 END) as occupied
        FROM zones
        LEFT JOIN parking_places ON zones.id = parking_places.zone_id
        GROUP BY zones.name
    """)
    zone_occupancy = cursor.fetchall()
    zone_names = [z["name"] for z in zone_occupancy]
    zone_totals = [z["total"] or 0 for z in zone_occupancy]
    zone_occupied = [z["occupied"] or 0 for z in zone_occupancy]
    
    conn.close()
    
    return render_template(
        "dashboard.html", 
        username=session["user"],
        total_places=total_places,
        available_places=available_places,
        occupied_places=occupied_places,
        entries_today=entries_today,
        exits_today=exits_today,
        revenue_today=revenue_today,
        currency=currency,
        recent_activities=recent_activities,
        zone_names=zone_names,
        zone_totals=zone_totals,
        zone_occupied=zone_occupied
    )

@app.route("/parking/exit", methods=["GET", "POST"])
def parking_exit():
    """
    صفحة تسجيل خروج السيارة.
    - GET: البحث بالماتريكول أو رقم التذكرة وعرض تفاصيل الجلسة + السعر المحسوب.
    - POST: تأكيد الخروج، تحديث الجلسة، تحرير المكان، تسجيل الدفع.
    """
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # ========== Fetch currency from settings ==========
    cursor.execute("SELECT currency FROM settings LIMIT 1")
    s = cursor.fetchone()
    currency = s["currency"] if s else "MAD"

    found_session = None
    receipt_session = None

    # ========== Afficher le reçu après sortie confirmée ==========
    receipt_id = request.args.get("receipt_id")
    if receipt_id:
        cursor.execute("""
            SELECT parking_sessions.*,
                   vehicles.matricule, vehicles.owner_name, vehicles.phone,
                   brands.name as brand_name, colors.name as color_name,
                   vehicle_types.name as vtype_name,
                   parking_places.place_number,
                   zones.name as zone_name,
                   parking_types.name as ptype_name
            FROM parking_sessions
            JOIN vehicles       ON parking_sessions.vehicle_id   = vehicles.id
            LEFT JOIN brands    ON vehicles.brand_id              = brands.id
            LEFT JOIN colors    ON vehicles.color_id              = colors.id
            LEFT JOIN vehicle_types ON vehicles.vehicle_type_id   = vehicle_types.id
            JOIN parking_places ON parking_sessions.place_id      = parking_places.id
            JOIN zones          ON parking_places.zone_id         = zones.id
            JOIN parking_types  ON parking_places.parking_type_id = parking_types.id
            WHERE parking_sessions.id = ?
        """, (receipt_id,))
        res = cursor.fetchone()
        if res:
            receipt_session = dict(res)
            # Fetch services associated with this session
            cursor.execute("""
                SELECT services.name, parking_services.price
                FROM parking_services
                JOIN services ON parking_services.service_id = services.id
                WHERE parking_services.parking_session_id = ?
            """, (receipt_id,))
            receipt_services = cursor.fetchall()
            receipt_session["services"] = [dict(svc) for svc in receipt_services]
            receipt_session["services_total"] = sum(svc["price"] for svc in receipt_services)
            receipt_session["parking_price"] = receipt_session["total_price"] - receipt_session["services_total"]

    # ========== Recherche par ticket ou matricule ==========
    search_query = request.args.get("search", "").strip()
    if search_query:
        # Cherche d'abord par numéro de ticket (ex: TK-000007 ou simple id)
        ticket_id = search_query.replace("TK-", "").lstrip("0") or "0"
        cursor.execute("""
            SELECT parking_sessions.*,
                   vehicles.matricule, vehicles.owner_name, vehicles.phone,
                   brands.name as brand_name, colors.name as color_name,
                   vehicle_types.name as vtype_name,
                   parking_places.place_number,
                   zones.name as zone_name,
                   parking_types.name as ptype_name,
                   parking_types.price_24h, parking_types.extra_hour_price
            FROM parking_sessions
            JOIN vehicles       ON parking_sessions.vehicle_id   = vehicles.id
            LEFT JOIN brands    ON vehicles.brand_id              = brands.id
            LEFT JOIN colors    ON vehicles.color_id              = colors.id
            LEFT JOIN vehicle_types ON vehicles.vehicle_type_id   = vehicle_types.id
            JOIN parking_places ON parking_sessions.place_id      = parking_places.id
            JOIN zones          ON parking_places.zone_id         = zones.id
            JOIN parking_types  ON parking_places.parking_type_id = parking_types.id
            WHERE parking_sessions.status = 'INSIDE'
              AND (parking_sessions.id = ? OR vehicles.matricule LIKE ?)
            LIMIT 1
        """, (ticket_id, f"%{search_query}%"))
        found_res = cursor.fetchone()

        if found_res:
            found_session = dict(found_res)
            # Calcul dynamique de la durée et du prix du parking
            entry_dt = datetime.datetime.strptime(found_session["entry_datetime"], "%Y-%m-%d %H:%M:%S")
            now_dt   = datetime.datetime.now()
            delta    = now_dt - entry_dt
            hours    = max(delta.total_seconds() / 3600, 0)

            days  = int(hours // 24)
            extra = hours - (days * 24)

            price_24h  = found_session["price_24h"]
            extra_rate = found_session["extra_hour_price"]
            parking_price = (days * price_24h) + (extra * extra_rate)
            parking_price = round(parking_price, 2)

            # Charger les services choisis
            cursor.execute("""
                SELECT services.name, parking_services.price
                FROM parking_services
                JOIN services ON parking_services.service_id = services.id
                WHERE parking_services.parking_session_id = ?
            """, (found_session["id"],))
            session_services = cursor.fetchall()
            services_total = sum(svc["price"] for svc in session_services)
            total_price = round(parking_price + services_total, 2)

            # On passe ces valeurs en dictionnaire
            found_session["calc_hours"]   = round(hours, 2)
            found_session["calc_parking_price"] = parking_price
            found_session["calc_price"]   = total_price
            found_session["services"]     = [dict(svc) for svc in session_services]
            found_session["services_total"] = services_total
            found_session["currency"]     = currency
            found_session["now_str"]      = now_dt.strftime("%Y-%m-%d %H:%M:%S")

    # ========== Confirmation de la sortie (POST) ==========
    if request.method == "POST":
        session_id     = request.form.get("session_id")
        place_id       = request.form.get("place_id")
        total_price    = request.form.get("total_price", 0)
        duration_hours = request.form.get("duration_hours", 0)
        payment_method = request.form.get("payment_method", "CASH")
        now_str        = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # REDIRECT if CARD or MOBILE to dynamic checkout
        if payment_method in ["CARD", "MOBILE"]:
            conn.close()
            return redirect(url_for("payment_checkout", session_id=session_id, method=payment_method))

        try:
            # 1. Mettre à jour la session de stationnement
            cursor.execute("""
                UPDATE parking_sessions
                SET exit_datetime  = ?,
                    duration_hours = ?,
                    total_price    = ?,
                    payment_status = 'PAYE',
                    status         = 'EXITED'
                WHERE id = ?
            """, (now_str, duration_hours, total_price, session_id))

            # 2. Libérer la place
            cursor.execute("UPDATE parking_places SET status = 'FREE' WHERE id = ?", (place_id,))

            # 3. Enregistrer le paiement
            cursor.execute("""
                INSERT INTO payments (parking_session_id, amount, payment_method)
                VALUES (?, ?, ?)
            """, (session_id, total_price, payment_method))

            # 4. Logger l'action
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'EXIT', ?)
            """, (session.get("user_id"),
                  f"Sortie de la session TK-{int(session_id):06d} | Durée: {duration_hours}h | Prix: {total_price} {currency}"))

            conn.commit()
            flash("Sortie enregistrée avec succès !", "success")
            conn.close()
            return redirect(url_for("parking_exit", receipt_id=session_id))

        except Exception as e:
            conn.close()
            flash(f"Erreur lors de l'enregistrement de la sortie : {str(e)}", "danger")
            return redirect(url_for("parking_exit"))

    conn.close()
    return render_template(
        "parking/exit.html",
        found_session=found_session,
        receipt_session=receipt_session,
        search_query=search_query,
        currency=currency
    )


@app.route("/parking/spots")
def parking_spots():
    """
    Tableau de bord visuel des places actives : véhicules actuellement à l'intérieur.
    Affiche matricule, zone, place, heure d'entrée, durée écoulée.
    """
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Toutes les sessions INSIDE avec détails véhicule et place
    cursor.execute("""
        SELECT parking_sessions.id,
               parking_sessions.entry_datetime,
               vehicles.matricule,
               vehicles.owner_name,
               brands.name   AS brand_name,
               colors.name   AS color_name,
               parking_places.place_number,
               zones.name    AS zone_name,
               parking_types.name AS ptype_name
        FROM parking_sessions
        JOIN vehicles       ON parking_sessions.vehicle_id   = vehicles.id
        LEFT JOIN brands    ON vehicles.brand_id              = brands.id
        LEFT JOIN colors    ON vehicles.color_id              = colors.id
        JOIN parking_places ON parking_sessions.place_id      = parking_places.id
        JOIN zones          ON parking_places.zone_id         = zones.id
        JOIN parking_types  ON parking_places.parking_type_id = parking_types.id
        WHERE parking_sessions.status = 'INSIDE'
        ORDER BY parking_sessions.entry_datetime DESC
    """)
    active_sessions = cursor.fetchall()

    # Compteurs synthétiques
    cursor.execute("SELECT COUNT(*) FROM parking_places")
    total_spots = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM parking_places WHERE status = 'FREE'")
    free_spots = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM parking_places WHERE status = 'OCCUPIED'")
    occupied_spots = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM parking_places WHERE status = 'MAINTENANCE'")
    maintenance_spots = cursor.fetchone()[0] or 0

    conn.close()
    return render_template(
        "parking/active.html",
        active_sessions=active_sessions,
        total_spots=total_spots,
        free_spots=free_spots,
        occupied_spots=occupied_spots,
        maintenance_spots=maintenance_spots,
        now=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

@app.route("/parking/search")
def parking_search():
    """
    Recherche instantanée multi-critères :
    matricule, propriétaire, téléphone, numéro de ticket.
    Retourne JSON si ?json=1, sinon HTML complet.
    """
    if "user" not in session:
        return redirect(url_for("login"))

    q         = request.args.get("q", "").strip()
    as_json   = request.args.get("json", "0") == "1"
    conn      = get_db_connection()
    cursor    = conn.cursor()
    results   = []

    if q:
        ticket_id = q.replace("TK-", "").lstrip("0") or "0"
        cursor.execute("""
            SELECT parking_sessions.id,
                   parking_sessions.status      AS session_status,
                   parking_sessions.entry_datetime,
                   parking_sessions.exit_datetime,
                   parking_sessions.total_price,
                   parking_sessions.duration_hours,
                   vehicles.matricule,
                   vehicles.owner_name,
                   vehicles.phone,
                   brands.name   AS brand_name,
                   colors.name   AS color_name,
                   vehicle_types.name AS vtype_name,
                   parking_places.place_number,
                   zones.name    AS zone_name,
                   parking_types.name AS ptype_name
            FROM parking_sessions
            JOIN vehicles       ON parking_sessions.vehicle_id   = vehicles.id
            LEFT JOIN brands    ON vehicles.brand_id              = brands.id
            LEFT JOIN colors    ON vehicles.color_id              = colors.id
            LEFT JOIN vehicle_types ON vehicles.vehicle_type_id   = vehicle_types.id
            JOIN parking_places ON parking_sessions.place_id      = parking_places.id
            JOIN zones          ON parking_places.zone_id         = zones.id
            JOIN parking_types  ON parking_places.parking_type_id = parking_types.id
            WHERE parking_sessions.id  = ?
               OR vehicles.matricule   LIKE ?
               OR vehicles.owner_name  LIKE ?
               OR vehicles.phone       LIKE ?
            ORDER BY parking_sessions.entry_datetime DESC
            LIMIT 30
        """, (ticket_id, f"%{q}%", f"%{q}%", f"%{q}%"))
        results = cursor.fetchall()

    if as_json:
        conn.close()
        data = []
        for r in results:
            data.append({
                "id":            r["id"],
                "ticket":        f"TK-{r['id']:06d}",
                "matricule":     r["matricule"],
                "owner_name":    r["owner_name"] or "",
                "phone":         r["phone"] or "",
                "brand_name":    r["brand_name"] or "",
                "color_name":    r["color_name"] or "",
                "zone_name":     r["zone_name"],
                "place_number":  r["place_number"],
                "entry_datetime":r["entry_datetime"],
                "exit_datetime": r["exit_datetime"] or "",
                "status":        r["session_status"],
                "total_price":   r["total_price"]
            })
        return jsonify(data)

    conn.close()
    return render_template("parking/search.html", results=results, q=q)

@app.route("/parking/history")
def parking_history():
    """
    Historique paginé de toutes les sessions (INSIDE + EXITED).
    Filtres : date_from, date_to, status, zone_id.
    Export CSV disponible via ?export=csv.
    """
    if "user" not in session:
        return redirect(url_for("login"))

    # ---- Paramètres de filtre ----
    date_from   = request.args.get("date_from", "")
    date_to     = request.args.get("date_to",   "")
    status      = request.args.get("status",    "")
    zone_id     = request.args.get("zone_id",   "")
    page        = int(request.args.get("page",  1))
    per_page    = 20
    export_csv  = request.args.get("export") == "csv"

    conn   = get_db_connection()
    cursor = conn.cursor()

    # ---- Build dynamic WHERE ----
    conditions = ["1=1"]
    params     = []

    if date_from:
        conditions.append("DATE(parking_sessions.entry_datetime) >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("DATE(parking_sessions.entry_datetime) <= ?")
        params.append(date_to)
    if status:
        conditions.append("parking_sessions.status = ?")
        params.append(status)
    if zone_id:
        conditions.append("zones.id = ?")
        params.append(zone_id)

    where_clause = " AND ".join(conditions)

    base_query = f"""
        SELECT parking_sessions.id,
               parking_sessions.status      AS session_status,
               parking_sessions.entry_datetime,
               parking_sessions.exit_datetime,
               parking_sessions.duration_hours,
               parking_sessions.total_price,
               parking_sessions.payment_status,
               vehicles.matricule,
               vehicles.owner_name,
               brands.name   AS brand_name,
               colors.name   AS color_name,
               parking_places.place_number,
               zones.name    AS zone_name,
               parking_types.name AS ptype_name
        FROM parking_sessions
        JOIN vehicles       ON parking_sessions.vehicle_id   = vehicles.id
        LEFT JOIN brands    ON vehicles.brand_id              = brands.id
        LEFT JOIN colors    ON vehicles.color_id              = colors.id
        JOIN parking_places ON parking_sessions.place_id      = parking_places.id
        JOIN zones          ON parking_places.zone_id         = zones.id
        JOIN parking_types  ON parking_places.parking_type_id = parking_types.id
        WHERE {where_clause}
        ORDER BY parking_sessions.entry_datetime DESC
    """

    # ---- CSV export (no pagination) ----
    if export_csv:
        import csv
        import io
        from flask import Response
        cursor.execute(base_query, params)
        rows = cursor.fetchall()
        conn.close()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Ticket","Matricule","Propriétaire","Marque","Couleur",
                         "Zone","Place","Type","Entrée","Sortie",
                         "Durée(h)","Prix","Paiement","Statut"])
        for r in rows:
            writer.writerow([
                f"TK-{r['id']:06d}",
                r["matricule"], r["owner_name"] or "",
                r["brand_name"] or "", r["color_name"] or "",
                r["zone_name"], r["place_number"], r["ptype_name"],
                r["entry_datetime"], r["exit_datetime"] or "",
                r["duration_hours"], r["total_price"],
                r["payment_status"], r["session_status"]
            ])
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=historique_parking.csv"}
        )

    # ---- Count total for pagination ----
    cursor.execute(f"SELECT COUNT(*) FROM ({base_query})", params)
    total_count = cursor.fetchone()[0] or 0
    total_pages = max(1, (total_count + per_page - 1) // per_page)

    # ---- Paginated query ----
    cursor.execute(base_query + f" LIMIT {per_page} OFFSET {(page - 1) * per_page}", params)
    sessions = cursor.fetchall()

    # ---- Zones for filter dropdown ----
    cursor.execute("SELECT id, name FROM zones ORDER BY name ASC")
    zones = cursor.fetchall()

    # ---- Summary statistics for this filtered set ----
    cursor.execute(f"""
        SELECT
          COUNT(*) as total_sessions,
          SUM(CASE WHEN parking_sessions.status='EXITED' THEN 1 ELSE 0 END) as total_exited,
          SUM(parking_sessions.total_price) as total_revenue
        FROM parking_sessions
        JOIN vehicles       ON parking_sessions.vehicle_id   = vehicles.id
        JOIN parking_places ON parking_sessions.place_id      = parking_places.id
        JOIN zones          ON parking_places.zone_id         = zones.id
        JOIN parking_types  ON parking_places.parking_type_id = parking_types.id
        WHERE {where_clause}
    """, params)
    stats = cursor.fetchone()

    conn.close()
    return render_template(
        "parking/history.html",
        sessions=sessions,
        zones=zones,
        stats=stats,
        page=page,
        total_pages=total_pages,
        total_count=total_count,
        date_from=date_from,
        date_to=date_to,
        status=status,
        zone_id=zone_id
    )

# ==========================================
#  VEHICLES MANAGEMENT
# ==========================================
@app.route("/vehicles", methods=["GET", "POST"])
def vehicles_list():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        matricule = request.form.get("matricule")
        brand_id = request.form.get("brand_id")
        color_id = request.form.get("color_id")
        vehicle_type_id = request.form.get("vehicle_type_id")
        owner_name = request.form.get("owner_name")
        phone = request.form.get("phone")
        
        try:
            cursor.execute("""
                INSERT INTO vehicles (matricule, brand_id, color_id, vehicle_type_id, owner_name, phone)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (matricule, brand_id, color_id, vehicle_type_id, owner_name, phone))
            
            # Log action
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'VEHICLE_ADD', ?)
            """, (session.get("user_id"), f"Ajout du véhicule matricule {matricule}"))
            
            conn.commit()
            flash("Véhicule ajouté avec succès !", "success")
        except Exception as e:
            flash(f"Erreur : {str(e)}", "danger")
            
        return redirect(url_for("vehicles_list"))
        
    cursor.execute("""
        SELECT vehicles.*, brands.name as brand_name, colors.name as color_name, vehicle_types.name as type_name
        FROM vehicles
        LEFT JOIN brands ON vehicles.brand_id = brands.id
        LEFT JOIN colors ON vehicles.color_id = colors.id
        LEFT JOIN vehicle_types ON vehicles.vehicle_type_id = vehicle_types.id
        ORDER BY vehicles.created_at DESC
    """)
    vehicles = cursor.fetchall()
    
    cursor.execute("SELECT * FROM brands ORDER BY name ASC")
    brands = cursor.fetchall()
    
    cursor.execute("SELECT * FROM colors ORDER BY name ASC")
    colors = cursor.fetchall()
    
    cursor.execute("SELECT * FROM vehicle_types ORDER BY name ASC")
    vehicle_types = cursor.fetchall()
    
    conn.close()
    return render_template("vehicles/vehicles.html", vehicles=vehicles, brands=brands, colors=colors, vehicle_types=vehicle_types)

@app.route("/vehicles/delete/<int:id>")
def vehicle_delete(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT matricule FROM vehicles WHERE id = ?", (id,))
    veh = cursor.fetchone()
    if veh:
        cursor.execute("DELETE FROM vehicles WHERE id = ?", (id,))
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'VEHICLE_DELETE', ?)
        """, (session.get("user_id"), f"Suppression du véhicule {veh['matricule']}"))
        conn.commit()
        flash("Véhicule supprimé avec succès !", "success")
        
    conn.close()
    return redirect(url_for("vehicles_list"))

# ==========================================
#  BRANDS CRUD
# ==========================================
@app.route("/vehicles/brands", methods=["GET", "POST"])
def brands_list():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        name = request.form.get("name")
        try:
            cursor.execute("INSERT INTO brands (name) VALUES (?)", (name,))
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'BRAND_ADD', ?)
            """, (session.get("user_id"), f"Ajout de la marque {name}"))
            conn.commit()
            flash("Marque ajoutée avec succès !", "success")
        except Exception as e:
            flash(f"La marque '{name}' existe déjà ou une erreur est survenue.", "danger")
        return redirect(url_for("brands_list"))
        
    cursor.execute("SELECT * FROM brands ORDER BY name ASC")
    brands = cursor.fetchall()
    conn.close()
    return render_template("vehicles/brands.html", brands=brands)

@app.route("/vehicles/brands/delete/<int:id>")
def brand_delete(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM brands WHERE id = ?", (id,))
    brand = cursor.fetchone()
    if brand:
        try:
            cursor.execute("DELETE FROM brands WHERE id = ?", (id,))
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'BRAND_DELETE', ?)
            """, (session.get("user_id"), f"Suppression de la marque {brand['name']}"))
            conn.commit()
            flash("Marque supprimée avec succès !", "success")
        except Exception:
            flash("Impossible de supprimer cette marque car elle est associée à des véhicules.", "danger")
            
    conn.close()
    return redirect(url_for("brands_list"))

# ==========================================
#  COLORS CRUD
# ==========================================
@app.route("/vehicles/colors", methods=["GET", "POST"])
def colors_list():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        name = request.form.get("name")
        try:
            cursor.execute("INSERT INTO colors (name) VALUES (?)", (name,))
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'COLOR_ADD', ?)
            """, (session.get("user_id"), f"Ajout de la couleur {name}"))
            conn.commit()
            flash("Couleur ajoutée avec succès !", "success")
        except Exception as e:
            flash(f"La couleur '{name}' existe déjà ou une erreur est survenue.", "danger")
        return redirect(url_for("colors_list"))
        
    cursor.execute("SELECT * FROM colors ORDER BY name ASC")
    colors = cursor.fetchall()
    conn.close()
    return render_template("vehicles/colors.html", colors=colors)

@app.route("/vehicles/colors/delete/<int:id>")
def color_delete(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM colors WHERE id = ?", (id,))
    color = cursor.fetchone()
    if color:
        try:
            cursor.execute("DELETE FROM colors WHERE id = ?", (id,))
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'COLOR_DELETE', ?)
            """, (session.get("user_id"), f"Suppression de la couleur {color['name']}"))
            conn.commit()
            flash("Couleur supprimée avec succès !", "success")
        except Exception:
            flash("Impossible de supprimer cette couleur car elle est associée à des véhicules.", "danger")
            
    conn.close()
    return redirect(url_for("colors_list"))

# ==========================================
#  VEHICLE TYPES CRUD
# ==========================================
@app.route("/vehicles/types", methods=["GET", "POST"])
def types_list():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        name = request.form.get("name")
        try:
            cursor.execute("INSERT INTO vehicle_types (name) VALUES (?)", (name,))
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'VEHICLE_TYPE_ADD', ?)
            """, (session.get("user_id"), f"Ajout du type {name}"))
            conn.commit()
            flash("Type de véhicule ajouté avec succès !", "success")
        except Exception as e:
            flash(f"Le type '{name}' existe déjà ou une erreur est survenue.", "danger")
        return redirect(url_for("types_list"))
        
    cursor.execute("SELECT * FROM vehicle_types ORDER BY name ASC")
    types = cursor.fetchall()
    conn.close()
    return render_template("vehicles/types.html", vehicle_types=types)

@app.route("/vehicles/types/delete/<int:id>")
def type_delete(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM vehicle_types WHERE id = ?", (id,))
    vt = cursor.fetchone()
    if vt:
        try:
            cursor.execute("DELETE FROM vehicle_types WHERE id = ?", (id,))
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'VEHICLE_TYPE_DELETE', ?)
            """, (session.get("user_id"), f"Suppression du type de véhicule {vt['name']}"))
            conn.commit()
            flash("Type de véhicule supprimé avec succès !", "success")
        except Exception:
            flash("Impossible de supprimer ce type de véhicule car il est associé à des véhicules.", "danger")
            
    conn.close()
    return redirect(url_for("types_list"))

# ==========================================
#  ZONES CRUD
# ==========================================
@app.route("/parking-management/zones", methods=["GET", "POST"])
def zones_list():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        status = request.form.get("status", "ACTIVE")
        
        try:
            cursor.execute("""
                INSERT INTO zones (name, description, status)
                VALUES (?, ?, ?)
            """, (name, description, status))
            
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'ZONE_ADD', ?)
            """, (session.get("user_id"), f"Ajout de la zone {name}"))
            conn.commit()
            flash("Zone ajoutée avec succès !", "success")
        except Exception as e:
            flash(f"La zone '{name}' existe déjà ou une erreur est survenue.", "danger")
        return redirect(url_for("zones_list"))
        
    # Get all zones with dynamic spots count
    cursor.execute("""
        SELECT zones.*, COUNT(parking_places.id) as total_spots,
        SUM(CASE WHEN parking_places.status = 'FREE' THEN 1 ELSE 0 END) as free_spots
        FROM zones
        LEFT JOIN parking_places ON zones.id = parking_places.zone_id
        GROUP BY zones.id
        ORDER BY zones.name ASC
    """)
    zones = cursor.fetchall()
    conn.close()
    return render_template("parking_management/zones.html", zones=zones)

@app.route("/parking-management/zones/edit/<int:id>", methods=["POST"])
def zone_edit(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    name = request.form.get("name")
    description = request.form.get("description")
    status = request.form.get("status")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE zones 
            SET name = ?, description = ?, status = ?
            WHERE id = ?
        """, (name, description, status, id))
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'ZONE_EDIT', ?)
        """, (session.get("user_id"), f"Modification de la zone {name}"))
        conn.commit()
        flash("Zone mise à jour avec succès !", "success")
    except Exception as e:
        flash(f"Erreur lors de la mise à jour de la zone : {str(e)}", "danger")
        
    conn.close()
    return redirect(url_for("zones_list"))

@app.route("/parking-management/zones/delete/<int:id>")
def zone_delete(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM zones WHERE id = ?", (id,))
    zone = cursor.fetchone()
    if zone:
        try:
            cursor.execute("DELETE FROM zones WHERE id = ?", (id,))
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'ZONE_DELETE', ?)
            """, (session.get("user_id"), f"Suppression de la zone {zone['name']}"))
            conn.commit()
            flash("Zone supprimée avec succès !", "success")
        except Exception:
            flash("Impossible de supprimer cette zone car elle contient des places ou est associée à des sessions.", "danger")
            
    conn.close()
    return redirect(url_for("zones_list"))

# ==========================================
#  PLACES CRUD
# ==========================================
@app.route("/parking-management/places", methods=["GET", "POST"])
def places_list():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        place_number = request.form.get("place_number")
        zone_id = request.form.get("zone_id")
        parking_type_id = request.form.get("parking_type_id")
        status = request.form.get("status", "FREE")
        
        try:
            cursor.execute("""
                INSERT INTO parking_places (zone_id, parking_type_id, place_number, status)
                VALUES (?, ?, ?, ?)
            """, (zone_id, parking_type_id, place_number, status))
            
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'SPOT_ADD', ?)
            """, (session.get("user_id"), f"Ajout de la place {place_number}"))
            conn.commit()
            flash("Place ajoutée avec succès !", "success")
        except Exception as e:
            flash(f"La place '{place_number}' existe déjà dans cette zone ou une erreur est survenue.", "danger")
        return redirect(url_for("places_list"))
        
    # Get all spots with zone name and parking type details
    cursor.execute("""
        SELECT parking_places.*, zones.name as zone_name, parking_types.name as type_name
        FROM parking_places
        JOIN zones ON parking_places.zone_id = zones.id
        JOIN parking_types ON parking_places.parking_type_id = parking_types.id
        ORDER BY zones.name ASC, parking_places.place_number ASC
    """)
    places = cursor.fetchall()
    
    cursor.execute("SELECT * FROM zones WHERE status = 'ACTIVE' ORDER BY name ASC")
    zones = cursor.fetchall()
    
    cursor.execute("SELECT * FROM parking_types ORDER BY name ASC")
    parking_types = cursor.fetchall()
    
    conn.close()
    return render_template("parking_management/places.html", places=places, zones=zones, parking_types=parking_types)

@app.route("/parking-management/places/edit/<int:id>", methods=["POST"])
def place_edit(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    place_number = request.form.get("place_number")
    zone_id = request.form.get("zone_id")
    parking_type_id = request.form.get("parking_type_id")
    status = request.form.get("status")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE parking_places 
            SET place_number = ?, zone_id = ?, parking_type_id = ?, status = ?
            WHERE id = ?
        """, (place_number, zone_id, parking_type_id, status, id))
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'SPOT_EDIT', ?)
        """, (session.get("user_id"), f"Modification de la place {place_number}"))
        conn.commit()
        flash("Place mise à jour avec succès !", "success")
    except Exception as e:
        flash(f"Erreur lors de la mise à jour de la place : {str(e)}", "danger")
        
    conn.close()
    return redirect(url_for("places_list"))

@app.route("/parking-management/places/delete/<int:id>")
def place_delete(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT place_number FROM parking_places WHERE id = ?", (id,))
    place = cursor.fetchone()
    if place:
        try:
            cursor.execute("DELETE FROM parking_places WHERE id = ?", (id,))
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'SPOT_DELETE', ?)
            """, (session.get("user_id"), f"Suppression de la place {place['place_number']}"))
            conn.commit()
            flash("Place supprimée avec succès !", "success")
        except Exception:
            flash("Impossible de supprimer cette place car elle est liée à une session en cours.", "danger")
            
    conn.close()
    return redirect(url_for("places_list"))

# ==========================================
#  5. تسجيل الخروج (Logout)
# ==========================================
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ==========================================
#  STRIPE & CHECKOUT INTEGRATION
# ==========================================
@app.route("/payment/checkout/<int:session_id>")
def payment_checkout(session_id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    method = request.args.get("method", "CARD")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get settings for publishable key & currency
    cursor.execute("SELECT * FROM settings LIMIT 1")
    setting = cursor.fetchone()
    currency = setting["currency"] if setting else "MAD"
    publishable_key = setting["stripe_publishable_key"] if setting else "pk_test_placeholder"
    
    # Get session details
    cursor.execute("""
        SELECT parking_sessions.*, vehicles.matricule
        FROM parking_sessions
        JOIN vehicles ON parking_sessions.vehicle_id = vehicles.id
        WHERE parking_sessions.id = ?
    """, (session_id,))
    parking_session = cursor.fetchone()
    
    if not parking_session:
        conn.close()
        flash("Session introuvable.", "danger")
        return redirect(url_for("parking_exit"))
        
    # Get calculated price and details
    entry_dt = datetime.datetime.strptime(parking_session["entry_datetime"], "%Y-%m-%d %H:%M:%S")
    now_dt   = datetime.datetime.now()
    delta    = now_dt - entry_dt
    hours    = max(delta.total_seconds() / 3600, 0)
    
    days  = int(hours // 24)
    extra = hours - (days * 24)
    
    # Get rates
    cursor.execute("""
        SELECT parking_types.price_24h, parking_types.extra_hour_price
        FROM parking_sessions
        JOIN parking_places ON parking_sessions.place_id = parking_places.id
        JOIN parking_types ON parking_places.parking_type_id = parking_types.id
        WHERE parking_sessions.id = ?
    """, (session_id,))
    rates = cursor.fetchone()
    price_24h = rates["price_24h"] if rates else 40
    extra_rate = rates["extra_hour_price"] if rates else 5
    
    parking_price = round((days * price_24h) + (extra * extra_rate), 2)
    
    # Add services
    cursor.execute("""
        SELECT price FROM parking_services WHERE parking_session_id = ?
    """, (session_id,))
    services_total = sum(row["price"] for row in cursor.fetchall())
    total_price = round(parking_price + services_total, 2)
    
    conn.close()
    
    return render_template(
        "parking/payment.html",
        parking_session_data=dict(parking_session) if parking_session else {},  # 👈 بدلنا الاسم وحولناه لـ Dictionary آمن
        method=method,
        currency=currency,
        publishable_key=publishable_key,
        total_price=total_price,
        calc_hours=round(hours, 2),
        parking_price=parking_price,
        services_total=services_total
    )

@app.route("/api/create-payment-intent", methods=["POST"])
def create_payment_intent():
    import stripe
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT stripe_secret_key, currency FROM settings LIMIT 1")
    setting = cursor.fetchone()
    secret_key = setting["stripe_secret_key"] if setting else "sk_test_placeholder"
    currency = (setting["currency"] if setting else "MAD").lower()
    
    stripe.api_key = secret_key
    
    data = request.json or {}
    session_id = data.get("session_id")
    amount_val = data.get("amount")
    
    if not session_id or not amount_val:
        conn.close()
        return jsonify({"error": "Paramètres manquants"}), 400
        
    try:
        amount_cents = int(float(amount_val) * 100)
        
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency=currency,
            metadata={"session_id": session_id},
            automatic_payment_methods={"enabled": True}
        )
        
        conn.close()
        return jsonify({
            "clientSecret": intent.client_secret
        })
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e)}), 500

@app.route("/api/confirm-payment", methods=["POST"])
def confirm_payment():
    data = request.json or {}
    session_id = data.get("session_id")
    payment_method = data.get("payment_method", "CARD")
    amount = data.get("amount")
    payment_intent_id = data.get("payment_intent_id", "simulated")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT place_id, entry_datetime FROM parking_sessions WHERE id = ?", (session_id,))
    parking_session = cursor.fetchone()
    if not parking_session:
        conn.close()
        return jsonify({"success": False, "message": "Session introuvable"}), 404
        
    place_id = parking_session["place_id"]
    entry_dt = datetime.datetime.strptime(parking_session["entry_datetime"], "%Y-%m-%d %H:%M:%S")
    now_dt = datetime.datetime.now()
    delta = now_dt - entry_dt
    duration_hours = round(max(delta.total_seconds() / 3600, 0), 2)
    now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        # 1. Update parking session
        cursor.execute("""
            UPDATE parking_sessions
            SET exit_datetime  = ?,
                duration_hours = ?,
                total_price    = ?,
                payment_status = 'PAYE',
                status         = 'EXITED'
            WHERE id = ?
        """, (now_str, duration_hours, amount, session_id))
        
        # 2. Free place
        cursor.execute("UPDATE parking_places SET status = 'FREE' WHERE id = ?", (place_id,))
        
        # 3. Add to payments
        cursor.execute("""
            INSERT INTO payments (parking_session_id, amount, payment_method)
            VALUES (?, ?, ?)
        """, (session_id, amount, payment_method))
        
        # 4. Save Stripe details if provided
        if payment_intent_id and payment_intent_id != "simulated":
            cursor.execute("""
                INSERT INTO stripe_payments (parking_session_id, payment_intent_id, amount, currency, status)
                VALUES (?, ?, ?, ?, 'succeeded')
            """, (session_id, payment_intent_id, amount, "MAD"))
            
        # 5. Log activity
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'EXIT', ?)
        """, (session.get("user_id") or 1, f"Sortie via Paiement {payment_method} | Ticket TK-{int(session_id):06d} | Prix: {amount}"))
        
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Paiement confirmé avec succès"})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": str(e)}), 500

# ==========================================
#  REPORTS & STATISTICS
# ==========================================
@app.route("/reports")
def reports_dashboard():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Get currency
    cursor.execute("SELECT currency FROM settings LIMIT 1")
    s = cursor.fetchone()
    currency = s["currency"] if s else "MAD"
    
    # Overall summary stats
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payments")
    total_revenue = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM parking_sessions")
    total_sessions = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT AVG(duration_hours) FROM parking_sessions WHERE status='EXITED'")
    avg_duration = cursor.fetchone()[0] or 0
    avg_duration = round(avg_duration, 1) if avg_duration else 0
    
    # Revenue today, this week, this month
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE date(payment_date) = date('now')")
    rev_today = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE date(payment_date) >= date('now', '-7 days')")
    rev_week = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COALESCE(SUM(amount), 0) FROM payments WHERE date(payment_date) >= date('now', 'start of month')")
    rev_month = cursor.fetchone()[0] or 0
    
    # Payment method breakdown
    cursor.execute("""
        SELECT payment_method, COUNT(*) as count, SUM(amount) as total
        FROM payments
        GROUP BY payment_method
    """)
    pm_breakdown = cursor.fetchall()
    pm_labels = [row["payment_method"] for row in pm_breakdown]
    pm_totals = [row["total"] for row in pm_breakdown]
    
    # Zone occupancy breakdown
    cursor.execute("""
        SELECT zones.name, COUNT(parking_places.id) as total,
        SUM(CASE WHEN parking_places.status = 'OCCUPIED' THEN 1 ELSE 0 END) as occupied
        FROM zones
        LEFT JOIN parking_places ON zones.id = parking_places.zone_id
        GROUP BY zones.name
    """)
    zone_stats = cursor.fetchall()
    
    # Daily entries & exits for line chart (last 7 days)
    chart_dates = []
    chart_entries = []
    chart_exits = []
    for i in range(6, -1, -1):
        d_str = (datetime.datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
        cursor.execute("SELECT COUNT(*) FROM parking_sessions WHERE date(entry_datetime) = ?", (d_str,))
        ent = cursor.fetchone()[0] or 0
        cursor.execute("SELECT COUNT(*) FROM parking_sessions WHERE date(exit_datetime) = ?", (d_str,))
        ex = cursor.fetchone()[0] or 0
        chart_dates.append(d_str)
        chart_entries.append(ent)
        chart_exits.append(ex)
        
    # Popular services
    cursor.execute("""
        SELECT services.name, COUNT(*) as count, SUM(parking_services.price) as total
        FROM parking_services
        JOIN services ON parking_services.service_id = services.id
        GROUP BY services.name
        ORDER BY count DESC
    """)
    popular_services = cursor.fetchall()
    
    # Exited sessions log for the list
    cursor.execute("""
        SELECT parking_sessions.*, vehicles.matricule, payments.payment_method
        FROM parking_sessions
        JOIN vehicles ON parking_sessions.vehicle_id = vehicles.id
        LEFT JOIN payments ON payments.parking_session_id = parking_sessions.id
        WHERE parking_sessions.status = 'EXITED'
        ORDER BY parking_sessions.exit_datetime DESC
        LIMIT 20
    """)
    recent_exits = cursor.fetchall()
    
    conn.close()
    
    return render_template(
        "reports/reports.html",
        username=session["user"],
        currency=currency,
        total_revenue=total_revenue,
        total_sessions=total_sessions,
        avg_duration=avg_duration,
        rev_today=rev_today,
        rev_week=rev_week,
        rev_month=rev_month,
        pm_labels=pm_labels,
        pm_totals=pm_totals,
        zone_stats=zone_stats,
        chart_dates=chart_dates,
        chart_entries=chart_entries,
        chart_exits=chart_exits,
        popular_services=popular_services,
        recent_exits=recent_exits
    )

# ==========================================
#  SETTINGS & PROFILE
# ==========================================
@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        company_name = request.form.get("company_name")
        airport_name = request.form.get("airport_name")
        airport_code = request.form.get("airport_code")
        address = request.form.get("address")
        phone = request.form.get("phone")
        email = request.form.get("email")
        currency = request.form.get("currency", "MAD")
        enable_stripe = 1 if request.form.get("enable_stripe") else 0
        stripe_publishable_key = request.form.get("stripe_publishable_key")
        stripe_secret_key = request.form.get("stripe_secret_key")
        
        cursor.execute("""
            UPDATE settings
            SET company_name = ?, airport_name = ?, airport_code = ?,
                address = ?, phone = ?, email = ?, currency = ?,
                enable_stripe = ?, stripe_publishable_key = ?, stripe_secret_key = ?
            WHERE id = 1
        """, (company_name, airport_name, airport_code, address, phone, email, currency,
              enable_stripe, stripe_publishable_key, stripe_secret_key))
        conn.commit()
        
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'SETTINGS_EDIT', 'Mise à jour des paramètres du système')
        """, (session.get("user_id"),))
        conn.commit()
        flash("Paramètres enregistrés avec succès !", "success")
        return redirect(url_for("settings_page"))
        
    cursor.execute("SELECT * FROM settings LIMIT 1")
    settings_data = cursor.fetchone()
    
    # Load all services
    cursor.execute("SELECT * FROM services ORDER BY name ASC")
    services = cursor.fetchall()
    
    conn.close()
    
    return render_template(
        "settings/settings.html",
        username=session["user"],
        settings=settings_data,
        services=services
    )

@app.route("/profile", methods=["GET", "POST"])
def profile_page():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        fullname = request.form.get("fullname")
        email = request.form.get("email")
        phone = request.form.get("phone")
        password = request.form.get("password")
        
        if password:
            hashed_pwd = generate_password_hash(password)
            cursor.execute("""
                UPDATE users SET fullname = ?, email = ?, phone = ?, password = ?
                WHERE id = ?
            """, (fullname, email, phone, hashed_pwd, session["user_id"]))
        else:
            cursor.execute("""
                UPDATE users SET fullname = ?, email = ?, phone = ?
                WHERE id = ?
            """, (fullname, email, phone, session["user_id"]))
            
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'PROFILE_EDIT', 'Mise à jour des informations de profil')
        """, (session["user_id"],))
        
        conn.commit()
        session["fullname"] = fullname
        
        flash("Profil mis à jour avec succès !", "success")
        return redirect(url_for("profile_page"))
        
    cursor.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],))
    user_info = cursor.fetchone()
    conn.close()
    
    return render_template(
        "settings/profile.html",
        username=session["user"],
        user=user_info
    )

# ==========================================
#  SERVICES CRUD
# ==========================================
@app.route("/settings/services/add", methods=["POST"])
def service_add():
    if "user" not in session:
        return redirect(url_for("login"))
        
    name = request.form.get("name")
    price = request.form.get("price")
    description = request.form.get("description")
    icon = request.form.get("icon", "fa-concierge-bell")
    status = request.form.get("status", "ACTIVE")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO services (name, price, description, icon, status)
            VALUES (?, ?, ?, ?, ?)
        """, (name, float(price), description, icon, status))
        
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'SERVICE_ADD', ?)
        """, (session.get("user_id"), f"Ajout du service: {name}"))
        
        conn.commit()
        flash("Service ajouté avec succès !", "success")
    except Exception as e:
        flash(f"Erreur lors de l'ajout du service: {str(e)}", "danger")
        
    conn.close()
    return redirect(url_for("settings_page"))

@app.route("/settings/services/edit/<int:id>", methods=["POST"])
def service_edit(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    name = request.form.get("name")
    price = request.form.get("price")
    description = request.form.get("description")
    icon = request.form.get("icon", "fa-concierge-bell")
    status = request.form.get("status", "ACTIVE")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE services
            SET name = ?, price = ?, description = ?, icon = ?, status = ?
            WHERE id = ?
        """, (name, float(price), description, icon, status, id))
        
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'SERVICE_EDIT', ?)
        """, (session.get("user_id"), f"Modification du service ID {id} ({name})"))
        
        conn.commit()
        flash("Service mis à jour avec succès !", "success")
    except Exception as e:
        flash(f"Erreur lors de la modification du service: {str(e)}", "danger")
        
    conn.close()
    return redirect(url_for("settings_page"))

@app.route("/settings/services/delete/<int:id>")
def service_delete(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM parking_services
            JOIN parking_sessions ON parking_services.parking_session_id = parking_sessions.id
            WHERE parking_services.service_id = ? AND parking_sessions.status = 'INSIDE'
        """, (id,))
        used_count = cursor.fetchone()[0]
        
        if used_count > 0:
            flash("Impossible de supprimer ce service car il est actuellement associé à des véhicules garés.", "danger")
        else:
            cursor.execute("DELETE FROM services WHERE id = ?", (id,))
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'SERVICE_DELETE', ?)
            """, (session.get("user_id"), f"Suppression du service ID {id}"))
            conn.commit()
            flash("Service supprimé avec succès !", "success")
    except Exception as e:
        flash(f"Erreur lors de la suppression du service: {str(e)}", "danger")
        
    conn.close()
    return redirect(url_for("settings_page"))

# ==========================================
#  USERS CRUD
# ==========================================
@app.route("/users", methods=["GET", "POST"])
def users_list():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password")
        role = request.form.get("role", "AGENT")
        status = request.form.get("status", "ACTIVE")
        
        # Validate uniqueness (ignoring empty emails)
        if email:
            cursor.execute("SELECT id FROM users WHERE username = ? OR email = ?", (username, email))
        else:
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            
        if cursor.fetchone():
            flash("Erreur : Ce nom d'utilisateur ou cet email existe déjà.", "danger")
        else:
            hashed_pwd = generate_password_hash(password)
            try:
                cursor.execute("""
                    INSERT INTO users (fullname, username, email, phone, password, role, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (fullname, username, email, phone, hashed_pwd, role, status))
                
                cursor.execute("""
                    INSERT INTO logs (user_id, action, details)
                    VALUES (?, 'USER_ADD', ?)
                """, (session.get("user_id"), f"Ajout de l'utilisateur: {username} ({role})"))
                
                conn.commit()
                flash("Utilisateur ajouté avec succès !", "success")
            except Exception as e:
                flash("Erreur lors de l'ajout de l'utilisateur.", "danger")
            
        conn.close()
        return redirect(url_for("users_list"))
        
    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    conn.close()
    
    return render_template("users/users.html", username=session["user"], users=users)

@app.route("/users/edit/<int:id>", methods=["POST"])
def user_edit(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    fullname = request.form.get("fullname")
    username = request.form.get("username")
    email = request.form.get("email")
    phone = request.form.get("phone")
    password = request.form.get("password")
    role = request.form.get("role")
    status = request.form.get("status")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        if password:
            hashed_pwd = generate_password_hash(password)
            cursor.execute("""
                UPDATE users
                SET fullname = ?, username = ?, email = ?, phone = ?, password = ?, role = ?, status = ?
                WHERE id = ?
            """, (fullname, username, email, phone, hashed_pwd, role, status, id))
        else:
            cursor.execute("""
                UPDATE users
                SET fullname = ?, username = ?, email = ?, phone = ?, role = ?, status = ?
                WHERE id = ?
            """, (fullname, username, email, phone, role, status, id))
            
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'USER_EDIT', ?)
        """, (session.get("user_id"), f"Modification de l'utilisateur ID {id} ({username})"))
        
        conn.commit()
        flash("Utilisateur mis à jour avec succès !", "success")
    except Exception as e:
        flash(f"Erreur lors de la mise à jour de l'utilisateur: {str(e)}", "danger")
        
    conn.close()
    return redirect(url_for("users_list"))

@app.route("/users/delete/<int:id>")
def user_delete(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    if id == session["user_id"]:
        flash("Vous ne pouvez pas supprimer votre propre compte !", "danger")
        return redirect(url_for("users_list"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET status = 'INACTIVE' WHERE id = ?", (id,))
        cursor.execute("SELECT username FROM users WHERE id = ?", (id,))
        u = cursor.fetchone()
        
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'USER_DEACTIVATE', ?)
        """, (session.get("user_id"), f"Désactivation de l'utilisateur ID {id} ({u['username'] if u else 'inconnu'})"))
        
        conn.commit()
        flash("Utilisateur désactivé avec succès !", "success")
    except Exception as e:
        flash(f"Erreur lors de la désactivation de l'utilisateur: {str(e)}", "danger")
        
    conn.close()
    return redirect(url_for("users_list"))

# ==========================================
#  GUARDS MANAGEMENT
# ==========================================
@app.route("/users/guards")
def guards_list():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM users WHERE role = 'AGENT' ORDER BY fullname ASC")
    guards = cursor.fetchall()
    
    guards_details = []
    for guard in guards:
        cursor.execute("SELECT COUNT(*) FROM shifts WHERE guard_id = ? AND date(shift_date) >= date('now', 'start of month')", (guard["id"],))
        shifts_count = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT COUNT(*) FROM parking_sessions WHERE guard_id = ? AND date(entry_datetime) = date('now')", (guard["id"],))
        sessions_today = cursor.fetchone()[0] or 0
        
        cursor.execute("SELECT status FROM shifts WHERE guard_id = ? AND date(shift_date) = date('now') LIMIT 1", (guard["id"],))
        shift_status = cursor.fetchone()
        status_today = shift_status["status"] if shift_status else "NON_PLANIFIE"
        
        g_dict = dict(guard)
        g_dict["shifts_this_month"] = shifts_count
        g_dict["sessions_today"] = sessions_today
        g_dict["status_today"] = status_today
        guards_details.append(g_dict)
        
    conn.close()
    return render_template("users/guards.html", username=session["user"], guards=guards_details)

# ==========================================
#  SHIFTS SCHEDULING
# ==========================================
@app.route("/users/shifts", methods=["GET", "POST"])
def shifts_page():
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if request.method == "POST":
        guard_id = request.form.get("guard_id")
        shift_date = request.form.get("shift_date")
        start_time = request.form.get("start_time")
        end_time = request.form.get("end_time")
        status = request.form.get("status", "EN_SERVICE")
        
        try:
            cursor.execute("""
                INSERT INTO shifts (guard_id, shift_date, start_time, end_time, status)
                VALUES (?, ?, ?, ?, ?)
            """, (guard_id, shift_date, start_time, end_time, status))
            
            cursor.execute("SELECT fullname FROM users WHERE id = ?", (guard_id,))
            g = cursor.fetchone()
            
            cursor.execute("""
                INSERT INTO logs (user_id, action, details)
                VALUES (?, 'SHIFT_ADD', ?)
            """, (session.get("user_id"), f"Planification du shift pour {g['fullname'] if g else 'Garde'} le {shift_date}"))
            
            conn.commit()
            flash("Shift planifié avec succès !", "success")
        except Exception as e:
            flash(f"Erreur lors de la planification du shift: {str(e)}", "danger")
            
        return redirect(url_for("shifts_page"))
        
    cursor.execute("""
        SELECT shifts.*, users.fullname as guard_name
        FROM shifts
        JOIN users ON shifts.guard_id = users.id
        WHERE shifts.shift_date >= date('now', '-7 days')
        ORDER BY shifts.shift_date ASC, shifts.start_time ASC
    """)
    shifts = cursor.fetchall()
    
    cursor.execute("SELECT id, fullname FROM users WHERE role = 'AGENT' AND status = 'ACTIVE' ORDER BY fullname ASC")
    guards = cursor.fetchall()
    
    conn.close()
    return render_template(
        "users/shifts.html",
        username=session["user"],
        shifts=shifts,
        guards=guards
    )

@app.route("/users/shifts/edit/<int:id>", methods=["POST"])
def shift_edit(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    shift_date = request.form.get("shift_date")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")
    status = request.form.get("status")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE shifts
            SET shift_date = ?, start_time = ?, end_time = ?, status = ?
            WHERE id = ?
        """, (shift_date, start_time, end_time, status, id))
        
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'SHIFT_EDIT', ?)
        """, (session.get("user_id"), f"Modification du shift ID {id}"))
        
        conn.commit()
        flash("Shift mis à jour avec succès !", "success")
    except Exception as e:
        flash(f"Erreur lors de la mise à jour du shift: {str(e)}", "danger")
        
    conn.close()
    return redirect(url_for("shifts_page"))

@app.route("/users/shifts/delete/<int:id>")
def shift_delete(id):
    if "user" not in session:
        return redirect(url_for("login"))
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM shifts WHERE id = ?", (id,))
        cursor.execute("""
            INSERT INTO logs (user_id, action, details)
            VALUES (?, 'SHIFT_DELETE', ?)
        """, (session.get("user_id"), f"Suppression du shift ID {id}"))
        conn.commit()
        flash("Shift supprimé avec succès !", "success")
    except Exception as e:
        flash(f"Erreur lors de la suppression du shift: {str(e)}", "danger")
        
    conn.close()
    return redirect(url_for("shifts_page"))

# ==========================================
#  TRANSLATION ENGINE
# ==========================================

TRANSLATIONS = {
    "en": {
        "dashboard": "Dashboard",
        "entry": "Vehicle Entry",
        "exit": "Vehicle Exit",
        "vehicles": "Vehicles List",
        "brands": "Brands",
        "colors": "Colors",
        "types": "Vehicle Types",
        "zones": "Zones Management",
        "places": "Parking Spots",
        "search": "Instant Search",
        "history": "History & Logs",
        "reports": "Reports",
        "users": "System Users",
        "guards": "Guards/Agents",
        "shifts": "Guard Shifts",
        "settings": "Settings",
        "logout": "Logout",
        "airport_title": "Essaouira Mogador Airport",
        "smart_parking": "Smart Parking System",
        "notifications": "Notifications",
        "profile": "Profile",
        "total_spots": "Total Spots",
        "available_spots": "Available Spots",
        "occupied_spots": "Occupied Spots",
        "entries_today": "Entries Today",
        "exits_today": "Exits Today",
        "revenue_today": "Revenue Today",
        "recent_activities": "Recent Activities",
        "statistics": "Statistics Overview",
        "occupancy_rate": "Occupancy Rate",
        "no_activity": "No recent activity found.",
        "plate": "License Plate",
        "driver": "Driver Name",
        "phone": "Phone Number",
        "parking_type": "Parking Type",
        "duration": "Expected Duration",
        "propose_spot": "Proposed Spot",
        "submit_entry": "Register Entry",
        "print_ticket": "Print Ticket",
        "search_exit": "Search Ticket or Plate",
        "submit_exit": "Register Exit",
        "duration_parked": "Duration Parked",
        "price": "Price",
        "save": "Save",
        "cancel": "Cancel",
        "edit": "Edit",
        "delete": "Delete",
        "add": "Add New"
    },
    "fr": {
        "dashboard": "Tableau de bord",
        "entry": "Entrée véhicule",
        "exit": "Sortie véhicule",
        "vehicles": "Liste Véhicules",
        "brands": "Marques",
        "colors": "Couleurs",
        "types": "Types de véhicule",
        "zones": "Gestion des Zones",
        "places": "Places de parking",
        "search": "Recherche instantanée",
        "history": "Historique & Logs",
        "reports": "Rapports",
        "users": "Utilisateurs",
        "guards": "Agents/Gardiens",
        "shifts": "Shifts des agents",
        "settings": "Paramètres",
        "logout": "Déconnexion",
        "airport_title": "Aéroport Essaouira Mogador",
        "smart_parking": "Système de Parking Intelligent",
        "notifications": "Notifications",
        "profile": "Profil",
        "total_spots": "Places Totales",
        "available_spots": "Places Disponibles",
        "occupied_spots": "Places Occupées",
        "entries_today": "Entrées Aujourd'hui",
        "exits_today": "Sorties Aujourd'hui",
        "revenue_today": "Revenus du Jour",
        "recent_activities": "Dernières Activités",
        "statistics": "Aperçu des Statistiques",
        "occupancy_rate": "Taux d'occupation",
        "no_activity": "Aucune activité récente.",
        "plate": "Immatriculation",
        "driver": "Nom du propriétaire",
        "phone": "Téléphone",
        "parking_type": "Type de parking",
        "duration": "Durée prévue",
        "propose_spot": "Place Proposée",
        "submit_entry": "Enregistrer l'Entrée",
        "print_ticket": "Imprimer Ticket",
        "search_exit": "Rechercher Ticket ou Matricule",
        "submit_exit": "Valider la Sortie",
        "duration_parked": "Durée stationnement",
        "price": "Prix",
        "save": "Enregistrer",
        "cancel": "Annuler",
        "edit": "Modifier",
        "delete": "Supprimer",
        "add": "Ajouter"
    },
    "ar": {
        "dashboard": "لوحة التحكم",
        "entry": "تسجيل دخول",
        "exit": "تسجيل خروج",
        "vehicles": "قائمة المركبات",
        "brands": "العلامات التجارية",
        "colors": "الألوان",
        "types": "أنواع المركبات",
        "zones": "إدارة المناطق",
        "places": "أماكن الوقوف",
        "search": "بحث فوري",
        "history": "الأرشيف والسجلات",
        "reports": "التقارير",
        "users": "المستخدمين",
        "guards": "حراس الأمن",
        "shifts": "مناوبات الحراس",
        "settings": "الإعدادات",
        "logout": "تسجيل الخروج",
        "airport_title": "مطار الصويرة موغادور",
        "smart_parking": "نظام مواقف السيارات الذكي",
        "notifications": "الإشعارات",
        "profile": "الملف الشخصي",
        "total_spots": "إجمالي الأماكن",
        "available_spots": "الأماكن الشاغرة",
        "occupied_spots": "الأماكن المحجوزة",
        "entries_today": "دخول اليوم",
        "exits_today": "خروج اليوم",
        "revenue_today": "مداخيل اليوم",
        "recent_activities": "آخر النشاطات",
        "statistics": "نظرة عامة على الإحصائيات",
        "occupancy_rate": "نسبة الإشغال",
        "no_activity": "لا توجد نشاطات حديثة.",
        "plate": "رقم اللوحة",
        "driver": "اسم صاحب المركبة",
        "phone": "رقم الهاتف",
        "parking_type": "نوع الموقف",
        "duration": "المدة المتوقعة",
        "propose_spot": "المكان المقترح",
        "submit_entry": "تسجيل الدخول",
        "print_ticket": "طباعة التذكرة",
        "search_exit": "بحث برقم التذكرة أو اللوحة",
        "submit_exit": "تأكيد الخروج",
        "duration_parked": "مدة الوقوف",
        "price": "السعر",
        "save": "حفظ",
        "cancel": "إلغاء",
        "edit": "تعديل",
        "delete": "حذف",
        "add": "إضافة"
    }
}

@app.route("/set-language/<lang>")
def set_language(lang):
    if lang in ["fr", "en", "ar"]:
        session["lang"] = lang
        referer = request.referrer
        if referer and request.host in referer:
            return redirect(referer)
        return redirect(url_for("dashboard"))
    return redirect(url_for("dashboard"))

@app.context_processor
def inject_global_data():
    lang = session.get("lang", "fr")
    def translate(key):
        return TRANSLATIONS.get(lang, TRANSLATIONS["fr"]).get(key, key)
        
    try:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings LIMIT 1")
        setting = cursor.fetchone()
        conn.close()
    except Exception:
        setting = None
        
    currency = setting["currency"] if setting else "MAD"
    
    currency_symbols = {"MAD": "MAD", "EUR": "EUR", "USD": "USD"}
    curr_symbol = currency_symbols.get(currency, currency)
    
    def convert_amount(amount):
        if amount is None:
            return 0.0
        amount = float(amount)
        if currency == "EUR":
            return round(amount / 10.8, 2)
        elif currency == "USD":
            return round(amount / 10.1, 2)
        return round(amount, 2)
        
    def format_price(amount):
        converted = convert_amount(amount)
        if currency == "EUR":
            return f"{converted:.2f} €"
        elif currency == "USD":
            return f"${converted:.2f}"
        return f"{converted:.2f} MAD"
        
    return dict(
        t=translate, 
        current_lang=lang, 
        settings=setting, 
        currency=currency, 
        curr_symbol=curr_symbol,
        convert_amount=convert_amount,
        format_price=format_price
    )


if __name__ == "__main__":
    app.run(debug=True)