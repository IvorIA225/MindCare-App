import streamlit as st
import os
import json
import logging
import random
import pandas as pd
from groq import Groq
from dotenv import load_dotenv
load_dotenv()
from datetime import datetime, timedelta
from database import (
    init_db, obtenir_ou_creer_id_anonyme, obtenir_id_par_prenom,
    sauvegarder_conversation, charger_historique, supprimer_historique,
    compter_messages, verifier_limite_messages, incrementer_compteur_quotidien,
    charger_profil, sauvegarder_profil, est_premium, journaliser,
    valider_prenom, valider_pin, compter_utilisateurs, beta_pleine, LIMITE_BETA,
    supprimer_compte_complet, sauvegarder_feedback,
    a_deja_donne_feedback_aujourd_hui, nettoyer_messages_corrompus,
    verifier_pin, definir_pin,
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
# 1. CONFIG
# ============================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    st.error("❌ Clé API Groq manquante.")
    st.stop()

client               = Groq(api_key=GROQ_API_KEY)
DUREE_SESSION_HEURES = 2

# ============================================================
# 2. UTILITAIRES
# ============================================================
def salutation_heure() -> str:
    h = datetime.now().hour
    if 5 <= h < 12:    return "Bonjour"
    elif 12 <= h < 18: return "Bon après-midi"
    elif 18 <= h < 22: return "Bonsoir"
    else:              return "Bonne nuit"

# ============================================================
# 3. PROMPT
# ============================================================
SYSTEM_PROMPT_BASE = """Tu es Aura, assistante de bien-être
dédiée aux étudiants de Côte d'Ivoire.

## PERSONNALITÉ
- Chaleureuse, empathique, grande sœur bienveillante
- Expressions africaines douces si appropriées
- Directe, douce, humour léger si possible

## RÈGLES
1. Valide les émotions AVANT de conseiller
2. UNE seule question à la fois — 3-4 phrases max
3. Appelle l'étudiant par son prénom
4. Jamais de diagnostic médical
5. Adapte la salutation à l'heure

## URGENCES
Pensées suicidaires → 110/111 · 185 · 180

Tu parles TOUJOURS en français. Tu es Aura ✨"""

def construire_prompt(prenom: str, profil: dict) -> str:
    sal  = salutation_heure()
    base = SYSTEM_PROMPT_BASE + f"\n\nHeure:{datetime.now().strftime('%H:%M')} Salutation:'{sal}'"
    if not profil:
        return base + f"\n\nL'étudiant(e) s'appelle {prenom}."
    return base + f"""
## MÉMOIRE DE {prenom.upper()}
Situation:{profil.get('situation','?')} · Défis:{profil.get('defis','?')}
Objectifs:{profil.get('objectifs','?')} · Humeur:{profil.get('humeur_generale','?')}
Notes Aura:{profil.get('notes_aura','aucune')} · Dernière session:{profil.get('derniere_maj','?')}"""

# ============================================================
# 4. PROFIL IA
# ============================================================
def mettre_a_jour_profil_ia(user_id, prenom, historique, profil):
    if len(historique) < 4:
        return
    try:
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"user","content":f"""
Extrais les infos. JSON uniquement :
{{"situation":"...","defis":"...","objectifs":"...","humeur_generale":"...","preferences":"...","notes_aura":"..."}}
Profil:{json.dumps(profil,ensure_ascii=False)}
Échanges:{json.dumps(historique[-6:],ensure_ascii=False)}"""}],
            temperature=0.1, max_tokens=300,
        )
        t = r.choices[0].message.content.strip()
        d = json.loads(t[t.find("{"):t.rfind("}")+1])
        d["prenom"] = prenom
        sauvegarder_profil(user_id, d)
    except Exception as e:
        logging.error(f"Erreur profil IA:{type(e).__name__}")

# ============================================================
# 5. EXERCICES
# ============================================================
EXERCICES = {
    "🌬️ Respiration 4-7-8": {
        "description":"Calme l'anxiété en 2 minutes.",
        "etapes":[("Inspire",4,"Inspire lentement..."),("Retiens",7,"Retiens..."),("Expire",8,"Expire...")],
        "repetitions":4,"couleur":"#075e54"
    },
    "🌿 Ancrage 5-4-3-2-1": {
        "description":"Reviens au moment présent.",
        "etapes":[("👁️ Vois",15,"5 choses..."),("✋ Touche",15,"4 objets..."),
                  ("👂 Écoute",15,"3 sons..."),("👃 Sens",10,"2 odeurs..."),("👅 Goûte",10,"1 goût...")],
        "repetitions":1,"couleur":"#128c7e"
    },
    "🙏 Gratitude": {
        "description":"Change ta perspective.",
        "etapes":[("Pense",30,"3 choses positives..."),("Ressens",30,"Gratitude..."),("Retiens",20,"Grave...")],
        "repetitions":1,"couleur":"#25d366"
    },
    "🎯 Pomodoro": {
        "description":"Travaille mieux.",
        "etapes":[("Prépare",60,"Ouvre ton cours..."),("Travaille",1500,"25 min !"),("Repose",300,"Pause !")],
        "repetitions":4,"couleur":"#075e54"
    }
}

