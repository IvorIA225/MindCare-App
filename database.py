import sqlite3
import uuid
from datetime import datetime

DB_PATH = "aura_data.db"

# ============================================================
# INITIALISATION
# ============================================================
def init_db():
    """Initialise la base de données et crée les tables si elles n'existent pas."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table 1 : Les Identités (Le pont secret)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            real_name   TEXT UNIQUE,
            created_at  TIMESTAMP
        )
    """)

    # Table 2 : Les Conversations (Anonymisées)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT,
            role        TEXT,
            content     TEXT,
            timestamp   TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# ============================================================
# GESTION DES UTILISATEURS
# ============================================================
def obtenir_ou_creer_id_anonyme(nom_reel: str) -> str:
    """Récupère l'ID anonyme d'un utilisateur ou en crée un nouveau."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM users WHERE real_name = ?", (nom_reel,))
    result = cursor.fetchone()

    if result:
        user_id = result[0]
    else:
        user_id = str(uuid.uuid4())[:8]
        cursor.execute(
            "INSERT INTO users (id, real_name, created_at) VALUES (?, ?, ?)",
            (user_id, nom_reel, datetime.now())
        )
        conn.commit()

    conn.close()
    return user_id


def lister_prenoms() -> list:
    """Retourne la liste de tous les prénoms enregistrés."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT real_name FROM users ORDER BY real_name ASC")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]


# ============================================================
# GESTION DES MESSAGES
# ============================================================
def sauvegarder_conversation(user_id: str, role: str, texte: str):
    """Enregistre un message en utilisant uniquement l'ID anonyme."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (user_id, role, texte, datetime.now())
    )
    conn.commit()
    conn.close()


def charger_historique(user_id: str) -> list:
    """Charge tout l'historique d'un utilisateur via son ID anonyme."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT role, content, timestamp 
           FROM messages 
           WHERE user_id = ? 
           ORDER BY message_id ASC""",
        (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "role": r[0],
            "content": r[1],
            "horodatage": str(r[2])
        }
        for r in rows
    ]


def compter_messages(user_id: str) -> dict:
    """Retourne des statistiques sur les conversations d'un utilisateur."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role = 'user'",
        (user_id,)
    )
    nb_messages = cursor.fetchone()[0]

    cursor.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM messages WHERE user_id = ?",
        (user_id,)
    )
    dates = cursor.fetchone()
    conn.close()

    return {
        "nb_messages": nb_messages,
        "premiere_session": str(dates[0])[:10] if dates[0] else "Aujourd'hui",
        "derniere_session": str(dates[1])[:10] if dates[1] else "Maintenant"
    }


def supprimer_historique(user_id: str):
    """Supprime tous les messages d'un utilisateur (garde le compte)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()