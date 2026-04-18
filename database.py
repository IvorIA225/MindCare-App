import sqlite3
import uuid
import logging
import re
import hashlib
import os
from datetime import datetime
from cryptography.fernet import Fernet

DB_PATH     = "aura_data.db"
LIMITE_BETA = 50

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("aura_errors.log")]
)

# ============================================================
# CHIFFREMENT — OBLIGATOIRE
# ============================================================
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "").encode()

if not ENCRYPTION_KEY:
    raise RuntimeError(
        "❌ ENCRYPTION_KEY manquante. Générez-en une avec :\n"
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"\n"
        "Puis ajoutez-la dans votre .env ou Streamlit Secrets."
    )

fernet = Fernet(ENCRYPTION_KEY)

def chiffrer(texte: str) -> str:
    if texte:
        try:
            return fernet.encrypt(texte.encode()).decode()
        except Exception as e:
            logging.error(f"Erreur chiffrement : {e}")
    return texte

def dechiffrer(texte: str) -> str:
    if texte:
        try:
            return fernet.decrypt(texte.encode()).decode()
        except:
            return texte  # Déjà en clair ou corrompu
    return texte

# ============================================================
# VALIDATION
# ============================================================
def valider_prenom(prenom: str) -> bool:
    if not prenom or len(prenom.strip()) < 2 or len(prenom.strip()) > 50:
        return False
    return bool(re.match(r"^[a-zA-ZÀ-ÿ\s'\-]+$", prenom.strip()))

def valider_pin(pin: str) -> bool:
    return bool(pin and len(pin) == 4 and pin.isdigit())

# ============================================================
# PIN — SÉCURITÉ
# ============================================================
def hasher_pin(pin: str) -> str:
    return hashlib.sha256(pin.encode()).hexdigest()

def definir_pin(user_id: str, pin: str):
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET pin_hash = ? WHERE id = ?",
        (hasher_pin(pin), user_id)
    )
    conn.commit()
    conn.close()

def verifier_pin(user_id: str, pin: str) -> bool:
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT pin_hash FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row or not row[0]:
        return False
    return row[0] == hasher_pin(pin)

def obtenir_id_par_prenom(nom_reel: str) -> str | None:
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM users WHERE real_name = ?",
        (nom_reel.strip().capitalize(),)
    )
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