# ============================================================
# 6. IA & AUDIO
# ============================================================
def obtenir_reponse(historique: list, prenom: str, profil: dict) -> str:
    histo_propre = [
        {"role":m["role"],"content":m["content"]} for m in historique
        if m.get("role") in ("user","assistant") and m.get("content")
        and m["content"] not in ("user","assistant") and len(m["content"].strip())>=2
    ]
    if not histo_propre:
        return f"{salutation_heure()} {prenom} ✨ Comment puis-je t'aider ?"
    try:
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role":"system","content":construire_prompt(prenom,profil)}]+histo_propre,
            temperature=0.75, max_tokens=400,
        )
        return r.choices[0].message.content
    except Exception as e:
        logging.error(f"Erreur Groq:{type(e).__name__}")
        return "Je suis désolée, une erreur s'est produite. 🙏"

def transcrire_audio(fichier_audio) -> str:
    try:
        t = client.audio.transcriptions.create(
            model="whisper-large-v3", file=fichier_audio, language="fr"
        )
        return t.text
    except Exception as e:
        logging.error(f"Erreur transcription:{type(e).__name__}")
        return ""

# ============================================================
# 7. BULLES
# ============================================================
def bulle_bot(texte: str, heure: str = None):
    h  = heure or datetime.now().strftime("%H:%M")
    th = texte.replace("\n\n","<br><br>").replace("\n","<br>")
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-start;margin:2px 0;padding:0 8px;">
      <div style="background:#fff;border-radius:0 8px 8px 8px;padding:8px 10px 4px;
                  max-width:80%;min-width:60px;font-family:'Segoe UI',sans-serif;
                  font-size:14.5px;line-height:1.55;color:#111;
                  box-shadow:0 1px 2px rgba(0,0,0,0.13);word-wrap:break-word;">
        {th}
        <div style="font-size:11px;color:#999;text-align:right;margin-top:3px;">{h}</div>
      </div>
    </div>""", unsafe_allow_html=True)

def bulle_user(texte: str, heure: str = None, est_vocal: bool = False):
    h     = heure or datetime.now().strftime("%H:%M")
    th    = texte.replace("\n\n","<br><br>").replace("\n","<br>")
    icone = "🎤 " if est_vocal else ""
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-end;margin:2px 0;padding:0 8px;">
      <div style="background:#dcf8c6;border-radius:8px 0 8px 8px;padding:8px 10px 4px;
                  max-width:80%;min-width:60px;font-family:'Segoe UI',sans-serif;
                  font-size:14.5px;line-height:1.55;color:#111;
                  box-shadow:0 1px 2px rgba(0,0,0,0.13);word-wrap:break-word;">
        {icone}{th}
        <div style="display:flex;align-items:center;justify-content:flex-end;gap:3px;margin-top:3px;">
          <span style="font-size:11px;color:#999;">{h}</span>
          <span style="color:#4fc3f7;font-size:13px;">✓✓</span>
        </div>
      </div>
    </div>""", unsafe_allow_html=True)

def separateur_date(label: str):
    st.markdown(f"""
    <div style="display:flex;justify-content:center;margin:8px 0 4px;">
      <div style="background:rgba(225,245,254,0.92);color:#555;font-size:12px;
                  padding:4px 14px;border-radius:8px;
                  box-shadow:0 1px 2px rgba(0,0,0,0.08);
                  font-family:'Segoe UI',sans-serif;">{label}</div>
    </div>""", unsafe_allow_html=True)

def message_securite():
    st.markdown("""
    <div style="display:flex;justify-content:center;margin:8px 8px 4px;">
      <div style="background:#fff9c4;border-radius:8px;padding:9px 16px;
                  font-size:12.5px;color:#7a6a00;text-align:center;max-width:90%;
                  box-shadow:0 1px 2px rgba(0,0,0,0.08);line-height:1.5;">
        🔒 Prototype expérimental · Messages chiffrés · Données anonymisées
      </div>
    </div>""", unsafe_allow_html=True)

