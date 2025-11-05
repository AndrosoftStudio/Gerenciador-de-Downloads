# core/database.py
import sqlite3
import os
from .settings import DB_FILE # Importa o caminho do DB_FILE

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            path TEXT NOT NULL,
            filename TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.commit()

def add_to_history(url, file_path):
    try:
        filename = os.path.basename(file_path)
        folder_path = os.path.dirname(file_path)
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO downloads (url, path, filename) VALUES (?, ?, ?)", 
                           (url, folder_path, filename))
            conn.commit()
    except Exception as e:
        print(f"Erro ao salvar no histórico: {e}")

def get_history():
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT url, path, filename, timestamp FROM downloads ORDER BY timestamp DESC")
            return cursor.fetchall()
    except Exception as e:
        print(f"Erro ao ler o histórico: {e}")
        return []