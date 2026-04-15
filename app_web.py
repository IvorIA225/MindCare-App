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
    a_deja_donne_feedback_aujourd_hui
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
GROQ_API_KEY  = os.getenv("GROQ_API_KEY", "")
VOIX_MENTOR   = os.getenv("VOIX_MENTOR",   "pNInz6obpgDQGcFmaJgB")
VOIX_CAMARADE = os.getenv("VOIX_CAMARADE", "ErXwobaYiN019PkySvjV")

if not GROQ_API_KEY:
    st.error("❌ Clé API Groq manquante.")
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

# ============================================================
# 2. SALUTATION DYNAMIQUE
# ============================================================
def salutation_heure() -> str:
    h = datetime.now().hour
    if 5 <= h < 12:   return "Bonjour"
    elif 12 <= h < 18: return "Bon après-midi"
    elif 18 <= h < 22: return "Bonsoir"
    else:              return "Bonne nuit"

# ============================================================
# 3. PROMPT SYSTÈME
# ============================================================
SYSTEM_PROMPT_BASE = """Tu es Aura, une assistante de bien-être et de coaching mental
dédiée aux étudiants de Côte d'Ivoire.

## PERSONNALITÉ
- Chaleureuse, empathique, grande sœur bienveillante
- Expressions africaines douces si appropriées
- Directe, douce, humour léger si possible

## RÈGLES
1. Valide les émotions AVANT de conseiller
2. UNE seule question à la fois
3. 3-4 phrases maximum
4. Prénom obligatoire dans la réponse
5. Jamais de diagnostic médical

## RÉALITÉS COMPRISES
- Pression familiale, difficultés financières
- Stress des examens, isolement, sentiment d'échec

## URGENCES
Pensées suicidaires → 110/111 · 185 · 180

Tu parles TOUJOURS en français. Tu es Aura — une lumière douce. ✨"""


