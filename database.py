import sqlite3
from datetime import datetime

DB_PATH = "mindcare_historique.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            prenom      TEXT,
            role        TEXT,
            message     TEXT,
            horodatage  TEXT
        )
    """)
    conn.commit()
    conn.close()

def sauvegarder_message(prenom: str, role: str, message: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO conversations (prenom, role, message, horodatage) VALUES (?, ?, ?, ?)",
        (prenom or "Anonyme", role, message, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def charger_historique(prenom: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT role, message, horodatage FROM conversations WHERE prenom = ? ORDER BY id ASC",
        (prenom or "Anonyme",)
    )
    rows = c.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1], "horodatage": r[2]} for r in rows]

def lister_prenoms() -> list:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT DISTINCT prenom FROM conversations ORDER BY prenom ASC")
    rows = c.fetchall()
    conn.close()
    return [r[0] for r in rows]

def supprimer_historique(prenom: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM conversations WHERE prenom = ?", (prenom,))
    conn.commit()
    conn.close()

def compter_messages(prenom: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM conversations WHERE prenom = ? AND role = 'user'",
        (prenom or "Anonyme",)
    )
    nb_user = c.fetchone()[0]
    c.execute(
        "SELECT MIN(horodatage), MAX(horodatage) FROM conversations WHERE prenom = ?",
        (prenom or "Anonyme",)
    )
    dates = c.fetchone()
    conn.close()
    return {
        "nb_messages": nb_user,
        "premiere_session": dates[0],
        "derniere_session": dates[1]
    }