# ============================================================
# INITIALISATION BDD
# ============================================================
def init_db():
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           TEXT PRIMARY KEY,
            real_name    TEXT UNIQUE,
            created_at   TIMESTAMP,
            is_premium   INTEGER DEFAULT 0,
            consentement INTEGER DEFAULT 0,
            pin_hash     TEXT    DEFAULT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            message_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT    NOT NULL,
            role        TEXT    NOT NULL CHECK(role IN ('user','assistant')),
            content     TEXT    NOT NULL,
            timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS humeurs (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  TEXT,
            score    INTEGER,
            emoji    TEXT,
            note     TEXT,
            date     TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compteur_quotidien (
            user_id TEXT,
            date    TEXT,
            nb      INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS feedbacks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     TEXT,
            utile       TEXT,
            commentaire TEXT,
            prix_mois   TEXT,
            timestamp   TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs_acces (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   TEXT,
            action    TEXT,
            timestamp TIMESTAMP
        )
    """)

    # Migration : ajoute pin_hash si colonne absente (ancienne BDD)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN pin_hash TEXT DEFAULT NULL")
    except:
        pass

    conn.commit()
    conn.close()

# ============================================================
# NETTOYAGE DONNÉES CORROMPUES
# ============================================================
def nettoyer_messages_corrompus(user_id: str) -> int:
    conn   = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM messages
        WHERE user_id = ?
        AND (
            content IN ('user','assistant')
            OR content IS NULL
            OR content = ''
            OR length(content) < 2
        )
    """, (user_id,))
    nb = cursor.rowcount
    conn.commit()
    conn.close()
    if nb > 0:
        logging.warning(f"Nettoyage : {nb} messages corrompus supprimés pour {user_id[:4]}****")
    return nb

# ============================================================
# GESTION UTILISATEURS
# ============================================================
def compter_utilisateurs() -> int:
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("SELECT COUNT(*) FROM users")
    nb = c.fetchone()[0]
    conn.close()
    return nb

def beta_pleine() -> bool:
    return compter_utilisateurs() >= LIMITE_BETA

def obtenir_ou_creer_id_anonyme(nom_reel: str, consentement: bool = False) -> str:
    if not valider_prenom(nom_reel):
        raise ValueError("Prénom invalide")
    conn          = sqlite3.connect(DB_PATH)
    cursor        = conn.cursor()
    nom_normalise = nom_reel.strip().capitalize()
    cursor.execute("SELECT id FROM users WHERE real_name = ?", (nom_normalise,))
    result = cursor.fetchone()
    if result:
        user_id = result[0]
    else:
        if beta_pleine():
            conn.close()
            raise OverflowError("Beta complète")
        user_id = str(uuid.uuid4())[:8]
        cursor.execute(
            "INSERT INTO users (id, real_name, created_at, is_premium, consentement) VALUES (?,?,?,?,?)",
            (user_id, nom_normalise, datetime.now(), 0, int(consentement))
        )
        conn.commit()
    conn.close()
    return user_id

def est_premium(user_id: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("SELECT is_premium FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return bool(row and row[0])

# ============================================================
# MESSAGES
# ============================================================
def sauvegarder_conversation(user_id: str, role: str, texte: str):
    if role not in ("user", "assistant"):
        logging.error(f"Role invalide : '{role}'")
        return
    if not texte or not texte.strip():
        logging.error("Contenu vide — non sauvegardé")
        return
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (user_id, role, content, timestamp) VALUES (?,?,?,?)",
            (user_id, role, chiffrer(texte), datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Erreur sauvegarde : {type(e).__name__} — {e}")

def charger_historique(user_id: str) -> list:
    nettoyer_messages_corrompus(user_id)
    try:
        conn   = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT role, content, timestamp
               FROM messages
               WHERE user_id = ?
                 AND role IN ('user','assistant')
                 AND content IS NOT NULL
                 AND content != ''
                 AND content NOT IN ('user','assistant')
                 AND length(content) >= 2
               ORDER BY message_id ASC""",
            (user_id,)
        )
        rows = cursor.fetchall()
        conn.close()
        messages_valides = []
        for r in rows:
            role      = r[0]
            contenu   = dechiffrer(r[1])
            horodatage = str(r[2]) if r[2] else datetime.now().isoformat()
            if (role in ("user","assistant")
                    and contenu
                    and contenu not in ("user","assistant")
                    and len(contenu.strip()) >= 2):
                messages_valides.append({
                    "role":       role,
                    "content":    contenu,
                    "horodatage": horodatage
                })
        return messages_valides
    except Exception as e:
        logging.error(f"Erreur historique : {type(e).__name__} — {e}")
        return []

def compter_messages(user_id: str) -> dict:
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("SELECT COUNT(*) FROM messages WHERE user_id=? AND role='user'", (user_id,))
    nb = c.fetchone()[0]
    c.execute("SELECT MIN(timestamp), MAX(timestamp) FROM messages WHERE user_id=?", (user_id,))
    dates = c.fetchone()
    conn.close()
    return {
        "nb_messages":      nb,
        "premiere_session": str(dates[0])[:10] if dates[0] else "Aujourd'hui",
        "derniere_session": str(dates[1])[:10] if dates[1] else "Maintenant"
    }

def compter_messages_aujourdhui(user_id: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute(
        "SELECT nb FROM compteur_quotidien WHERE user_id=? AND date=?",
        (user_id, datetime.now().strftime("%Y-%m-%d"))
    )
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def incrementer_compteur_quotidien(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("""
        INSERT INTO compteur_quotidien (user_id, date, nb) VALUES (?,?,1)
        ON CONFLICT(user_id, date) DO UPDATE SET nb = nb + 1
    """, (user_id, datetime.now().strftime("%Y-%m-%d")))
    conn.commit()
    conn.close()

def verifier_limite_messages(user_id: str) -> tuple:
    limite = 9999 if est_premium(user_id) else 20
    nb     = compter_messages_aujourdhui(user_id)
    return (nb < limite, nb, limite)

def supprimer_historique(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute("DELETE FROM messages WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

def supprimer_compte_complet(user_id: str):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    for table in ["messages","profils","humeurs","compteur_quotidien","feedbacks","logs_acces"]:
        c.execute(f"DELETE FROM {table} WHERE user_id=?", (user_id,))
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()

# ============================================================
# PROFIL PERSONNALISÉ
# ============================================================
def charger_profil(user_id: str) -> dict:
    try:
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        c.execute("SELECT * FROM profils WHERE user_id=?", (user_id,))
        row  = c.fetchone()
        conn.close()
        if row:
            cols = ["user_id","prenom","situation","defis","objectifs",
                    "humeur_generale","preferences","notes_aura","derniere_maj"]
            return dict(zip(cols, row))
        return {}
    except:
        return {}

def sauvegarder_profil(user_id: str, donnees: dict):
    try:
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        c.execute("""
            INSERT INTO profils
                (user_id,prenom,situation,defis,objectifs,
                 humeur_generale,preferences,notes_aura,derniere_maj)
            VALUES (?,?,?,?,?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
                situation=excluded.situation,
                defis=excluded.defis,
                objectifs=excluded.objectifs,
                humeur_generale=excluded.humeur_generale,
                preferences=excluded.preferences,
                notes_aura=excluded.notes_aura,
                derniere_maj=excluded.derniere_maj
        """, (
            user_id,
            donnees.get("prenom",""),    donnees.get("situation",""),
            donnees.get("defis",""),     donnees.get("objectifs",""),
            donnees.get("humeur_generale",""), donnees.get("preferences",""),
            donnees.get("notes_aura",""), datetime.now().strftime("%Y-%m-%d %H:%M")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logging.error(f"Erreur profil : {type(e).__name__}")

# ============================================================
# HUMEUR
# ============================================================
def init_humeur_table():
    pass  # Déjà dans init_db()

def sauvegarder_humeur(user_id: str, score: int, emoji: str, note: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute(
        "INSERT INTO humeurs (user_id,score,emoji,note,date) VALUES (?,?,?,?,?)",
        (user_id, score, emoji,
         chiffrer(note) if note else "",
         datetime.now().strftime("%Y-%m-%d %H:%M"))
    )
    conn.commit()
    conn.close()

def charger_humeurs(user_id: str, jours: int = 14) -> list:
    from datetime import timedelta
    conn   = sqlite3.connect(DB_PATH)
    c      = conn.cursor()
    depuis = (datetime.now() - timedelta(days=jours)).strftime("%Y-%m-%d")
    c.execute(
        "SELECT score,emoji,note,date FROM humeurs WHERE user_id=? AND date>=? ORDER BY date ASC",
        (user_id, depuis)
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"score":r[0],"emoji":r[1],
         "note": dechiffrer(r[2]) if r[2] else "",
         "date":r[3]}
        for r in rows
    ]

# ============================================================
# FEEDBACK
# ============================================================
def sauvegarder_feedback(user_id: str, utile: str, commentaire: str, prix_mois: str):
    conn = sqlite3.connect(DB_PATH)
    c    = conn.cursor()
    c.execute(
        "INSERT INTO feedbacks (user_id,utile,commentaire,prix_mois,timestamp) VALUES (?,?,?,?,?)",
        (user_id, utile, chiffrer(commentaire) if commentaire else "", prix_mois, datetime.now())
    )
    conn.commit()
    conn.close()

def a_deja_donne_feedback_aujourd_hui(user_id: str) -> bool:
    conn        = sqlite3.connect(DB_PATH)
    c           = conn.cursor()
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    c.execute(
        "SELECT COUNT(*) FROM feedbacks WHERE user_id=? AND timestamp>=?",
        (user_id, aujourd_hui)
    )
    nb = c.fetchone()[0]
    conn.close()
    return nb > 0

# ============================================================
# LOGS
# ============================================================
def journaliser(user_id: str, action: str):
    try:
        conn = sqlite3.connect(DB_PATH)
        c    = conn.cursor()
        c.execute(
            "INSERT INTO logs_acces (user_id,action,timestamp) VALUES (?,?,?)",
            (user_id, action, datetime.now())
        )
        conn.commit()
        conn.close()
    except:
        pass