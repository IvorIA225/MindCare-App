import streamlit as st
import requests
import os
import random
import json
import logging
import pandas as pd
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime, timedelta
from database import (
    init_db, obtenir_ou_creer_id_anonyme, sauvegarder_conversation,
    charger_historique, supprimer_historique, compter_messages,
    verifier_limite_messages, incrementer_compteur_quotidien,
    charger_profil, sauvegarder_profil, est_premium, journaliser,
    valider_prenom, compter_utilisateurs, beta_pleine, LIMITE_BETA,
    supprimer_compte_complet, sauvegarder_feedback,
    a_deja_donne_feedback_aujourd_hui, nettoyer_messages_corrompus,
    obtenir_id_par_prenom, verifier_pin, definir_pin,
    utilisateur_a_un_pin,
)
from dashboard import afficher_dashboard

load_dotenv()
init_db()

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("aura_errors.log")]
)

# ============================================================
# 1. CONFIGURATION
# ============================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    st.error("❌ Clé API Groq manquante.")
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

# ============================================================
# 2. SALUTATION
# ============================================================
def salutation_heure() -> str:
    h = datetime.now().hour
    if 5 <= h < 12:    return "Bonjour"
    elif 12 <= h < 18: return "Salut"
    elif 18 <= h < 22: return "Bonsoir"
    else:              return "Salut"

# ============================================================
# 3. PROMPT
# ============================================================
SYSTEM_PROMPT_BASE = """Tu es Aura, assistant de bien-être dédiée aux étudiants de Côte d'Ivoire.

## PERSONNALITÉ
- Chaleureuse, empathique, grand frère bienveillant
- Expressions africaines douces si appropriées
- Direct, doux, humour léger si possible

## RÈGLES
1. Valide les émotions AVANT de conseiller
2. UNE seule question à la fois
3. 3-4 phrases maximum
4. Prénom obligatoire dans la réponse
5. Jamais de diagnostic médical
6. Adapte ta salutation à l'heure actuelle

## URGENCES
Pensées suicidaires → 110/111 · 185 · 180

Tu parles TOUJOURS en français."""


def construire_prompt(prenom: str, profil: dict) -> str:
    sal  = salutation_heure()
    base = SYSTEM_PROMPT_BASE + f"\n\nHeure : {datetime.now().strftime('%H:%M')}. Salutation : '{sal}'."
    if not profil:
        return base + f"\n\nL'étudiant(e) s'appelle {prenom}."
    return base + f"""

## MÉMOIRE DE {prenom.upper()}
- Situation       : {profil.get('situation','?')}
- Défis           : {profil.get('defis','?')}
- Objectifs       : {profil.get('objectifs','?')}
- Humeur générale : {profil.get('humeur_generale','?')}
- Préférences     : {profil.get('preferences','?')}
- Notes Aura      : {profil.get('notes_aura','aucune')}
- Dernière session: {profil.get('derniere_maj','?')}"""

# ============================================================
# 4. MISE À JOUR PROFIL IA
# ============================================================
def mettre_a_jour_profil_ia(user_id, prenom, historique, profil):
    if len(historique) < 4:
        return
    try:
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"""
Extrais les infos importantes. JSON uniquement, aucun texte autour :
{{"situation":"...","defis":"...","objectifs":"...","humeur_generale":"...","preferences":"...","notes_aura":"..."}}
Profil actuel : {json.dumps(profil, ensure_ascii=False)}
Échanges : {json.dumps(historique[-6:], ensure_ascii=False)}"""}],
            temperature=0.1, max_tokens=300,
        )
        t = r.choices[0].message.content.strip()
        d = json.loads(t[t.find("{"):t.rfind("}")+1])
        d["prenom"] = prenom
        sauvegarder_profil(user_id, d)
    except Exception as e:
        logging.error(f"Erreur profil IA : {type(e).__name__}")

# ============================================================
# 5. EXERCICES
# ============================================================
EXERCICES = {
    "Respiration 4-7-8": {
        "description": "Calme l'anxiété en 2 minutes.",
        "etapes": [
            ("Inspire", 4,  "Inspire lentement par le nez... 1, 2, 3, 4"),
            ("Retiens", 7,  "Retiens ton souffle... 1 à 7"),
            ("Expire",  8,  "Expire lentement par la bouche... 1 à 8"),
        ], "repetitions": 4, "couleur": "#075e54"
    },
    "Ancrage 5-4-3-2-1": {
        "description": "Reviens au moment présent.",
        "etapes": [
            ("👁️ Vois",   15, "Nomme 5 choses que tu vois..."),
            ("✋ Touche", 15, "Touche 4 objets, sens leur texture..."),
            ("👂 Écoute", 15, "Identifie 3 sons..."),
            ("👃 Sens",   10, "Repère 2 odeurs..."),
            ("👅 Goûte",  10, "1 goût dans ta bouche..."),
        ], "repetitions": 1, "couleur": "#128c7e"
    },
    "Gratitude (3 min)": {
        "description": "Change ta perspective.",
        "etapes": [
            ("Pense",   30, "3 choses positives d'aujourd'hui..."),
            ("Ressens", 30, "Ressens la gratitude..."),
            ("Retiens", 20, "Grave ces moments..."),
        ], "repetitions": 1, "couleur": "#25d366"
    },
    "Pomodoro": {
        "description": "Travaille mieux, procrastine moins.",
        "etapes": [
            ("Prépare",   60,   "Pose ton téléphone, ouvre ton cours..."),
            ("Travaille", 1500, "UNE seule tâche — 25 min !"),
            ("Repose",    300,  "Pause ! Lève-toi, bouge..."),
        ], "repetitions": 4, "couleur": "#075e54"
    }
}