# ============================================================
# 8. PAGES INTERNES
# ============================================================
def afficher_exercices():
    st.markdown("### 🧘 Exercices guidés")
    st.markdown("*Techniques pour ton bien-être quotidien*")
    st.markdown("---")

    choix   = st.selectbox("Choisis un exercice :", list(EXERCICES.keys()))
    ex      = EXERCICES[choix]
    couleur = ex["couleur"]

    st.markdown(f"""
    <div style="background:#fff;border-radius:8px;padding:12px 16px;margin:10px 0;
                box-shadow:0 1px 3px rgba(0,0,0,0.1);border-left:4px solid {couleur};">
        <strong style="color:{couleur};font-size:14px;">{choix}</strong><br>
        <span style="font-size:13px;color:#555;">{ex['description']}</span>
    </div>
    """, unsafe_allow_html=True)

    for k,v in {"ex_actif":False,"ex_etape":0,"ex_rep":0}.items():
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
        ex_c   = EXERCICES.get(st.session_state.get("ex_choix",choix), ex)
        etapes = ex_c["etapes"]
        ei, ri = st.session_state.ex_etape, st.session_state.ex_rep
        if ei < len(etapes):
            nom, duree, instruction = etapes[ei]
            st.progress((ei+ri*len(etapes))/(len(etapes)*ex_c["repetitions"]))
            st.markdown(f"""
            <div style="text-align:center;padding:22px 16px;background:#fff;
                        border-radius:10px;margin:10px 0;box-shadow:0 1px 3px rgba(0,0,0,0.1);">
                <div style="font-size:1.8rem;margin-bottom:6px;">{nom}</div>
                <div style="font-size:13.5px;color:#555;line-height:1.6;">{instruction}</div>
                <div style="font-size:2.4rem;font-weight:700;color:{couleur};margin-top:10px;">{duree}s</div>
                <div style="font-size:12px;color:#999;margin-top:4px;">Répétition {ri+1}/{ex_c['repetitions']}</div>
            </div>""", unsafe_allow_html=True)
            c1,c2 = st.columns(2)
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
            st.success("🎉 Exercice terminé !")
            if st.button("🔄 Recommencer", use_container_width=True):
                st.session_state.ex_actif = False
                st.rerun()

def afficher_feedback(user_id: str):
    if a_deja_donne_feedback_aujourd_hui(user_id):
        return
    st.markdown("---")
    st.markdown("""
    <div style="background:#fff;border-radius:8px;padding:12px 16px;
                margin:10px 0;border-left:4px solid #25d366;">
        <strong style="color:#075e54;">💬 Ton avis nous aide !</strong><br>
        <span style="font-size:13px;color:#555;">Aura t'a-t-il été utile ?</span>
    </div>""", unsafe_allow_html=True)
    utile = st.radio("Utile ?",["✅ Oui !","🤔 Un peu","❌ Non"],horizontal=True)
    comm  = st.text_area("Comment t'a-t-il aidé ?",
                         placeholder="Ex: J'ai pu parler de mon stress...", height=60)
    prix  = st.select_slider("Combien paierais-tu/mois ?",
                             options=["0 FCFA","500 FCFA","1 000 FCFA","2 000 FCFA","+ de 2 000 FCFA"])
    if st.button("📤 Envoyer mon avis", use_container_width=True):
        sauvegarder_feedback(user_id, utile, comm, prix)
        st.success("Merci ! 🙏")
        st.rerun()

def afficher_confidentialite():
    st.markdown("### 🔒 Politique de confidentialité")
    st.markdown("---")
    st.markdown("""
    <div style="background:#fff;border-radius:8px;padding:18px 20px;
                font-size:13.5px;color:#333;line-height:2;">

    <strong style="color:#075e54;">Ce que nous collectons</strong><br>
    • Prénom → ID anonyme interne<br>
    • Messages chiffrés AES-256<br>
    • Humeur quotidienne (optionnel)<br><br>

    <strong style="color:#075e54;">Ce que nous ne faisons JAMAIS</strong><br>
    • Vente de données · Publicité ciblée · Partage tiers<br><br>

    <strong style="color:#075e54;">Tes droits</strong><br>
    • Suppression totale via Tableau de bord<br>
    • Toutes tes données visibles dans l'app<br><br>

    <strong style="color:#075e54;">Sécurité</strong><br>
    • Chiffrement Fernet · PIN hashé SHA-256<br>
    • Blocage après 5 tentatives · Session 2h<br><br>

    <strong style="color:#075e54;">Conformité</strong><br>
    Loi ivoirienne 2013-451 sur la cybersécurité · ARTCI<br><br>

    📧 aura.civ@gmail.com · Avril 2026
    </div>""", unsafe_allow_html=True)

# ============================================================
# 9. CONFIG PAGE — sidebar collapsed par défaut sur mobile
# ============================================================
st.set_page_config(
    page_title="Aura", page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed"   # ← FERMÉE au démarrage → chat visible d'abord
)

