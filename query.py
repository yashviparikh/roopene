import sqlite3

conn = sqlite3.connect("data/app.db")
cursor = conn.cursor()

cursor.execute("SELECT * FROM inventory_master")
rows = cursor.fetchall()

conn.close()