# ============================================================
# 6. FONCTIONS IA
# ============================================================
def obtenir_reponse(historique: list, prenom: str, profil: dict) -> str:
    # Filtrer l'historique avant envoi à Groq
    historique_propre = [
        {"role": m["role"], "content": m["content"]}
        for m in historique
        if (m.get("role") in ("user", "assistant")
            and m.get("content")
            and m["content"] not in ("user", "assistant")
            and len(m["content"].strip()) >= 2)
    ]
    if not historique_propre:
        return f"{salutation_heure()} {prenom} ✨ Comment puis-je t'aider aujourd'hui ?"
    try:
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": construire_prompt(prenom, profil)}] + historique_propre,
            temperature=0.75, max_tokens=400,
        )
        return r.choices[0].message.content
    except Exception as e:
        logging.error(f"Erreur Groq : {type(e).__name__} — {e}")
        return "Je suis désolée, une erreur technique s'est produite. 🙏"

def transcrire_audio(fichier_audio) -> str:
    try:
        t = client.audio.transcriptions.create(
            model="whisper-large-v3", file=fichier_audio, language="fr"
        )
        return t.text
    except Exception as e:
        logging.error(f"Erreur transcription : {type(e).__name__}")
        return ""

# ============================================================
# 7. BULLES WHATSAPP
# ============================================================
def bulle_bot(texte: str, heure: str = None):
    heure = heure or datetime.now().strftime("%H:%M")
    th    = texte.replace("\n\n","<br><br>").replace("\n","<br>")
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-start;margin:2px 0;padding:0 8px;">
      <div style="
        background:#fff;border-radius:0 8px 8px 8px;
        padding:8px 10px 4px;max-width:78%;min-width:80px;
        font-family:'Segoe UI',sans-serif;font-size:14.5px;
        line-height:1.55;color:#111;
        box-shadow:0 1px 2px rgba(0,0,0,0.13);word-wrap:break-word;">
        {th}
        <div style="font-size:11px;color:#999;text-align:right;margin-top:3px;">{heure}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

def bulle_user(texte: str, heure: str = None, est_vocal: bool = False):
    heure = heure or datetime.now().strftime("%H:%M")
    th    = texte.replace("\n\n","<br><br>").replace("\n","<br>")
    icone = "🎤 " if est_vocal else ""
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-end;margin:2px 0;padding:0 8px;">
      <div style="
        background:#dcf8c6;border-radius:8px 0 8px 8px;
        padding:8px 10px 4px;max-width:78%;min-width:80px;
        font-family:'Segoe UI',sans-serif;font-size:14.5px;
        line-height:1.55;color:#111;
        box-shadow:0 1px 2px rgba(0,0,0,0.13);word-wrap:break-word;">
        {icone}{th}
        <div style="display:flex;align-items:center;justify-content:flex-end;gap:3px;margin-top:3px;">
          <span style="font-size:11px;color:#999;">{heure}</span>
          <span style="color:#4fc3f7;font-size:13px;">✓✓</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

def separateur_date(label: str):
    st.markdown(f"""
    <div style="display:flex;justify-content:center;margin:10px 0 6px;">
      <div style="background:rgba(225,245,254,0.92);color:#555;
                  font-size:12px;padding:4px 14px;border-radius:8px;
                  box-shadow:0 1px 2px rgba(0,0,0,0.08);
                  font-family:'Segoe UI',sans-serif;">{label}</div>
    </div>
    """, unsafe_allow_html=True)

