import sqlite3
import uuid
import logging
import re
from datetime import datetime
from cryptography.fernet import Fernet
import os

DB_PATH = "aura_data.db"

# ============================================================
# CHIFFREMENT
# ============================================================
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "").encode()
fernet = Fernet(ENCRYPTION_KEY) if ENCRYPTION_KEY else None

def chiffrer(texte: str) -> str:
    if fernet and texte:
        try:
            return fernet.encrypt(texte.encode()).decode()
        except:
            return texte
    return texte

def dechiffrer(texte: str) -> str:
    if fernet and texte:
        try:
            return fernet.decrypt(texte.encode()).decode()
        except:
            return texte
    return texte

# ============================================================
# VALIDATION
# ============================================================
def valider_prenom(prenom: str) -> bool:
    if not prenom or len(prenom.strip()) < 2 or len(prenom.strip()) > 50:
        return False
    return bool(re.match(r"^[a-zA-ZÀ-ÿ\s'\-]+$", prenom.strip()))

# ============================================================
# INITIALISATION
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table 1 — Identités anonymisées
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id          TEXT PRIMARY KEY,
            real_name   TEXT UNIQUE,
            created_at  TIMESTAMP,
            is_premium  INTEGER DEFAULT 0
        )
    """)

    # Table 2 — Messages chiffrés
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

    # Table 3 — Profil personnalisé persistant
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profils (
            user_id         TEXT PRIMARY KEY,
            prenom          TEXT,
            situation       TEXT,
            defis           TEXT,
            objectifs       TEXT,
            humeur_generale TEXT,
            preferences     TEXT,
            notes_aura      TEXT,
            derniere_maj    TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Table 4 — Suivi humeur
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS humeurs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT,
            score       INTEGER,
            emoji       TEXT,
            note        TEXT,
            date        TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    # Table 5 — Logs d'accès (sans données personnelles)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs_acces (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT,
            action      TEXT,
            timestamp   TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

# ============================================================
# GESTION UTILISATEURS
# ============================================================
def obtenir_ou_creer_id_anonyme(nom_reel: str) -> str:
    if not valider_prenom(nom_reel):
        raise ValueError("Prénom invalide")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    nom_normalise = nom_reel.strip().capitalize()
    cursor.execute("SELECT id FROM users WHERE real_name = ?", (nom_normalise,))
    result = cursor.fetchone()
    if result:
        user_id = result[0]
    else:
        user_id = str(uuid.uuid4())[:8]
        cursor.execute(
            "INSERT INTO users (id, real_name, created_at, is_premium) VALUES (?, ?, ?, ?)",
            (user_id, nom_normalise, datetime.now(), 0)
        )
        conn.commit()
    conn.close()
    return user_id

def est_premium(user_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT is_premium FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0])

def activer_premium(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE users SET is_premium = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

# ============================================================
# GESTION MESSAGES
# ============================================================
def sauvegarder_conversation(user_id: str, role: str, texte: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        texte_chiffre = chiffrer(texte)
        cursor.execute(
            "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, role, texte_chiffre, datetime.now())
        )
        conn.commit()
        conn.close()
        journaliser(user_id, f"message_{role}")
    except Exception as e:
        logging.error(f"Erreur sauvegarde message : {type(e).__name__}")

def charger_historique(user_id: str) -> list:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT role, content, timestamp FROM messages WHERE user_id = ? ORDER BY message_id ASC",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "role": r[0],
                "content": dechiffrer(r[1]),
                "horodatage": str(r[2])
            }
            for r in rows
        ]
    except Exception as e:
        logging.error(f"Erreur chargement historique : {type(e).__name__}")
        return []

def compter_messages(user_id: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT COUNT(*) FROM messages WHERE user_id = ? AND role = 'user'",
        (user_id,)
    )
    nb = c.fetchone()[0]
    c.execute(
        "SELECT MIN(timestamp), MAX(timestamp) FROM messages WHERE user_id = ?",
        (user_id,)
    )
    dates = c.fetchone()
    conn.close()
    return {
        "nb_messages": nb,
        "premiere_session": str(dates[0])[:10] if dates[0] else "Aujourd'hui",
        "derniere_session": str(dates[1])[:10] if dates[1] else "Maintenant"
    }

def compter_messages_aujourdhui(user_id: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        """SELECT COUNT(*) FROM messages
           WHERE user_id = ? AND role = 'user'
           AND timestamp >= ?""",
        (user_id, aujourd_hui)
    )
    nb = c.fetchone()[0]
    conn.close()
    return nb

def supprimer_historique(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    journaliser(user_id, "suppression_historique")

def supprimer_compte_complet(user_id: str):
    """Supprime TOUTES les données — droit à l'oubli."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM messages WHERE user_id = ?",  (user_id,))
    c.execute("DELETE FROM profils WHERE user_id = ?",   (user_id,))
    c.execute("DELETE FROM humeurs WHERE user_id = ?",   (user_id,))
    c.execute("DELETE FROM logs_acces WHERE user_id = ?", (user_id,))
    c.execute("DELETE FROM users WHERE id = ?",          (user_id,))
    conn.commit()
    conn.close()
    logging.info(f"Compte supprimé : {user_id[:4]}****")

