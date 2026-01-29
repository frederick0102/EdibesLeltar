"""Régi jelszó törlése - egyszeri futtatás"""
import sqlite3
import os

db_path = 'data/leltar.db'

if not os.path.exists(db_path):
    print("Adatbázis még nem létezik. Indítsd el az alkalmazást!")
else:
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM settings WHERE key = 'app_password'")
    conn.commit()
    conn.close()
    print("Régi jelszó törölve! Indítsd újra az alkalmazást.")