def message_securite():
    st.markdown("""
    <div style="display:flex;justify-content:center;margin:8px 8px 4px;">
      <div style="background:#fff9c4;border-radius:8px;padding:9px 16px;
                  font-size:12.5px;color:#7a6a00;text-align:center;
                  max-width:85%;box-shadow:0 1px 2px rgba(0,0,0,0.08);
                  font-family:'Segoe UI',sans-serif;line-height:1.5;">
        🔒 Tes messages sont chiffrés. Aura est un prototype confidentiel.
      </div>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 8. PAGE EXERCICES
# ============================================================
def afficher_exercices():
    st.markdown("""
    <div style="background:#075e54;border-radius:0;padding:14px 20px;
                margin:-20px -24px 16px;">
        <h2 style="color:#fff;margin:0;font-size:1.1rem;
                   font-family:'Segoe UI',sans-serif;">🧘 Exercices guidés</h2>
        <p style="color:#b2dfdb;margin:2px 0 0;font-size:0.8rem;">
            Techniques pour ton bien-être quotidien</p>
    </div>
    """, unsafe_allow_html=True)

    choix   = st.selectbox("Choisis :", list(EXERCICES.keys()))
    ex      = EXERCICES[choix]
    couleur = ex["couleur"]

    st.markdown(f"""
    <div style="background:#fff;border-radius:8px;padding:12px 16px;
                margin:10px 0;box-shadow:0 1px 3px rgba(0,0,0,0.1);
                border-left:4px solid {couleur};">
        <strong style="color:{couleur};font-size:14px;">{choix}</strong><br>
        <span style="font-size:13px;color:#555;">{ex['description']}</span><br>
        <span style="font-size:12px;color:#999;">
            {ex['repetitions']} répétition(s) · {len(ex['etapes'])} étapes
        </span>
    </div>
    """, unsafe_allow_html=True)

    for k, v in {"ex_actif":False,"ex_etape":0,"ex_rep":0}.items():
        if k not in st.session_state:
            st.session_state[k] = v

    if not st.session_state.ex_actif:
        if st.button("▶️ Commencer", use_container_width=True):
            st.session_state.ex_actif = True
            st.session_state.ex_etape = 0
            st.session_state.ex_rep   = 0
            st.session_state.ex_choix = choix
            st.rerun()
    else:
        ex_c   = EXERCICES.get(st.session_state.get("ex_choix", choix), ex)
        etapes = ex_c["etapes"]
        ei, ri = st.session_state.ex_etape, st.session_state.ex_rep
        if ei < len(etapes):
            nom, duree, instruction = etapes[ei]
            st.progress((ei + ri * len(etapes)) / (len(etapes) * ex_c["repetitions"]))
            st.markdown(f"""
            <div style="text-align:center;padding:22px 16px;background:#fff;
                        border-radius:10px;margin:10px 0;
                        box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                <div style="font-size:1.8rem;margin-bottom:6px;">{nom}</div>
                <div style="font-size:13.5px;color:#555;line-height:1.6;
                            max-width:300px;margin:0 auto;">{instruction}</div>
                <div style="font-size:2.4rem;font-weight:700;color:{couleur};
                            margin-top:10px;">{duree}s</div>
                <div style="font-size:12px;color:#999;margin-top:4px;">
                    Répétition {ri+1}/{ex_c['repetitions']}</div>
            </div>
            """, unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            with c1:
                if st.button("⏭️ Suivant", use_container_width=True):
                    st.session_state.ex_etape += 1
                    if st.session_state.ex_etape >= len(etapes):
                        st.session_state.ex_rep  += 1
                        st.session_state.ex_etape = 0
                    st.rerun()
            with c2:
                if st.button("⏹️ Arrêter", use_container_width=True):
                    st.session_state.ex_actif = False
                    st.rerun()
        else:
            st.balloons()
            st.success("🎉 Bravo ! Exercice terminé !")
            if st.button("🔄 Recommencer", use_container_width=True):
                st.session_state.ex_actif = False
                st.rerun()

# ============================================================
# 9. FEEDBACK
# ============================================================
def afficher_feedback(user_id: str):
    if a_deja_donne_feedback_aujourd_hui(user_id):
        return
    st.markdown("""
    <div style="background:#fff;border-radius:8px;padding:14px 16px;
                margin:12px 0;box-shadow:0 1px 3px rgba(0,0,0,0.1);
                border-left:4px solid #25d366;">
        <div style="font-size:14px;font-weight:700;color:#075e54;margin-bottom:3px;">
            💬 Ton avis nous aide !</div>
        <div style="font-size:13px;color:#555;">
            Aura t'a-t-il été utile lors de cette session ?</div>
    </div>
    """, unsafe_allow_html=True)
    utile = st.radio(
        "Utile ?",
        ["✅ Oui, vraiment !", "🤔 Un peu", "❌ Pas vraiment"],
        horizontal=True
    )
    commentaire = st.text_area(
        "Comment t'a-t-il aidé ?",
        placeholder="Ex: J'ai pu parler de mon stress et me sentir mieux...",
        height=70
    )
    prix = st.select_slider(
        "Combien paierais-tu par mois à l'avenir ?",
        options=["0 FCFA","500 FCFA","1 000 FCFA","2 000 FCFA","3 000 FCFA","+ de 3 000 FCFA"]
    )
    if st.button("📤 Envoyer mon avis", use_container_width=True):
        sauvegarder_feedback(user_id, utile, commentaire, prix)
        st.success("Merci ! 🙏")
        st.rerun()

# ============================================================
# 10. CONFIG PAGE
# ============================================================
st.set_page_config(
    page_title="Aura", page_icon="✨",
    layout="wide", initial_sidebar_state="expanded"
)

# ============================================================
# 11. CSS WHATSAPP
# ============================================================
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
.stApp {
    background-color: #eae6df !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'%3E%3Cg fill='%23c8bdb0' fill-opacity='0.12'%3E%3Ccircle cx='25' cy='25' r='5'/%3E%3Ccircle cx='75' cy='25' r='3'/%3E%3Ccircle cx='125' cy='25' r='5'/%3E%3Ccircle cx='175' cy='25' r='3'/%3E%3Ccircle cx='50' cy='50' r='3'/%3E%3Ccircle cx='100' cy='50' r='6'/%3E%3Ccircle cx='150' cy='50' r='3'/%3E%3Ccircle cx='25' cy='75' r='3'/%3E%3Ccircle cx='75' cy='75' r='6'/%3E%3Ccircle cx='125' cy='75' r='3'/%3E%3Ccircle cx='175' cy='75' r='5'/%3E%3Ccircle cx='25' cy='125' r='5'/%3E%3Ccircle cx='75' cy='125' r='3'/%3E%3Ccircle cx='125' cy='125' r='5'/%3E%3Ccircle cx='175' cy='125' r='3'/%3E%3Ccircle cx='50' cy='150' r='3'/%3E%3Ccircle cx='100' cy='150' r='5'/%3E%3Ccircle cx='150' cy='150' r='3'/%3E%3C/g%3E%3C/svg%3E") !important;
}
.main .block-container { padding: 0 !important; max-width: 100% !important; }

/* ── SIDEBAR — bouton hamburger mobile ── */
section[data-testid="stSidebar"] {
    background: #075e54 !important;
    min-width: 210px !important;
    max-width: 210px !important;
    transition: all 0.3s ease !important;
}

/* Afficher le bouton collapse natif de Streamlit sur mobile */
@media (max-width: 768px) {
    [data-testid="stSidebarCollapseButton"] {
        display: flex !important;
        background: #075e54 !important;
        color: #fff !important;
        border: none !important;
        position: fixed !important;
        top: 10px !important;
        left: 10px !important;
        z-index: 9999 !important;
        width: 36px !important;
        height: 36px !important;
        border-radius: 50% !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 2px 6px rgba(0,0,0,0.3) !important;
    }
    [data-testid="stSidebarCollapseButton"] svg {
        fill: #fff !important;
    }
    section[data-testid="stSidebar"] {
        min-width: 100vw !important;
        max-width: 100vw !important;
    }
}

/* Sur PC : cacher le bouton collapse */
@media (min-width: 769px) {
    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"] {
        display: none !important;
    }
}
            
.stat-box {
    background:rgba(0,0,0,0.15);border-radius:6px;
    padding:9px 12px;margin:4px 10px;font-size:11px;
    color:#b2dfdb !important;line-height:1.9;
}

.wa-topbar {
    background:#075e54;padding:9px 16px;
    display:flex;align-items:center;gap:12px;
    position:sticky;top:0;z-index:200;
    box-shadow:0 2px 4px rgba(0,0,0,0.2);
}
.wa-avatar {
    width:38px;height:38px;border-radius:50%;
    background:linear-gradient(135deg,#25d366,#128c7e);
    display:flex;align-items:center;justify-content:center;
    font-size:17px;flex-shrink:0;
}
.wa-name   { font-size:15px;font-weight:600;color:#fff;font-family:'Segoe UI',sans-serif; }
.wa-status { font-size:12px;color:#b2dfdb;font-family:'Segoe UI',sans-serif; }

.messages-container { padding:4px 0;min-height:60vh; }

[data-testid="stChatMessage"] {
    background:transparent !important;border:none !important;
    box-shadow:none !important;padding:0 !important;margin:0 !important;
}
[data-testid="stChatMessage"] > div { background:transparent !important; }

div[data-testid="stChatInput"] {
    background:#f0f0f0 !important;border:none !important;
    border-top:1px solid #ddd !important;border-radius:0 !important;
    box-shadow:none !important;padding:8px 12px !important;
}
div[data-testid="stChatInput"] > div {
    background:transparent !important;border:none !important;
    box-shadow:none !important;padding:0 !important;
    display:flex !important;align-items:center !important;gap:8px !important;
}
div[data-testid="stChatInput"] textarea {
    font-family:'Segoe UI',sans-serif !important;font-size:15px !important;
    color:#111 !important;background:#fff !important;
    border:none !important;border-radius:22px !important;
    padding:10px 16px !important;min-height:44px !important;
    box-shadow:0 1px 2px rgba(0,0,0,0.1) !important;resize:none !important;
}
div[data-testid="stChatInput"] textarea::placeholder { color:#999 !important;font-size:14px !important; }
div[data-testid="stChatInput"] button {
    background:#25d366 !important;border-radius:50% !important;
    width:44px !important;height:44px !important;min-width:44px !important;
    box-shadow:0 2px 4px rgba(0,0,0,0.2) !important;
    border:none !important;flex-shrink:0 !important;
}
div[data-testid="stChatInput"] button:hover { background:#128c7e !important; }
div[data-testid="stChatInput"] button svg { fill:#fff !important;width:20px !important;height:20px !important; }

.login-bg { min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px; }
.login-card {
    background:#fff;border-radius:10px;padding:0;
    max-width:420px;width:100%;
    box-shadow:0 4px 20px rgba(0,0,0,0.12);overflow:hidden;
}
.login-top {
    background:#075e54;padding:28px 20px 20px;text-align:center;
}
.login-body { padding:24px 28px; }

.page-content { padding:14px 18px; }
.stAlert { border-radius:8px !important; }
::-webkit-scrollbar { width:4px; }
::-webkit-scrollbar-thumb { background:#c8b8a2;border-radius:10px; }

@media (max-width:768px) {
    section[data-testid="stSidebar"] { min-width:100% !important;max-width:100% !important; }
    .wa-topbar { padding:7px 10px; }
    .wa-name { font-size:14px; }
    div[data-testid="stChatInput"] { padding:6px 8px !important; }
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 12. SESSION STATE
# ============================================================
defaults = {
    "user_id": None, "prenom": None, "messages": [],
    "conversation_initiee": False, "page": "💬 Chat",
    "profil": {}, "ex_actif": False, "ex_etape": 0, "ex_rep": 0,
    "transcription_en_attente": "", "session_messages_count": 0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# 13. LOGIN — avec PIN sécurisé
# ============================================================
if st.session_state.user_id is None:
    nb_users         = compter_utilisateurs()
    places_restantes = LIMITE_BETA - nb_users

    st.markdown('<div class="login-bg">', unsafe_allow_html=True)
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown(f"""
        <div class="login-card">
          <div class="login-top">
            <div style="font-size:44px;margin-bottom:6px;">✨</div>
            <div style="font-size:1.7rem;font-weight:700;color:#fff;">Aura</div>
            <div style="font-size:12px;color:#b2dfdb;margin-top:4px;">
                Coach de bien-être pour les étudiants
            </div>
          </div>
          <div class="login-body">
            <div style="background:#e8f5e9;border-radius:6px;padding:7px 12px;
                        margin-bottom:16px;font-size:12px;color:#2e7d32;text-align:center;">
                🧪 Bêta · {nb_users}/{LIMITE_BETA} participants
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        if beta_pleine():
            st.error(f"🔒 Bêta complète ({LIMITE_BETA} participants).")
            st.text_input("Contact WhatsApp :", placeholder="+225 07 00 00 00 00")
            st.button("📩 Liste d'attente", use_container_width=True)
        else:
            sal = salutation_heure()
            st.markdown(f"**{sal} !**")

            prenom_input = st.text_input(
                "👤 Ton prénom :",
                placeholder="Ex: Aminata",
                key="login_prenom"
            )

            # Vérifier si cet utilisateur existe déjà
            utilisateur_existant = False
            uid_existant         = None
            if prenom_input.strip() and valider_prenom(prenom_input.strip()):
                uid_existant = obtenir_id_par_prenom(prenom_input.strip())
                utilisateur_existant = uid_existant is not None

            if utilisateur_existant:
                # ── UTILISATEUR EXISTANT — demander le PIN ──
                st.markdown(f"""
                <div style="background:#e8f5e9;border-radius:8px;padding:9px 14px;
                            font-size:13px;color:#2e7d32;margin:8px 0;
                            border-left:3px solid #25d366;">
                    👋 Bon retour <strong>{prenom_input.strip().capitalize()}</strong> !
                    Entre ton code PIN pour accéder à tes conversations.
                </div>
                """, unsafe_allow_html=True)

                pin_input = st.text_input(
                    "🔐 Code PIN (4 chiffres) :",
                    type="password",
                    max_chars=4,
                    placeholder="••••",
                    key="login_pin_existant"
                )

                if st.button("🔓 Se connecter", use_container_width=True):
                    if not pin_input or len(pin_input) != 4 or not pin_input.isdigit():
                        st.error("Le PIN doit contenir exactement 4 chiffres.")
                    elif not verifier_pin(uid_existant, pin_input):
                        st.error("❌ Code PIN incorrect. Réessaie.")
                        journaliser(uid_existant, "tentative_pin_echouee")
                    else:
                        # ✅ PIN correct — connexion
                        st.session_state.user_id  = uid_existant
                        st.session_state.prenom   = prenom_input.strip().capitalize()
                        st.session_state.profil   = charger_profil(uid_existant)
                        historique = charger_historique(uid_existant)
                        if historique:
                            st.session_state.messages = historique
                            st.session_state.conversation_initiee = True
                        journaliser(uid_existant, "connexion")
                        st.rerun()

                st.markdown("""
                <div style="font-size:11px;color:#999;text-align:center;margin-top:8px;">
                    PIN oublié ? Contacte le support Aura.
                </div>
                """, unsafe_allow_html=True)

            else:
                # ── NOUVEL UTILISATEUR — créer un compte avec PIN ──
                if prenom_input.strip():
                    st.markdown("""
                    <div style="background:#fff3e0;border-radius:8px;padding:9px 14px;
                                font-size:13px;color:#e65100;margin:8px 0;
                                border-left:3px solid #ff9800;">
                        ✨ Nouveau sur Aura ? Crée ton accès sécurisé.
                    </div>
                    """, unsafe_allow_html=True)

                pin_nouveau = st.text_input(
                    "🔐 Crée ton code PIN (4 chiffres) :",
                    type="password",
                    max_chars=4,
                    placeholder="••••",
                    key="login_pin_nouveau"
                )
                pin_confirm = st.text_input(
                    "🔐 Confirme ton code PIN :",
                    type="password",
                    max_chars=4,
                    placeholder="••••",
                    key="login_pin_confirm"
                )

                consentement = st.checkbox(
                    "Je comprends que cet outil est un **prototype expérimental** et j'accepte "
                    "que mes données soient traitées de façon **anonyme** et utilisées à des fins "
                    "de **recherche et d'amélioration** de Aura."
                )

                st.info("📱 **Sur mobile :** Menu → *Ajouter à l'écran d'accueil*")

                if st.button("✨ Créer mon compte", use_container_width=True):
                    if not prenom_input.strip():
                        st.error("Entre ton prénom.")
                    elif not valider_prenom(prenom_input.strip()):
                        st.error("Prénom invalide (lettres uniquement, 2-50 caractères).")
                    elif not pin_nouveau or len(pin_nouveau) != 4 or not pin_nouveau.isdigit():
                        st.error("Le PIN doit contenir exactement 4 chiffres.")
                    elif pin_nouveau != pin_confirm:
                        st.error("Les deux PIN ne correspondent pas.")
                    elif not consentement:
                        st.warning("⚠️ Tu dois accepter les conditions pour continuer.")
                    else:
                        try:
                            uid = obtenir_ou_creer_id_anonyme(
                                prenom_input.strip(), consentement=True
                            )
                            definir_pin(uid, pin_nouveau)
                            st.session_state.user_id  = uid
                            st.session_state.prenom   = prenom_input.strip().capitalize()
                            st.session_state.profil   = charger_profil(uid)
                            st.session_state.messages = []
                            st.session_state.conversation_initiee = False
                            journaliser(uid, "inscription")
                            st.rerun()
                        except OverflowError:
                            st.error(f"🔒 Bêta complète ({LIMITE_BETA} participants).")
                        except ValueError as e:
                            st.error(str(e))
                        except Exception as e:
                            logging.error(f"Erreur inscription : {type(e).__name__} — {e}")
                            st.error("Une erreur est survenue. Réessaie.")

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ============================================================
# 14. VARIABLES
# ============================================================
prenom = st.session_state.prenom
profil = st.session_state.profil

# ============================================================
# 15. TOPBAR
# ============================================================
nb_users = compter_utilisateurs()
st.markdown(f"""
<div class="wa-topbar">
  <div class="wa-avatar">✨</div>
  <div style="flex:1;">
    <div class="wa-name">Aura</div>
    <div class="wa-status">
      <span style="display:inline-block;width:6px;height:6px;border-radius:50%;
                   background:#25d366;margin-right:4px;"></span>En ligne
    </div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:11px;color:#b2dfdb;">👤 {prenom}</div>
    <div style="font-size:10px;color:#80cbc4;">🧪 {nb_users}/{LIMITE_BETA}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 16. SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown(f"""
    <div class="sb-header">
        <div class="sb-title">✨ AURA</div>
        <div class="sb-sub">Coach de bien-être<br>pour les étudiants</div>
        <div class="sb-user">
            <span style="display:inline-block;width:7px;height:7px;
                         border-radius:50%;background:#25d366;"></span>
            {prenom}
        </div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio("", ["💬 Chat","🧘 Exercices","📊 Tableau de bord"], label_visibility="collapsed")
    st.session_state.page = page

    st.markdown("<hr>", unsafe_allow_html=True)
    ca, cb = st.columns(2)
    with ca:
        if st.button("🗑️ Nouveau", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_initiee = False
            st.session_state.session_messages_count = 0
            st.rerun()
    with cb:
        if st.button("🚪 Changer", use_container_width=True):
            for k in ["user_id","prenom","messages","conversation_initiee","profil"]:
                st.session_state[k] = None if k != "messages" else []
            st.session_state.conversation_initiee = False
            st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)
    stats = compter_messages(st.session_state.user_id)
    _, nb_today, limite = verifier_limite_messages(st.session_state.user_id)
    st.markdown(f"""
    <div class="stat-box">
        💬 {stats['nb_messages']} messages total<br>
        📅 {stats['premiere_session']}<br>
        🕐 {stats['derniere_session']}<br>
        📊 Aujourd'hui : {nb_today}/{limite}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    if st.button("🗑️ Effacer historique", use_container_width=True):
        supprimer_historique(st.session_state.user_id)
        st.session_state.messages = []
        st.session_state.conversation_initiee = False
        st.success("Effacé ✓")
        st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("""
    <div style="padding:0 10px 10px;">
        <div style="font-size:10px;color:#80cbc4;font-weight:700;
                    text-transform:uppercase;letter-spacing:1px;margin-bottom:7px;">
            🆘 URGENCES CI</div>
        <div style="font-size:12.5px;color:#e0f2f1;line-height:2.2;">
            📞 <strong style="color:#fff;">110/111</strong> Police<br>
            🚑 <strong style="color:#fff;">185</strong> SAMU<br>
            🔥 <strong style="color:#fff;">180</strong> Pompiers
        </div>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 17. ROUTEUR
# ============================================================
page = st.session_state.page

if page == "🧘 Exercices":
    st.markdown('<div class="page-content">', unsafe_allow_html=True)
    afficher_exercices()
    afficher_feedback(st.session_state.user_id)
    st.markdown('</div>', unsafe_allow_html=True)

elif page == "📊 Tableau de bord":
    st.markdown('<div class="page-content">', unsafe_allow_html=True)
    afficher_dashboard(st.session_state.user_id, prenom)
    afficher_feedback(st.session_state.user_id)
    st.markdown('</div>', unsafe_allow_html=True)

else:
    # ── CHAT ──
    sal = salutation_heure()

    # ✅ MESSAGE DE BIENVENUE — logique corrigée
    if not st.session_state.conversation_initiee:
        historique_bdd = charger_historique(st.session_state.user_id)

        if historique_bdd:
            # Utilisateur qui revient — on affiche son historique tel quel
            st.session_state.messages = historique_bdd
            st.session_state.conversation_initiee = True
            # Petit message de retour affiché visuellement seulement
            st.session_state.message_retour = f"Content(e) de te revoir, {prenom} 👋"
        else:
            # Nouvel utilisateur — message de bienvenue
            msg_bienvenue = (
                f"{sal} {prenom} ✨\n\n"
                f"Je suis **Aura**, ton espace de bien-être personnalisé dédié "
                f"à tous les étudiants de Côte d'Ivoire. Je suis là pour t'écouter, "
                f"sans jugement et en toute confidentialité.\n\n"
                f"Tu as franchi une étape importante pour ton bien-être. "
                f"Comment puis-je t'aider aujourd'hui ?\n\n"
                f"Tu peux aussi explorer les exercices ou ton tableau de bord."
            )
            # ✅ Sauvegarde dans la BDD avec le bon ordre
            sauvegarder_conversation(st.session_state.user_id, "assistant", msg_bienvenue)
            st.session_state.messages = [
                {"role": "assistant", "content": msg_bienvenue,
                 "horodatage": datetime.now().strftime("%H:%M")}
            ]
            st.session_state.conversation_initiee = True
            st.session_state.message_retour = None

    # ── Affichage messages ──
    st.markdown('<div class="messages-container">', unsafe_allow_html=True)
    message_securite()

    dates_affichees = set()
    for m in st.session_state.messages:
        h      = m.get("horodatage", "")
        # Extraction heure propre
        if len(h) >= 16:   heure = h[11:16];  date_msg = h[:10]
        elif len(h) == 5:  heure = h;          date_msg = datetime.now().strftime("%Y-%m-%d")
        else:              heure = datetime.now().strftime("%H:%M"); date_msg = datetime.now().strftime("%Y-%m-%d")

        # Séparateur de date
        if date_msg not in dates_affichees:
            dates_affichees.add(date_msg)
            try:
                d   = datetime.strptime(date_msg, "%Y-%m-%d").date()
                ajd = datetime.now().date()
                label = "Aujourd'hui" if d == ajd else ("Hier" if d == ajd - timedelta(days=1) else d.strftime("%d %B %Y"))
            except:
                label = date_msg
            separateur_date(label)

        # ✅ Ignorer les entrées corrompues à l'affichage
        contenu = m.get("content", "")
        if (not contenu
                or contenu in ("user", "assistant")
                or len(contenu.strip()) < 2):
            continue

        if m["role"] == "assistant":
            bulle_bot(contenu, heure)
        else:
            bulle_user(contenu, heure, est_vocal=m.get("vocal", False))

    # Message de retour discret
    if st.session_state.get("message_retour"):
        separateur_date(st.session_state.message_retour)
        st.session_state.message_retour = None

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Zone vocale ──
    st.markdown("""
    <div style="background:#f0f0f0;border-top:1px solid #e0e0e0;padding:7px 12px;">
        <span style="font-size:12px;color:#666;">🎤 Note vocale — parle directement à Aura</span>
    </div>
    """, unsafe_allow_html=True)

    audio_file = st.audio_input("Enregistre", label_visibility="collapsed", key="audio_input")

    if audio_file is not None:
        with st.spinner("🎤 Transcription..."):
            texte_transcrit = transcrire_audio(audio_file)
        if texte_transcrit:
            st.markdown(f"""
            <div style="background:#e8f5e9;border-radius:8px;padding:9px 14px;
                        font-size:13px;color:#2e7d32;margin:4px 12px;
                        border-left:3px solid #25d366;">
                📝 <em>"{texte_transcrit}"</em>
            </div>
            """, unsafe_allow_html=True)
            st.session_state.transcription_en_attente = texte_transcrit
            if st.button("✅ Envoyer ce message vocal", use_container_width=True):
                prompt = st.session_state.transcription_en_attente
                st.session_state.transcription_en_attente = ""
                autorise, _, lim = verifier_limite_messages(st.session_state.user_id)
                if not autorise:
                    st.warning(f"⚠️ Limite {lim} messages/jour atteinte.")
                else:
                    heure_now = datetime.now().strftime("%H:%M")
                    sauvegarder_conversation(st.session_state.user_id, "user", prompt)
                    incrementer_compteur_quotidien(st.session_state.user_id)
                    st.session_state.messages.append(
                        {"role":"user","content":prompt,"horodatage":heure_now,"vocal":True}
                    )
                    st.session_state.session_messages_count += 1
                    hg = [{"role":m["role"],"content":m["content"]} for m in st.session_state.messages if m.get("content") not in ("user","assistant")]
                    with st.spinner(""):
                        rep = obtenir_reponse(hg, prenom, profil)
                    heure_rep = datetime.now().strftime("%H:%M")
                    sauvegarder_conversation(st.session_state.user_id, "assistant", rep)
                    st.session_state.messages.append({"role":"assistant","content":rep,"horodatage":heure_rep})
                    if len(st.session_state.messages) % 10 == 0:
                        mettre_a_jour_profil_ia(st.session_state.user_id, prenom, hg, profil)
                        st.session_state.profil = charger_profil(st.session_state.user_id)
                    st.rerun()
        else:
            st.warning("Impossible de transcrire. Écris ton message.")

    # ── Saisie texte ──
    if prompt := st.chat_input("Exprime-toi librement, je t'écoute..."):
        autorise, _, lim = verifier_limite_messages(st.session_state.user_id)
        if not autorise:
            st.warning(f"⚠️ Limite de {lim} messages/jour atteinte.")
            st.stop()

        MOTS_CRISE = ["suicid","mourir","me tuer","en finir",
                      "plus envie de vivre","automutil","me faire du mal"]
        if any(m in prompt.lower() for m in MOTS_CRISE):
            st.error("🆘 **Urgences :** 📞 110/111 · 🚑 185 · 🔥 180")

        heure_now = datetime.now().strftime("%H:%M")
        sauvegarder_conversation(st.session_state.user_id, "user", prompt)
        incrementer_compteur_quotidien(st.session_state.user_id)
        st.session_state.messages.append({"role":"user","content":prompt,"horodatage":heure_now})
        st.session_state.session_messages_count += 1

        # ✅ Historique propre envoyé à Groq
        hg = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
            if (m.get("content")
                and m["content"] not in ("user","assistant")
                and len(m["content"].strip()) >= 2)
        ]

        with st.spinner(""):
            rep = obtenir_reponse(hg, prenom, profil)

        heure_rep = datetime.now().strftime("%H:%M")
        sauvegarder_conversation(st.session_state.user_id, "assistant", rep)
        st.session_state.messages.append({"role":"assistant","content":rep,"horodatage":heure_rep})

        if len(st.session_state.messages) % 10 == 0:
            mettre_a_jour_profil_ia(st.session_state.user_id, prenom, hg, profil)
            st.session_state.profil = charger_profil(st.session_state.user_id)

        st.rerun()

    if st.session_state.session_messages_count >= 6:
        afficher_feedback(st.session_state.user_id)