import sqlite3
from werkzeug.security import generate_password_hash

conn = sqlite3.connect('database/parking.db')
cursor = conn.cursor()

fullname = "Test User"
username = "testuser"
email = "test@test.com"
phone = "123456"
password = "password"
role = "AGENT"
status = "ACTIVE"
hashed_pwd = generate_password_hash(password)

try:
    cursor.execute("""
        INSERT INTO users (fullname, username, email, phone, password, role, status)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (fullname, username, email, phone, hashed_pwd, role, status))
    
    cursor.execute("""
        INSERT INTO logs (user_id, action, details)
        VALUES (?, 'USER_ADD', ?)
    """, (1, f"Ajout de l'utilisateur: {username} ({role})"))
    
    conn.commit()
    print("Success")
except Exception as e:
    print("Error:", str(e))

conn.close()