# ============================================================
# 10. CSS COMPLET
# ============================================================
st.markdown("""
<style>
html, body, [class*="css"] {
    font-family: 'Segoe UI',-apple-system,BlinkMacSystemFont,sans-serif !important;
}

/* ── Fond WhatsApp ── */
.stApp {
    background-color: #eae6df !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'%3E%3Cg fill='%23c8bdb0' fill-opacity='0.12'%3E%3Ccircle cx='25' cy='25' r='5'/%3E%3Ccircle cx='75' cy='25' r='3'/%3E%3Ccircle cx='125' cy='25' r='5'/%3E%3Ccircle cx='175' cy='25' r='3'/%3E%3Ccircle cx='50' cy='50' r='3'/%3E%3Ccircle cx='100' cy='50' r='6'/%3E%3Ccircle cx='150' cy='50' r='3'/%3E%3Ccircle cx='25' cy='75' r='3'/%3E%3Ccircle cx='75' cy='75' r='6'/%3E%3Ccircle cx='125' cy='75' r='3'/%3E%3Ccircle cx='175' cy='75' r='5'/%3E%3Ccircle cx='25' cy='125' r='5'/%3E%3Ccircle cx='75' cy='125' r='3'/%3E%3Ccircle cx='125' cy='125' r='5'/%3E%3Ccircle cx='175' cy='125' r='3'/%3E%3Ccircle cx='50' cy='150' r='3'/%3E%3Ccircle cx='100' cy='150' r='5'/%3E%3Ccircle cx='150' cy='150' r='3'/%3E%3C/g%3E%3C/svg%3E") !important;
}
.main .block-container { padding: 0 !important; max-width: 100% !important; }

/* ── SIDEBAR ── */
section[data-testid="stSidebar"] {
    background: #075e54 !important;
    min-width: 240px !important;
    max-width: 240px !important;
}
section[data-testid="stSidebar"] > div {
    padding: 0 0 60px 0 !important;
    overflow-y: auto !important;
    height: 100vh !important;
}
section[data-testid="stSidebar"] * {
    color: #fff !important;
    font-family: 'Segoe UI',sans-serif !important;
}

/* ── BOUTON HAMBURGER ☰ — TOUJOURS VISIBLE ── */
[data-testid="stSidebarCollapseButton"] {
    display: flex !important;
    position: fixed !important;
    top: 10px !important;
    left: 10px !important;
    z-index: 99999 !important;
    width: 40px !important;
    height: 40px !important;
    border-radius: 50% !important;
    background: #075e54 !important;
    border: none !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.35) !important;
    cursor: pointer !important;
    transition: background 0.2s !important;
}
[data-testid="stSidebarCollapseButton"]:hover {
    background: #128c7e !important;
}
[data-testid="stSidebarCollapseButton"] svg {
    fill: #fff !important;
    width: 20px !important;
    height: 20px !important;
}
[data-testid="collapsedControl"] {
    display: flex !important;
    position: fixed !important;
    top: 10px !important;
    left: 10px !important;
    z-index: 99999 !important;
    width: 40px !important;
    height: 40px !important;
    border-radius: 50% !important;
    background: #075e54 !important;
    border: none !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.35) !important;
    cursor: pointer !important;
}
[data-testid="collapsedControl"] svg {
    fill: #fff !important;
    width: 20px !important;
    height: 20px !important;
}

/* ── Sidebar header ── */
.sb-header {
    background: #054c43;
    padding: 16px 14px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.1);
    margin-bottom: 4px;
}
.sb-title { font-size: 1.1rem; font-weight: 700; color: #fff !important; letter-spacing:.5px; }
.sb-sub   { font-size: 11px; color: #b2dfdb !important; margin-top: 3px; line-height: 1.5; }
.sb-user  { font-size: 12px; color: #80cbc4 !important; margin-top: 6px;
             display: flex; align-items: center; gap: 5px; }

/* ── Nav radio ── */
section[data-testid="stSidebar"] .stRadio > div {
    gap: 3px !important; padding: 6px 10px;
}
section[data-testid="stSidebar"] .stRadio > div > label {
    background: rgba(255,255,255,0.06) !important;
    border: none !important; border-radius: 7px !important;
    padding: 11px 14px !important; cursor: pointer;
    transition: background .15s; font-size: 14px !important;
    font-weight: 500 !important; color: #e0f2f1 !important;
    width: 100% !important; margin: 0 !important;
    min-height: 44px !important;
    display: flex !important; align-items: center !important;
}
section[data-testid="stSidebar"] .stRadio > div > label:hover {
    background: rgba(255,255,255,0.14) !important;
}
section[data-testid="stSidebar"] .stRadio input[type="radio"] { display: none !important; }

/* ── Boutons sidebar ── */
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.08) !important;
    color: #e0f2f1 !important; border: none !important;
    border-radius: 7px !important; font-size: 13px !important;
    padding: 9px 12px !important; min-height: 42px !important;
    transition: background .15s; width: 100%;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.16) !important;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.12) !important;
    margin: 8px 0 !important;
}

/* ── Stat box ── */
.stat-box {
    background: rgba(0,0,0,0.15); border-radius: 7px;
    padding: 10px 13px; margin: 4px 10px;
    font-size: 11.5px; color: #b2dfdb !important; line-height: 2;
}

/* ── TOPBAR WhatsApp ── */
.wa-topbar {
    background: #075e54; padding: 10px 16px 10px 60px;
    display: flex; align-items: center; gap: 12px;
    position: sticky; top: 0; z-index: 200;
    box-shadow: 0 2px 4px rgba(0,0,0,0.2);
    min-height: 58px;
}
.wa-avatar {
    width: 38px; height: 38px; border-radius: 50%;
    background: linear-gradient(135deg,#25d366,#128c7e);
    display: flex; align-items: center; justify-content: center;
    font-size: 17px; flex-shrink: 0;
}
.wa-name   { font-size: 15px; font-weight: 600; color: #fff; }
.wa-status { font-size: 12px; color: #b2dfdb; }

/* ── Zone messages ── */
.messages-container { padding: 4px 0; min-height: 55vh; }
[data-testid="stChatMessage"] {
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 0 !important; margin: 0 !important;
}
[data-testid="stChatMessage"] > div { background: transparent !important; }

/* ── Saisie texte ── */
div[data-testid="stChatInput"] {
    background: #f0f0f0 !important; border: none !important;
    border-top: 1px solid #ddd !important; border-radius: 0 !important;
    box-shadow: none !important; padding: 8px 12px !important;
}
div[data-testid="stChatInput"] > div {
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 0 !important;
    display: flex !important; align-items: center !important; gap: 8px !important;
}
div[data-testid="stChatInput"] textarea {
    font-family: 'Segoe UI',sans-serif !important; font-size: 15px !important;
    color: #111 !important; background: #fff !important;
    border: none !important; border-radius: 22px !important;
    padding: 10px 16px !important; min-height: 44px !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important; resize: none !important;
}
div[data-testid="stChatInput"] textarea::placeholder {
    color: #999 !important; font-size: 14px !important;
}
div[data-testid="stChatInput"] button {
    background: #25d366 !important; border-radius: 50% !important;
    width: 44px !important; height: 44px !important; min-width: 44px !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.2) !important; border: none !important;
}
div[data-testid="stChatInput"] button:hover { background: #128c7e !important; }
div[data-testid="stChatInput"] button svg {
    fill: #fff !important; width: 20px !important; height: 20px !important;
}

/* ── Login ── */
.login-bg {
    min-height: 100vh; display: flex; align-items: center;
    justify-content: center; padding: 20px;
}
.login-card {
    background: #fff; border-radius: 12px; overflow: hidden;
    max-width: 420px; width: 100%; box-shadow: 0 4px 24px rgba(0,0,0,0.14);
}
.login-top {
    background: #075e54; padding: 32px 20px 24px; text-align: center;
}
.login-body { padding: 22px 26px 26px; }

/* ── Pages ── */
.page-content { padding: 14px 18px; }
.stAlert { border-radius: 8px !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-thumb { background: #c8b8a2; border-radius: 10px; }

/* ── MOBILE ── */
@media (max-width: 768px) {
    section[data-testid="stSidebar"] {
        min-width: 85vw !important;
        max-width: 85vw !important;
        position: fixed !important;
        z-index: 9998 !important;
        height: 100vh !important;
        overflow-y: auto !important;
    }
    section[data-testid="stSidebar"] > div {
        padding-bottom: 80px !important;
        overflow-y: auto !important;
        height: 100% !important;
    }
    .wa-topbar { padding: 10px 16px 10px 58px !important; min-height: 56px; }
    .wa-name   { font-size: 14px; }
    .messages-container { padding: 4px 0; }
    div[data-testid="stChatInput"] { padding: 6px 8px !important; }
    div[data-testid="stChatInput"] button {
        width: 40px !important; height: 40px !important; min-width: 40px !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 11. SESSION STATE
# ============================================================
defaults = {
    "user_id": None, "prenom": None, "messages": [],
    "conversation_initiee": False, "page": "💬 Chat",
    "profil": {}, "ex_actif": False, "ex_etape": 0, "ex_rep": 0,
    "transcription_en_attente": "", "session_messages_count": 0,
    "heure_connexion": None,
    "pin_tentatives": 0, "pin_bloque_jusqu": None,
    "message_retour": None,
    "sidebar_ouverte": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# 12. EXPIRATION SESSION
# ============================================================
if st.session_state.user_id and st.session_state.heure_connexion:
    duree_h = (datetime.now() - st.session_state.heure_connexion).total_seconds() / 3600
    if duree_h > DUREE_SESSION_HEURES:
        st.warning(f"⏰ Session expirée ({DUREE_SESSION_HEURES}h). Reconnecte-toi.")
        for k in ["user_id","prenom","messages","conversation_initiee",
                  "profil","heure_connexion","pin_tentatives","pin_bloque_jusqu"]:
            st.session_state[k] = None if k != "messages" else []
        st.session_state.conversation_initiee = False
        st.rerun()

# ============================================================
# 13. LOGIN — sidebar collapsed, chat visible dès connexion
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
            <div style="font-size:48px;margin-bottom:8px;">✨</div>
            <div style="font-size:1.8rem;font-weight:700;color:#fff;">Aura</div>
            <div style="font-size:12px;color:#b2dfdb;margin-top:4px;">
                Coach de bien-être pour les étudiants</div>
          </div>
          <div class="login-body">
            <div style="background:#e8f5e9;border-radius:6px;padding:8px 12px;
                        font-size:12px;color:#2e7d32;text-align:center;margin-bottom:4px;">
                🧪 Bêta · {nb_users}/{LIMITE_BETA} participants · {places_restantes} place(s) dispo
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
            st.markdown(f"**{sal} !** Entre tes infos pour commencer.")

            prenom_input = st.text_input(
                "👤 Ton prénom :", placeholder="Ex: Aminata", key="login_prenom"
            )

            uid_existant         = None
            utilisateur_existant = False
            if prenom_input.strip() and valider_prenom(prenom_input.strip()):
                uid_existant = obtenir_id_par_prenom(prenom_input.strip())
                utilisateur_existant = uid_existant is not None

            if utilisateur_existant:
                st.markdown(f"""
                <div style="background:#e8f5e9;border-radius:8px;padding:9px 14px;
                            font-size:13px;color:#2e7d32;margin:8px 0;
                            border-left:3px solid #25d366;">
                    👋 Bon retour <strong>{prenom_input.strip().capitalize()}</strong> !
                </div>""", unsafe_allow_html=True)

                if st.session_state.pin_bloque_jusqu:
                    if datetime.now() < st.session_state.pin_bloque_jusqu:
                        reste = int((st.session_state.pin_bloque_jusqu - datetime.now()).total_seconds())
                        st.error(f"🔒 Compte bloqué. Réessaie dans {reste}s.")
                        st.stop()
                    else:
                        st.session_state.pin_tentatives   = 0
                        st.session_state.pin_bloque_jusqu = None

                pin_input = st.text_input(
                    "🔐 Code PIN (4 chiffres) :", type="password",
                    max_chars=4, placeholder="••••", key="login_pin_ex"
                )
                if st.session_state.pin_tentatives > 0:
                    st.warning(f"⚠️ {5 - st.session_state.pin_tentatives} tentative(s) restante(s).")

                if st.button("🔓 Se connecter", use_container_width=True):
                    if not valider_pin(pin_input):
                        st.error("Le PIN doit contenir 4 chiffres.")
                    elif not verifier_pin(uid_existant, pin_input):
                        st.session_state.pin_tentatives += 1
                        journaliser(uid_existant, "tentative_pin_echouee")
                        if st.session_state.pin_tentatives >= 5:
                            st.session_state.pin_bloque_jusqu = datetime.now() + timedelta(minutes=5)
                            st.error("🔒 5 échecs. Bloqué 5 minutes.")
                        else:
                            st.error(f"❌ PIN incorrect. {5-st.session_state.pin_tentatives} essai(s) restant(s).")
                    else:
                        # ✅ CONNEXION — sidebar reste fermée, chat s'ouvre
                        st.session_state.user_id         = uid_existant
                        st.session_state.prenom          = prenom_input.strip().capitalize()
                        st.session_state.profil          = charger_profil(uid_existant)
                        st.session_state.heure_connexion = datetime.now()
                        st.session_state.pin_tentatives  = 0
                        st.session_state.pin_bloque_jusqu = None
                        historique = charger_historique(uid_existant)
                        if historique:
                            st.session_state.messages = historique
                            st.session_state.conversation_initiee = True
                            st.session_state.message_retour = f"Content(e) de te revoir, {prenom_input.strip().capitalize()} 👋"
                        journaliser(uid_existant, "connexion")
                        st.rerun()
                st.caption("PIN oublié ? aura.civ@gmail.com")

            else:
                if prenom_input.strip() and valider_prenom(prenom_input.strip()):
                    st.markdown("""
                    <div style="background:#fff3e0;border-radius:8px;padding:9px 14px;
                                font-size:13px;color:#e65100;margin:8px 0;
                                border-left:3px solid #ff9800;">
                        ✨ Nouveau ? Crée ton accès sécurisé.
                    </div>""", unsafe_allow_html=True)

                pin_n = st.text_input("🔐 Crée ton PIN (4 chiffres) :", type="password",
                                      max_chars=4, placeholder="••••", key="pin_n")
                pin_c = st.text_input("🔐 Confirme ton PIN :", type="password",
                                      max_chars=4, placeholder="••••", key="pin_c")
                consent = st.checkbox(
                    "Je comprends que cet outil est un **prototype expérimental** "
                    "et j'accepte que mes données soient traitées de façon **anonyme** "
                    "à des fins de **recherche et d'amélioration** de Aura."
                )
                st.info("📱 Sur mobile : Menu → *Ajouter à l'écran d'accueil*")

                if st.button("✨  Créer mon compte", use_container_width=True):
                    if not prenom_input.strip() or not valider_prenom(prenom_input.strip()):
                        st.error("Prénom invalide.")
                    elif not valider_pin(pin_n):
                        st.error("PIN : 4 chiffres exactement.")
                    elif pin_n != pin_c:
                        st.error("Les PIN ne correspondent pas.")
                    elif not consent:
                        st.warning("Accepte les conditions pour continuer.")
                    else:
                        try:
                            uid = obtenir_ou_creer_id_anonyme(prenom_input.strip(), consentement=True)
                            definir_pin(uid, pin_n)
                            # ✅ INSCRIPTION — sidebar fermée, chat direct
                            st.session_state.user_id         = uid
                            st.session_state.prenom          = prenom_input.strip().capitalize()
                            st.session_state.profil          = {}
                            st.session_state.heure_connexion = datetime.now()
                            st.session_state.messages        = []
                            st.session_state.conversation_initiee = False
                            journaliser(uid, "inscription")
                            st.rerun()
                        except OverflowError:
                            st.error(f"🔒 Bêta complète ({LIMITE_BETA} participants).")
                        except ValueError as e:
                            st.error(str(e))
                        except Exception as e:
                            logging.error(f"Erreur inscription:{type(e).__name__}")
                            st.error("Erreur. Réessaie.")

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
if st.session_state.heure_connexion:
    restant_m = max(0, int(DUREE_SESSION_HEURES*60 -
                           (datetime.now()-st.session_state.heure_connexion).total_seconds()/60))
else:
    restant_m = DUREE_SESSION_HEURES * 60

st.markdown(f"""
<div class="wa-topbar">
  <div class="wa-avatar">✨</div>
  <div style="flex:1;">
    <div class="wa-name">Aura</div>
    <div class="wa-status">
      <span style="display:inline-block;width:6px;height:6px;border-radius:50%;
                   background:#25d366;margin-right:4px;"></span>En ligne · {prenom}
    </div>
  </div>
  <div style="text-align:right;">
    <div style="font-size:10px;color:#b2dfdb;">🧪 {nb_users}/{LIMITE_BETA}</div>
    <div style="font-size:10px;color:#80cbc4;">⏱️ {restant_m}min</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 16. SIDEBAR — contenu complet scrollable
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

    st.markdown("<div style='padding:6px 10px;'>", unsafe_allow_html=True)
    page = st.radio(
        "", ["💬 Chat","🧘 Exercices","📊 Tableau de bord","🔒 Confidentialité"],
        label_visibility="collapsed"
    )
    st.session_state.page = page
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<div style='padding:0 10px;'>", unsafe_allow_html=True)

    ca, cb = st.columns(2)
    with ca:
        if st.button("🗑️ Nouveau", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_initiee = False
            st.session_state.session_messages_count = 0
            st.rerun()
    with cb:
        if st.button("🚪 Changer", use_container_width=True):
            for k in ["user_id","prenom","messages","conversation_initiee",
                      "profil","heure_connexion","pin_tentatives","pin_bloque_jusqu"]:
                st.session_state[k] = None if k != "messages" else []
            st.session_state.conversation_initiee = False
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    stats = compter_messages(st.session_state.user_id)
    _, nb_today, limite = verifier_limite_messages(st.session_state.user_id)
    st.markdown(f"""
    <div class="stat-box">
        💬 {stats['nb_messages']} messages total<br>
        📅 Depuis : {stats['premiere_session']}<br>
        🕐 Dernière : {stats['derniere_session']}<br>
        📊 Aujourd'hui : {nb_today}/{limite}<br>
        ⏱️ Session : {restant_m}min restantes
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("<div style='padding:0 10px;'>", unsafe_allow_html=True)

    if st.button("🗑️ Effacer historique", use_container_width=True):
        supprimer_historique(st.session_state.user_id)
        st.session_state.messages = []
        st.session_state.conversation_initiee = False
        st.success("Effacé ✓")
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)

    st.markdown("""
    <div style="padding:4px 10px 16px;">
        <div style="font-size:10px;color:#80cbc4;font-weight:700;
                    text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">
            🆘 URGENCES CI</div>
        <div style="font-size:13px;color:#e0f2f1;line-height:2.4;">
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

elif page == "🔒 Confidentialité":
    st.markdown('<div class="page-content">', unsafe_allow_html=True)
    afficher_confidentialite()
    st.markdown('</div>', unsafe_allow_html=True)

else:
    # ══════════════════════════════════════════
    # CHAT
    # ══════════════════════════════════════════
    sal = salutation_heure()

    # Message de bienvenue
    if not st.session_state.conversation_initiee:
        historique_bdd = charger_historique(st.session_state.user_id)
        if historique_bdd:
            st.session_state.messages = historique_bdd
            st.session_state.conversation_initiee = True
            st.session_state.message_retour = f"Content(e) de te revoir, {prenom} 👋"
        else:
            msg = (
                f"{sal} {prenom} ✨\n\n"
                f"Je suis **Aura**, ton espace de bien-être dédié à tous les étudiants "
                f"de Côte d'Ivoire. Je suis là pour t'écouter, sans jugement et en toute confidentialité.\n\n"
                f"Tu as franchi une étape importante. Comment puis-je t'aider aujourd'hui ?\n\n"
                f"Tu peux aussi explorer les exercices ou ton tableau de bord via le menu ☰."
            )
            sauvegarder_conversation(st.session_state.user_id, "assistant", msg)
            st.session_state.messages = [
                {"role":"assistant","content":msg,
                 "horodatage":datetime.now().strftime("%H:%M")}
            ]
            st.session_state.conversation_initiee = True
            st.session_state.message_retour = None

    # Affichage messages
    st.markdown('<div class="messages-container">', unsafe_allow_html=True)
    message_securite()

    dates_vues = set()
    for m in st.session_state.messages:
        h = m.get("horodatage","")
        if len(h) >= 16:   heure = h[11:16]; date_msg = h[:10]
        elif len(h) == 5:  heure = h;        date_msg = datetime.now().strftime("%Y-%m-%d")
        else:              heure = datetime.now().strftime("%H:%M"); date_msg = datetime.now().strftime("%Y-%m-%d")

        if date_msg not in dates_vues:
            dates_vues.add(date_msg)
            try:
                d   = datetime.strptime(date_msg, "%Y-%m-%d").date()
                ajd = datetime.now().date()
                label = "Aujourd'hui" if d==ajd else ("Hier" if d==ajd-timedelta(days=1) else d.strftime("%d %B %Y"))
            except:
                label = date_msg
            separateur_date(label)

        contenu = m.get("content","")
        if not contenu or contenu in ("user","assistant") or len(contenu.strip()) < 2:
            continue
        if m["role"] == "assistant":
            bulle_bot(contenu, heure)
        else:
            bulle_user(contenu, heure, est_vocal=m.get("vocal",False))

    if st.session_state.get("message_retour"):
        separateur_date(st.session_state.message_retour)
        st.session_state.message_retour = None

    st.markdown('</div>', unsafe_allow_html=True)

    # Zone vocale
    st.markdown("""
    <div style="background:#f0f0f0;border-top:1px solid #e0e0e0;padding:7px 12px;">
        <span style="font-size:12px;color:#666;">🎤 Note vocale</span>
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
            </div>""", unsafe_allow_html=True)
            st.session_state.transcription_en_attente = texte_transcrit
            if st.button("✅ Envoyer ce message vocal", use_container_width=True):
                prompt = st.session_state.transcription_en_attente
                st.session_state.transcription_en_attente = ""
                autorise,_,lim = verifier_limite_messages(st.session_state.user_id)
                if not autorise:
                    st.warning(f"⚠️ Limite {lim} messages/jour.")
                else:
                    heure_now = datetime.now().strftime("%H:%M")
                    sauvegarder_conversation(st.session_state.user_id,"user",prompt)
                    incrementer_compteur_quotidien(st.session_state.user_id)
                    st.session_state.messages.append(
                        {"role":"user","content":prompt,"horodatage":heure_now,"vocal":True})
                    st.session_state.session_messages_count = st.session_state.get("session_messages_count",0)+1
                    hg = [{"role":m["role"],"content":m["content"]} for m in st.session_state.messages
                          if m.get("content") not in ("user","assistant")]
                    with st.spinner(""):
                        rep = obtenir_reponse(hg, prenom, profil)
                    heure_rep = datetime.now().strftime("%H:%M")
                    sauvegarder_conversation(st.session_state.user_id,"assistant",rep)
                    st.session_state.messages.append(
                        {"role":"assistant","content":rep,"horodatage":heure_rep})
                    if len(st.session_state.messages)%10==0:
                        mettre_a_jour_profil_ia(st.session_state.user_id,prenom,hg,profil)
                        st.session_state.profil = charger_profil(st.session_state.user_id)
                    st.rerun()
        else:
            st.warning("Impossible de transcrire. Écris ton message.")

    # Saisie texte
    if prompt := st.chat_input("Exprime-toi librement, je t'écoute..."):
        autorise,_,lim = verifier_limite_messages(st.session_state.user_id)
        if not autorise:
            st.warning(f"⚠️ Limite {lim} messages/jour atteinte.")
            st.stop()

        MOTS_CRISE = ["suicid","mourir","me tuer","en finir",
                      "plus envie de vivre","automutil","me faire du mal"]
        if any(m in prompt.lower() for m in MOTS_CRISE):
            st.error("🆘 **Urgences :** 📞 110/111 · 🚑 185 · 🔥 180")

        heure_now = datetime.now().strftime("%H:%M")
        sauvegarder_conversation(st.session_state.user_id,"user",prompt)
        incrementer_compteur_quotidien(st.session_state.user_id)
        st.session_state.messages.append({"role":"user","content":prompt,"horodatage":heure_now})
        st.session_state.session_messages_count = st.session_state.get("session_messages_count",0)+1

        hg = [
            {"role":m["role"],"content":m["content"]}
            for m in st.session_state.messages
            if m.get("content") and m["content"] not in ("user","assistant")
            and len(m["content"].strip())>=2
        ]
        with st.spinner(""):
            rep = obtenir_reponse(hg, prenom, profil)

        heure_rep = datetime.now().strftime("%H:%M")
        sauvegarder_conversation(st.session_state.user_id,"assistant",rep)
        st.session_state.messages.append({"role":"assistant","content":rep,"horodatage":heure_rep})

        if len(st.session_state.messages)%10==0:
            mettre_a_jour_profil_ia(st.session_state.user_id,prenom,hg,profil)
            st.session_state.profil = charger_profil(st.session_state.user_id)

        st.rerun()

    if st.session_state.get("session_messages_count",0) >= 6:
        afficher_feedback(st.session_state.user_id)