def construire_prompt(prenom: str, profil: dict) -> str:
    heure = datetime.now().strftime("%H:%M")
    sal   = salutation_heure()
    base  = SYSTEM_PROMPT_BASE + f"\n\nHeure : {heure}. Salutation appropriée : '{sal}'."
    if not profil:
        return base + f"\n\nL'étudiant(e) s'appelle {prenom}."
    return base + f"""

## MÉMOIRE DE {prenom.upper()}
- Situation : {profil.get('situation','?')}
- Défis : {profil.get('defis','?')}
- Objectifs : {profil.get('objectifs','?')}
- Humeur générale : {profil.get('humeur_generale','?')}
- Préférences : {profil.get('preferences','?')}
- Notes Aura : {profil.get('notes_aura','aucune')}
- Dernière connexion : {profil.get('derniere_maj','?')}"""

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
Extrais les infos importantes. JSON uniquement :
{{"situation":"...","defis":"...","objectifs":"...","humeur_generale":"...","preferences":"...","notes_aura":"..."}}
Profil actuel : {json.dumps(profil, ensure_ascii=False)}
Échanges : {json.dumps(historique[-6:], ensure_ascii=False)}"""}],
            temperature=0.1, max_tokens=300,
        )
        t = r.choices[0].message.content
        d = json.loads(t[t.find("{"):t.rfind("}")+1])
        d["prenom"] = prenom
        sauvegarder_profil(user_id, d)
    except Exception as e:
        logging.error(f"Erreur profil IA : {type(e).__name__}")

# ============================================================
# 5. EXERCICES
# ============================================================
EXERCICES = {
    "🌬️ Respiration 4-7-8": {
        "description": "Calme l'anxiété en 2 minutes.",
        "etapes": [
            ("Inspire", 4, "Inspire lentement par le nez... 1, 2, 3, 4"),
            ("Retiens", 7, "Retiens ton souffle... 1 à 7"),
            ("Expire",  8, "Expire lentement par la bouche... 1 à 8"),
        ], "repetitions": 4, "couleur": "#7c3aed"
    },
    "🌿 Ancrage 5-4-3-2-1": {
        "description": "Reviens au moment présent.",
        "etapes": [
            ("👁️ Vois",   15, "Nomme 5 choses que tu vois..."),
            ("✋ Touche", 15, "Touche 4 objets, sens leur texture..."),
            ("👂 Écoute", 15, "Identifie 3 sons que tu entends..."),
            ("👃 Sens",   10, "Repère 2 odeurs..."),
            ("👅 Goûte",  10, "1 goût dans ta bouche..."),
        ], "repetitions": 1, "couleur": "#1D9E75"
    },
    "🙏 Gratitude (3 min)": {
        "description": "Change ta perspective.",
        "etapes": [
            ("Pense",   30, "3 choses positives d'aujourd'hui..."),
            ("Ressens", 30, "Ressens la gratitude..."),
            ("Retiens", 20, "Grave ces moments..."),
        ], "repetitions": 1, "couleur": "#f59e0b"
    },
    "🎯 Pomodoro": {
        "description": "Travaille mieux, procrastine moins.",
        "etapes": [
            ("Prépare",   60,   "Pose ton téléphone, ouvre ton cours..."),
            ("Travaille", 1500, "UNE seule tâche — 25 min !"),
            ("Repose",    300,  "Pause ! Lève-toi, bouge..."),
        ], "repetitions": 4, "couleur": "#e24b4a"
    }
}

# ============================================================
# 6. FONCTIONS IA
# ============================================================
def obtenir_reponse(historique: list, prenom: str, profil: dict) -> str:
    try:
        r = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": construire_prompt(prenom, profil)}] + historique,
            temperature=0.75, max_tokens=400,
        )
        return r.choices[0].message.content
    except Exception as e:
        logging.error(f"Erreur Groq : {type(e).__name__}")
        return "Je suis désolée, une erreur technique s'est produite. 🙏"

def transcrire_audio(fichier_audio) -> str:
    try:
        t = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=fichier_audio,
            language="fr"
        )
        return t.text
    except Exception as e:
        logging.error(f"Erreur transcription : {type(e).__name__}")
        return ""

# ============================================================
# 7. BULLES
# ============================================================
def bulle_bot(texte: str, heure: str = None):
    heure = heure or datetime.now().strftime("%H:%M")
    th    = texte.replace("\n\n","<br><br>").replace("\n","<br>")
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-start;align-items:flex-start;margin:8px 0;">
      <div style="width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#7c3aed,#a855f7);
                  display:flex;align-items:center;justify-content:center;font-size:16px;
                  flex-shrink:0;margin-right:8px;box-shadow:0 2px 6px rgba(124,58,237,0.3);">✨</div>
      <div style="background:#fff;border-radius:0 18px 18px 18px;padding:12px 16px;
                  max-width:75%;font-family:'Nunito',sans-serif;font-size:15px;
                  line-height:1.75;color:#2d2d2d;box-shadow:0 1px 4px rgba(0,0,0,0.08);word-wrap:break-word;">
        {th}
        <div style="font-size:11px;color:#8a9e8a;text-align:right;margin-top:6px;">{heure}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

def bulle_user(texte: str, heure: str = None, est_vocal: bool = False):
    heure  = heure or datetime.now().strftime("%H:%M")
    th     = texte.replace("\n\n","<br><br>").replace("\n","<br>")
    icone  = "🎤 " if est_vocal else ""
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-end;align-items:flex-start;margin:8px 0;">
      <div style="background:#d9fdd3;border-radius:18px 0 18px 18px;padding:12px 16px;
                  max-width:75%;font-family:'Nunito',sans-serif;font-size:15px;
                  line-height:1.75;color:#111;box-shadow:0 1px 4px rgba(0,0,0,0.08);word-wrap:break-word;">
        {icone}{th}
        <div style="font-size:11px;color:#5a8a5a;text-align:right;margin-top:6px;">{heure} ✓✓</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 8. PAGE EXERCICES
# ============================================================
def afficher_exercices():
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a1a2e,#0f3460);border-radius:16px;
                padding:20px 24px;margin-bottom:20px;">
        <h2 style="color:#fff;margin:0;font-size:1.3rem;">🧘 Exercices guidés</h2>
        <p style="color:#c9b8f0;margin:4px 0 0;font-size:0.83rem;">Techniques pour ton bien-être quotidien</p>
    </div>
    """, unsafe_allow_html=True)

    choix   = st.selectbox("Choisis un exercice :", list(EXERCICES.keys()))
    ex      = EXERCICES[choix]
    couleur = ex["couleur"]

    st.markdown(f"""
    <div style="background:{couleur}18;border-left:4px solid {couleur};
                border-radius:0 12px 12px 0;padding:12px 18px;margin-bottom:20px;">
        <strong style="color:{couleur};">{choix}</strong><br>
        <span style="font-size:13px;color:#6b7280;">{ex['description']}</span><br>
        <span style="font-size:12px;color:#9ca3af;">{ex['repetitions']} répétition(s) · {len(ex['etapes'])} étapes</span>
    </div>
    """, unsafe_allow_html=True)

    for k, v in {"ex_actif": False, "ex_etape": 0, "ex_rep": 0}.items():
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
            <div style="text-align:center;padding:28px 20px;background:{couleur}10;border-radius:20px;margin:12px 0;">
                <div style="font-size:2rem;margin-bottom:8px;">{nom}</div>
                <div style="font-size:1rem;color:#4b5563;line-height:1.7;max-width:380px;margin:0 auto;">{instruction}</div>
                <div style="font-size:2.8rem;font-weight:700;color:{couleur};margin-top:14px;">{duree}s</div>
                <div style="font-size:12px;color:#9ca3af;margin-top:6px;">Répétition {ri+1}/{ex_c['repetitions']}</div>
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
                    st.session_state.ex_etape = 0
                    st.session_state.ex_rep   = 0
                    st.rerun()
        else:
            st.balloons()
            st.success(f"🎉 Bravo ! Exercice terminé !")
            if st.button("🔄 Recommencer", use_container_width=True):
                st.session_state.ex_actif = False
                st.session_state.ex_etape = 0
                st.session_state.ex_rep   = 0
                st.rerun()