# ============================================================
# PROFIL PERSONNALISÉ
# ============================================================
def charger_profil(user_id: str) -> dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT * FROM profils WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        if row:
            cols = ["user_id", "prenom", "situation", "defis", "objectifs",
                    "humeur_generale", "preferences", "notes_aura", "derniere_maj"]
            return dict(zip(cols, row))
        return {}
    except Exception as e:
        logging.error(f"Erreur chargement profil : {type(e).__name__}")
        return {}

def sauvegarder_profil(user_id: str, donnees: dict):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            INSERT INTO profils
                (user_id, prenom, situation, defis, objectifs,
                 humeur_generale, preferences, notes_aura, derniere_maj)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                situation       = excluded.situation,
                defis           = excluded.defis,
                objectifs       = excluded.objectifs,
                humeur_generale = excluded.humeur_generale,
                preferences     = excluded.preferences,
                notes_aura      = excluded.notes_aura,
                derniere_maj    = excluded.derniere_maj
        """, (
            user_id,
            donnees.get("prenom", ""),
            donnees.get("situation", ""),
            donnees.get("defis", ""),
            donnees.get("objectifs", ""),
            donnees.get("humeur_generale", ""),
            donnees.get("preferences", ""),
            donnees.get("notes_aura", ""),
            datetime.now().strftime("%Y-%m-%d %H:%M")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Erreur sauvegarde profil : {type(e).__name__}")

# ============================================================
# HUMEUR
# ============================================================
def init_humeur_table():
    pass  # Déjà créée dans init_db()

def sauvegarder_humeur(user_id: str, score: int, emoji: str, note: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    note_chiffree = chiffrer(note) if note else ""
    c.execute(
        "INSERT INTO humeurs (user_id, score, emoji, note, date) VALUES (?, ?, ?, ?, ?)",
        (user_id, score, emoji, note_chiffree, datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

def charger_humeurs(user_id: str, jours: int = 7) -> list:
    from datetime import timedelta
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    depuis = (datetime.now() - timedelta(days=jours)).strftime("%Y-%m-%d")
    c.execute(
        "SELECT score, emoji, note, date FROM humeurs WHERE user_id = ? AND date >= ? ORDER BY date ASC",
        (user_id, depuis)
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "score": r[0],
            "emoji": r[1],
            "note": dechiffrer(r[2]) if r[2] else "",
            "date": r[3]
        }
        for r in rows
    ]

# ============================================================
# LOGS (sans données personnelles)
# ============================================================
def journaliser(user_id: str, action: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "INSERT INTO logs_acces (user_id, action, timestamp) VALUES (?, ?, ?)",
            (user_id, action, datetime.now())
        )
        conn.commit()
        conn.close()
    except:
        pass

# ============================================================
# RATE LIMITING
# ============================================================
LIMITE_GRATUIT = 10
LIMITE_PREMIUM = 9999

def verifier_limite_messages(user_id: str) -> tuple[bool, int, int]:
    """Retourne (autorisé, nb_utilisé, limite)."""
    premium = est_premium(user_id)
    limite  = LIMITE_PREMIUM if premium else LIMITE_GRATUIT
    nb      = compter_messages_aujourdhui(user_id)
    return (nb < limite, nb, limite)