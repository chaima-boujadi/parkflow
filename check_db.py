import sqlite3
conn = sqlite3.connect('database/parking.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
print("Tables:", tables)

# Check users
c.execute("SELECT id, username, role FROM users")
users = c.fetchall()
print("Users:", users)

# Check settings
c.execute("SELECT * FROM settings")
settings = c.fetchall()
print("Settings:", settings)

conn.close()