# ============================================================
# 9. FORMULAIRE FEEDBACK
# ============================================================
def afficher_feedback(user_id: str):
    if a_deja_donne_feedback_aujourd_hui(user_id):
        return

    st.markdown("---")
    st.markdown("""
    <div style="background:linear-gradient(135deg,rgba(124,58,237,0.08),rgba(168,85,247,0.08));
                border-radius:16px;padding:20px 24px;border:1px solid rgba(124,58,237,0.2);">
        <div style="font-size:1rem;font-weight:700;color:#1a1a2e;margin-bottom:4px;">
            💬 Ton avis compte !
        </div>
        <div style="font-size:13px;color:#6b7280;">
            Aura a-t-il été utile lors de cette session ?
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    utile = st.radio(
        "Est-ce qu'Aura t'a été utile aujourd'hui ?",
        ["✅ Oui, vraiment !", "🤔 Un peu", "❌ Pas vraiment"],
        horizontal=True
    )
    commentaire = st.text_area(
        "Si oui, dis-nous comment il t'a aidé :",
        placeholder="Ex: J'ai pu parler de mon stress d'examen et me sentir mieux...",
        height=80
    )
    prix_mois = st.select_slider(
        "Combien serais-tu prêt(e) à payer par mois pour Aura à l'avenir ?",
        options=["0 FCFA", "500 FCFA", "1 000 FCFA", "2 000 FCFA", "3 000 FCFA", "Plus de 3 000 FCFA"]
    )

    if st.button("📤 Envoyer mon avis", use_container_width=True):
        sauvegarder_feedback(user_id, utile, commentaire, prix_mois)
        st.success("Merci pour ton retour ! Il nous aide à améliorer Aura. 🙏")
        st.balloons()
        st.rerun()

# ============================================================
# 10. CONFIG PAGE
# ============================================================
st.set_page_config(
    page_title="Aura — Coach de bien-être",
    page_icon="✨",
    layout="wide"
)

# ============================================================
# 11. CSS
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@300;400;500;600;700&family=Crimson+Pro:ital@0;1&display=swap');

html, body, [class*="css"] { font-family: 'Nunito', sans-serif !important; }

.stApp {
    background-color: #f0ebe3 !important;
    background-image: url("data:image/svg+xml,%3Csvg width='120' height='120' viewBox='0 0 120 120' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none'%3E%3Cg fill='%23b8a898' fill-opacity='0.08'%3E%3Ccircle cx='20' cy='20' r='3'/%3E%3Ccircle cx='60' cy='20' r='2'/%3E%3Ccircle cx='100' cy='20' r='3'/%3E%3Ccircle cx='20' cy='60' r='2'/%3E%3Ccircle cx='60' cy='60' r='4'/%3E%3Ccircle cx='100' cy='60' r='2'/%3E%3Ccircle cx='20' cy='100' r='3'/%3E%3Ccircle cx='60' cy='100' r='2'/%3E%3Ccircle cx='100' cy='100' r='3'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E") !important;
}

.main .block-container { padding: 0 !important; max-width: 100% !important; }

/* ── SIDEBAR ── */
section[data-testid="stSidebar"] {
    background: #1a2a1a !important;
    min-width: 220px !important; max-width: 220px !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
section[data-testid="stSidebar"] > div { padding: 0 !important; }
section[data-testid="stSidebar"] * { color: #d4efd4 !important; font-family: 'Nunito', sans-serif !important; }
[data-testid="stSidebarCollapseButton"],[data-testid="collapsedControl"] { display: none !important; }

.sidebar-logo {
    padding: 20px 16px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    margin-bottom: 6px;
}
.sidebar-logo-title {
    font-size: 1.3rem; font-weight: 800; color: #fff !important;
    letter-spacing: 1px;
}
.sidebar-logo-sub {
    font-size: 11px; color: #6aaa6a !important;
    margin-top: 2px; line-height: 1.4;
}
.sidebar-user {
    font-size: 12px; color: #8acc8a !important; margin-top: 6px;
    display: flex; align-items: center; gap: 4px;
}

section[data-testid="stSidebar"] .stRadio > div { gap: 4px !important; padding: 0 10px; }
section[data-testid="stSidebar"] .stRadio > div > label {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important; padding: 9px 12px !important;
    cursor: pointer; transition: all 0.18s;
    font-size: 13px !important; font-weight: 500 !important;
    color: #b8ddb8 !important; width: 100% !important; margin: 0 !important;
    display: flex !important; align-items: center !important;
}
section[data-testid="stSidebar"] .stRadio > div > label:hover {
    background: rgba(100,180,100,0.15) !important;
    border-color: rgba(100,200,100,0.3) !important; color: #fff !important;
}
section[data-testid="stSidebar"] .stRadio input[type="radio"] { display: none !important; }

section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.05) !important; color: #b8ddb8 !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important; font-size: 12px !important;
    padding: 7px 10px !important; transition: all 0.18s;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.10) !important; color: #fff !important;
}
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.07) !important; margin: 8px 0 !important; }

.stat-box {
    background: rgba(255,255,255,0.04); border-radius: 10px;
    padding: 10px 12px; margin: 4px 10px; font-size: 11px;
    color: #7aaa7a !important; border: 1px solid rgba(255,255,255,0.06); line-height: 1.9;
}

/* ── TOPBAR style photo ── */
.topbar {
    background: #fff;
    border-bottom: 1px solid rgba(0,0,0,0.08);
    padding: 10px 24px; display: flex; align-items: center; gap: 12px;
    position: sticky; top: 0; z-index: 100;
    box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.topbar-avatar {
    width: 42px; height: 42px; border-radius: 50%;
    background: linear-gradient(135deg, #2d6a2d, #4a9e4a);
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; flex-shrink: 0;
    box-shadow: 0 2px 8px rgba(45,106,45,0.3);
}
.topbar-name { font-size: 15px; font-weight: 700; color: #1a2a1a; }
.topbar-status { font-size: 12px; color: #4CAF50; display: flex; align-items: center; gap: 4px; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; background: #4CAF50; display: inline-block; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }

/* ── Disclaimer ── */
.disclaimer {
    background: rgba(255,251,235,0.95); border-left: 3px solid #f59e0b;
    border-radius: 0 10px 10px 0; padding: 8px 16px; font-size: 0.78rem;
    color: #78350f; margin: 8px 16px; line-height: 1.6;
}

/* ── Date séparateur ── */
.date-sep {
    text-align: center; font-size: 12px; color: #7a6a58;
    background: rgba(255,255,255,0.8); padding: 4px 18px;
    border-radius: 12px; margin: 10px auto; width: fit-content;
    display: block; font-weight: 600; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

/* ── Zone messages ── */
.messages-container { padding: 8px 20px; min-height: 60vh; }

[data-testid="stChatMessage"] {
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 0 !important; margin: 0 !important;
}
[data-testid="stChatMessage"] > div { background: transparent !important; }

/* ── ZONE SAISIE style photo ── */
.input-footer {
    background: #f5f0ea;
    border-top: 1px solid rgba(0,0,0,0.06);
    padding: 10px 16px;
}

div[data-testid="stChatInput"] {
    background: #f5f0ea !important; border: none !important;
    border-top: 1px solid rgba(0,0,0,0.06) !important;
    border-radius: 0 !important; box-shadow: none !important;
    padding: 10px 16px !important;
}
div[data-testid="stChatInput"] > div {
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 0 !important;
    display: flex !important; align-items: center !important; gap: 8px !important;
}
div[data-testid="stChatInput"] textarea {
    font-family: 'Nunito', sans-serif !important; font-size: 15px !important;
    color: #2d2d2d !important; background: #fff !important;
    border: 1px solid rgba(0,0,0,0.08) !important;
    border-radius: 24px !important; padding: 12px 18px !important;
    min-height: 48px !important; box-shadow: 0 1px 4px rgba(0,0,0,0.06) !important;
    transition: border-color 0.2s !important; resize: none !important;
}
div[data-testid="stChatInput"] textarea:focus {
    border-color: #4a9e4a !important; outline: none !important;
    box-shadow: 0 2px 8px rgba(74,158,74,0.15) !important;
}
div[data-testid="stChatInput"] textarea::placeholder { color: #aaa !important; font-style: italic; }

div[data-testid="stChatInput"] button {
    background: #2d6a2d !important; border-radius: 50% !important;
    width: 46px !important; height: 46px !important; min-width: 46px !important;
    box-shadow: 0 2px 8px rgba(45,106,45,0.35) !important;
    transition: all 0.2s !important; border: none !important; flex-shrink: 0 !important;
}
div[data-testid="stChatInput"] button:hover { transform: scale(1.06) !important; background: #4a9e4a !important; }
div[data-testid="stChatInput"] button svg { fill: #fff !important; width: 20px !important; height: 20px !important; }

/* ── Bouton microphone ── */
.mic-btn {
    width: 44px; height: 44px; border-radius: 50%;
    background: rgba(45,106,45,0.1); border: 1px solid rgba(45,106,45,0.2);
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; transition: all 0.2s; font-size: 18px; flex-shrink: 0;
}
.mic-btn:hover { background: rgba(45,106,45,0.2); }

/* ── Zone vocale ── */
.vocal-zone {
    background: rgba(74,158,74,0.06); border: 1.5px dashed rgba(74,158,74,0.3);
    border-radius: 16px; padding: 14px 18px; margin: 6px 16px 0;
}

/* ── Login ── */
.login-wrapper { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; background: #f0ebe3; }
.login-card {
    background: #fff; border-radius: 24px; padding: 40px 44px;
    max-width: 480px; width: 100%; text-align: center;
    box-shadow: 0 8px 40px rgba(0,0,0,0.10);
}

/* ── Beta badge ── */
.beta-badge {
    background: linear-gradient(135deg, #2d6a2d, #4a9e4a);
    color: #fff; font-size: 11px; padding: 3px 10px;
    border-radius: 20px; display: inline-block; margin-bottom: 12px;
}

/* ── Pages ── */
.page-content { padding: 20px 24px; }
.stAlert { border-radius: 12px !important; }
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #c8b8a2; border-radius: 10px; }

@media (max-width: 768px) {
    .topbar { padding: 8px 12px; }
    .topbar-avatar { width: 36px; height: 36px; font-size: 17px; }
    .messages-container { padding: 6px 10px; }
    .page-content { padding: 14px 10px; }
    div[data-testid="stChatInput"] { padding: 8px 10px !important; }
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
# 13. LOGIN
# ============================================================
if st.session_state.user_id is None:
    nb_users = compter_utilisateurs()
    places_restantes = LIMITE_BETA - nb_users

    st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"""
        <div class="login-card">
            <div style="font-size:52px;margin-bottom:8px;">✨</div>
            <div class="beta-badge">🧪 Version bêta — {nb_users}/{LIMITE_BETA} participants</div>
            <div style="font-size:2rem;font-weight:800;color:#1a2a1a;margin-bottom:4px;">Aura</div>
            <div style="font-size:0.95rem;color:#6b7280;font-style:italic;
                        font-family:'Crimson Pro',serif;margin-bottom:4px;">
                Coach de bien-être pour les étudiants
            </div>
            <div style="font-size:11px;color:#9ca3af;margin-bottom:24px;">
                Côte d'Ivoire · Prototype expérimental
            </div>
        </div>
        """, unsafe_allow_html=True)

        if beta_pleine():
            st.error(f"🔒 La bêta est complète ({LIMITE_BETA} participants atteints). Merci de ton intérêt !")
            st.info("Laisse ton contact pour être notifié du lancement officiel.")
            st.text_input("Ton email ou numéro WhatsApp :", placeholder="ex: +225 07 00 00 00 00")
            st.button("📩 M'inscrire sur la liste d'attente", use_container_width=True)
        else:
            sal = salutation_heure()
            st.markdown(f"#### {sal} ! 👋")
            st.markdown(f"**{places_restantes} place(s) restante(s)** sur {LIMITE_BETA}.")
            st.markdown("Entre ton prénom pour rejoindre la bêta.")

            prenom_input = st.text_input(
                "", placeholder="Ton prénom...", label_visibility="collapsed"
            )

            consentement = st.checkbox(
                "Je comprends que cet outil est un **prototype expérimental** et j'accepte que "
                "mes données soient traitées de façon **anonyme** et utilisées à des fins de "
                "**recherche et d'amélioration** de Aura.",
                value=False
            )

            if st.button("✨ Rejoindre la bêta Aura", use_container_width=True):
                if not prenom_input.strip():
                    st.error("Merci d'entrer ton prénom.")
                elif not consentement:
                    st.warning("⚠️ Tu dois accepter les conditions d'utilisation pour continuer.")
                elif not valider_prenom(prenom_input.strip()):
                    st.error("Prénom invalide (lettres uniquement, 2-50 caractères).")
                else:
                    try:
                        uid = obtenir_ou_creer_id_anonyme(prenom_input.strip(), consentement=True)
                        st.session_state.user_id  = uid
                        st.session_state.prenom   = prenom_input.strip().capitalize()
                        st.session_state.profil   = charger_profil(uid)
                        historique = charger_historique(uid)
                        if historique:
                            st.session_state.messages = [
                                {"role": m["role"], "content": m["content"],
                                 "horodatage": m.get("horodatage", "")}
                                for m in historique
                            ]
                            st.session_state.conversation_initiee = True
                        journaliser(uid, "connexion")
                        st.rerun()
                    except OverflowError:
                        st.error(f"🔒 La bêta vient d'atteindre sa limite de {LIMITE_BETA} participants.")
                    except ValueError as e:
                        st.error(str(e))
                    except Exception as e:
                        logging.error(f"Erreur login : {type(e).__name__}")
                        st.error("Une erreur est survenue. Réessaie.")

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ============================================================
# 14. VARIABLES
# ============================================================
prenom = st.session_state.prenom
profil = st.session_state.profil

# ============================================================
# 15. TOPBAR — style photo
# ============================================================
nb_users = compter_utilisateurs()
st.markdown(f"""
<div class="topbar">
  <div class="topbar-avatar">✨</div>
  <div style="flex:1;">
    <div class="topbar-name">Aura</div>
    <div class="topbar-status">
      <span class="status-dot"></span> En ligne
    </div>
  </div>
  <div style="text-align:right;line-height:1.7;">
    <div style="font-size:12px;color:#4a7a4a;font-weight:600;">👤 {prenom}</div>
    <div style="font-size:10px;color:#9ca3af;">🧪 Bêta · {nb_users}/{LIMITE_BETA}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 16. SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown(f"""
    <div class="sidebar-logo">
        <div class="sidebar-logo-title">✨ AURA</div>
        <div class="sidebar-logo-sub">Coach de bien-être pour<br>les étudiants</div>
        <div class="sidebar-user">👤 {prenom}</div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "",
        ["💬 Chat", "🧘 Exercices", "📊 Tableau de bord"],
        label_visibility="collapsed"
    )
    st.session_state.page = page

    st.markdown("<hr>", unsafe_allow_html=True)

    ca, cb = st.columns(2)
    with ca:
        if st.button("🗑️ Nouveau", use_container_width=True):
            # Proposer feedback avant de vider
            if st.session_state.session_messages_count > 0:
                st.session_state.show_feedback = True
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
        📊 Aujourd'hui : {nb_today} / {limite}
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
    <div style="padding:0 10px;">
        <div style="font-size:10px;color:#4a7a4a;font-weight:700;
                    text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">
            🆘 Urgences CI
        </div>
        <div style="font-size:12px;color:#b8ddb8;line-height:2.2;">
            📞 <strong style="color:#fff;">110 / 111</strong> Police<br>
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
    st.markdown(f"""
    <div class="disclaimer">
      ⚕️ <strong>Prototype expérimental.</strong> Aura est un outil de soutien, pas un professionnel de santé.
      Urgences : <strong>110/111</strong> · <strong>185</strong> · <strong>180</strong>
    </div>
    <div class="date-sep">Aujourd'hui</div>
    """, unsafe_allow_html=True)

    # Message de bienvenue
    if not st.session_state.conversation_initiee:
        if profil and profil.get("notes_aura"):
            msg = (
                f"{sal} {prenom} ✨.\n\n"
                f"Je suis **Aura**, ton espace de bien-être personnalisé dédié à tous les étudiants "
                f"de Côte d'Ivoire. Je suis là pour t'écouter, sans jugement et en toute confidentialité.\n\n"
                f"Content(e) de te revoir. Comment tu vas depuis la dernière fois ?"
            )
        else:
            msg = (
                f"{sal} {prenom} ✨.\n\n"
                f"Je suis **Aura**, ton espace de bien-être personnalisé dédié à tous les étudiants "
                f"de Côte d'Ivoire. Je suis là pour t'écouter, sans jugement et en toute confidentialité.\n\n"
                f"Tu as franchi une étape importante pour ton bien-être. "
                f"Comment puis-je t'aider aujourd'hui ?\n\n"
                f"Tu peux aussi explorer les exercices ou ton tableau de bord."
            )
        st.session_state.messages = [
            {"role": "assistant", "content": msg, "horodatage": datetime.now().strftime("%H:%M")}
        ]
        st.session_state.conversation_initiee = True

    # Affichage messages
    st.markdown('<div class="messages-container">', unsafe_allow_html=True)
    for m in st.session_state.messages:
        h     = m.get("horodatage", "")
        heure = h[11:16] if len(h) >= 16 else (h[:5] if h else datetime.now().strftime("%H:%M"))
        if m["role"] == "assistant":
            bulle_bot(m["content"], heure)
        else:
            bulle_user(m["content"], heure, est_vocal=m.get("vocal", False))
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Zone vocale ──
    st.markdown('<div class="vocal-zone" style="margin:4px 16px 0;">', unsafe_allow_html=True)
    st.markdown("""
    <div style="font-size:12px;color:#4a7a4a;font-weight:600;margin-bottom:6px;">
        🎤 Note vocale — parle directement à Aura
    </div>
    """, unsafe_allow_html=True)

    audio_file = st.audio_input(
        "Enregistre ton message",
        label_visibility="collapsed",
        key="audio_input"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    if audio_file is not None:
        with st.spinner("🎤 Transcription en cours..."):
            texte_transcrit = transcrire_audio(audio_file)
        if texte_transcrit:
            st.markdown(f"""
            <div style="background:rgba(74,158,74,0.08);border-radius:12px;
                        padding:10px 14px;font-size:13px;color:#2d4a2d;
                        margin:8px 16px;border-left:3px solid #4a9e4a;">
                📝 <em>"{texte_transcrit}"</em>
            </div>
            """, unsafe_allow_html=True)
            st.session_state.transcription_en_attente = texte_transcrit

            if st.button("✅ Envoyer ce message vocal", use_container_width=True):
                prompt = st.session_state.transcription_en_attente
                st.session_state.transcription_en_attente = ""
                autorise, _, lim = verifier_limite_messages(st.session_state.user_id)
                if not autorise:
                    st.warning(f"⚠️ Limite de {lim} messages/jour atteinte.")
                else:
                    heure_now = datetime.now().strftime("%H:%M")
                    bulle_user(prompt, heure_now, est_vocal=True)
                    sauvegarder_conversation(st.session_state.user_id, "user", prompt)
                    incrementer_compteur_quotidien(st.session_state.user_id)
                    st.session_state.messages.append(
                        {"role": "user", "content": prompt, "horodatage": heure_now, "vocal": True}
                    )
                    st.session_state.session_messages_count += 1
                    hg = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
                    with st.spinner(""):
                        rep = obtenir_reponse(hg, prenom, profil)
                    heure_rep = datetime.now().strftime("%H:%M")
                    bulle_bot(rep, heure_rep)
                    sauvegarder_conversation(st.session_state.user_id, "assistant", rep)
                    st.session_state.messages.append(
                        {"role": "assistant", "content": rep, "horodatage": heure_rep}
                    )
                    if len(st.session_state.messages) % 10 == 0:
                        mettre_a_jour_profil_ia(st.session_state.user_id, prenom, hg, profil)
                        st.session_state.profil = charger_profil(st.session_state.user_id)
                    st.rerun()
        else:
            st.warning("Impossible de transcrire. Réessaie ou écris ton message.")

    # ── Saisie texte ──
    if prompt := st.chat_input("Exprime-toi librement, je t'écoute..."):
        autorise, _, lim = verifier_limite_messages(st.session_state.user_id)
        if not autorise:
            st.warning(f"⚠️ Limite de {lim} messages/jour atteinte.")
            st.stop()

        MOTS_CRISE = ["suicid", "mourir", "me tuer", "en finir",
                      "plus envie de vivre", "automutil", "me faire du mal"]
        if any(mot in prompt.lower() for mot in MOTS_CRISE):
            st.error("🆘 **Appelle maintenant :** 📞 110/111 · 🚑 185 · 🔥 180")

        heure_now = datetime.now().strftime("%H:%M")
        bulle_user(prompt, heure_now)
        sauvegarder_conversation(st.session_state.user_id, "user", prompt)
        incrementer_compteur_quotidien(st.session_state.user_id)
        st.session_state.messages.append(
            {"role": "user", "content": prompt, "horodatage": heure_now}
        )
        st.session_state.session_messages_count += 1

        hg = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages]
        with st.spinner(""):
            rep = obtenir_reponse(hg, prenom, profil)

        heure_rep = datetime.now().strftime("%H:%M")
        bulle_bot(rep, heure_rep)
        sauvegarder_conversation(st.session_state.user_id, "assistant", rep)
        st.session_state.messages.append(
            {"role": "assistant", "content": rep, "horodatage": heure_rep}
        )

        if len(st.session_state.messages) % 10 == 0:
            mettre_a_jour_profil_ia(st.session_state.user_id, prenom, hg, profil)
            st.session_state.profil = charger_profil(st.session_state.user_id)

        st.rerun()

    # ── Feedback après 6 messages ──
    if st.session_state.session_messages_count >= 6:
        afficher_feedback(st.session_state.user_id)