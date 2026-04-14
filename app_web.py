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
    init_db,
    obtenir_ou_creer_id_anonyme,
    sauvegarder_conversation,
    charger_historique,
    supprimer_historique,
    compter_messages,
    verifier_limite_messages,
    charger_profil,
    sauvegarder_profil,
    est_premium,
    journaliser,
    valider_prenom
)
from dashboard import afficher_dashboard
from plans import PLANS

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
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
VOIX_MENTOR        = os.getenv("VOIX_MENTOR",   "pNInz6obpgDQGcFmaJgB")
VOIX_CAMARADE      = os.getenv("VOIX_CAMARADE", "ErXwobaYiN019PkySvjV")

if not GROQ_API_KEY:
    st.error("❌ Clé API Groq manquante. Vérifiez vos secrets.")
    st.stop()

client = Groq(api_key=GROQ_API_KEY)

# ============================================================
# 2. PROMPT SYSTÈME DYNAMIQUE
# ============================================================
SYSTEM_PROMPT_BASE = """Tu es Aura, une assistante de bien-être et de coaching mental conçue
spécialement pour les étudiants africains de l'Université Alassane Ouattara (UAO), Bouaké, CI.

## TA PERSONNALITÉ
- Chaleureuse, empathique, jamais condescendante
- Tu parles comme une grande sœur bienveillante
- Tu utilises parfois des expressions africaines douces
- Directe mais toujours douce, humour léger si approprié

## RÈGLES D'OR
1. Valide TOUJOURS les émotions avant de conseiller
2. UNE seule question à la fois
3. Réponses courtes — 3-4 phrases max
4. Appelle l'étudiant par son prénom
5. Tu es un soutien, jamais un médecin

## RÉALITÉS QUE TU COMPRENDS
- Pression familiale (être l'espoir de la famille)
- Difficultés financières et manque de ressources
- Stress des examens, isolement, sentiment d'échec

## URGENCES
Pensées suicidaires → compassion absolue + 110/111 · 185 · 180

Tu parles TOUJOURS en français. Tu es Aura — une lumière douce. ✨"""


def construire_prompt(prenom: str, profil: dict) -> str:
    if not profil:
        return SYSTEM_PROMPT_BASE + f"\n\nL'étudiant(e) s'appelle {prenom}."

    memoire = f"""

## CE QUE TU SAIS SUR {prenom.upper()} (mémoire persistante)
- Situation     : {profil.get('situation', 'non renseignée')}
- Défis actuels : {profil.get('defis', 'non précisés')}
- Objectifs     : {profil.get('objectifs', 'non précisés')}
- Humeur générale : {profil.get('humeur_generale', 'inconnue')}
- Préférences   : {profil.get('preferences', 'standard')}
- Notes Aura    : {profil.get('notes_aura', 'aucune')}
- Dernière connexion : {profil.get('derniere_maj', 'inconnue')}

⚠️ Utilise ces infos naturellement. Si tu apprends quelque chose
   d'important de nouveau, mémorise-le dans tes notes internes."""

    return SYSTEM_PROMPT_BASE + memoire


# ============================================================
# 3. MISE À JOUR PROFIL AUTO PAR L'IA
# ============================================================
def mettre_a_jour_profil_ia(user_id: str, prenom: str, historique: list, profil: dict):
    """Après chaque échange, l'IA enrichit le profil utilisateur."""
    if len(historique) < 4:
        return
    try:
        prompt_extraction = f"""
Analyse ces derniers messages et extrais les infos importantes sur l'utilisateur.
Réponds UNIQUEMENT en JSON valide, sans texte autour, avec ces clés exactes :
{{
  "situation": "situation académique/personnelle courte",
  "defis": "défis et problèmes actuels",
  "objectifs": "ce qu'il/elle veut améliorer",
  "humeur_generale": "humeur globale observée",
  "preferences": "comment il/elle préfère interagir",
  "notes_aura": "notes importantes pour les prochaines sessions"
}}
Profil actuel : {json.dumps(profil, ensure_ascii=False)}
Derniers échanges : {json.dumps(historique[-6:], ensure_ascii=False)}
"""
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt_extraction}],
            temperature=0.1,
            max_tokens=400,
        )
        texte = response.choices[0].message.content
        debut = texte.find("{")
        fin   = texte.rfind("}") + 1
        if debut != -1 and fin > debut:
            nouvelles_donnees = json.loads(texte[debut:fin])
            nouvelles_donnees["prenom"] = prenom
            sauvegarder_profil(user_id, nouvelles_donnees)
    except Exception as e:
        logging.error(f"Erreur mise à jour profil IA : {type(e).__name__}")


# ============================================================
# 4. EXERCICES GUIDÉS
# ============================================================
EXERCICES = {
    "🌬️ Respiration 4-7-8": {
        "description": "Calme l'anxiété en 2 minutes.",
        "etapes": [
            ("Inspire",  4,    "Inspire lentement par le nez... 1, 2, 3, 4"),
            ("Retiens",  7,    "Retiens ton souffle... 1, 2, 3, 4, 5, 6, 7"),
            ("Expire",   8,    "Expire lentement par la bouche... 1 à 8"),
        ],
        "repetitions": 4, "couleur": "#7c3aed"
    },
    "🌿 Ancrage 5-4-3-2-1": {
        "description": "Reviens au moment présent.",
        "etapes": [
            ("👁️ Vois",    15, "Nomme 5 choses que tu vois autour de toi..."),
            ("✋ Touche",  15, "Touche 4 objets, sens leur texture..."),
            ("👂 Écoute", 15, "Identifie 3 sons que tu entends..."),
            ("👃 Sens",   10, "Repère 2 odeurs dans ton environnement..."),
            ("👅 Goûte",  10, "Prends conscience d'1 goût dans ta bouche..."),
        ],
        "repetitions": 1, "couleur": "#1D9E75"
    },
    "🙏 Gratitude (3 min)": {
        "description": "Change ta perspective en 3 minutes.",
        "etapes": [
            ("Pense",    30, "Pense à 3 choses positives d'aujourd'hui..."),
            ("Ressens",  30, "Ressens la gratitude pour chacune..."),
            ("Retiens",  20, "Grave ces moments dans ta mémoire..."),
        ],
        "repetitions": 1, "couleur": "#f59e0b"
    },
    "🎯 Pomodoro (25 min)": {
        "description": "Travaille mieux, procrastine moins.",
        "etapes": [
            ("Prépare",  60,   "Pose ton téléphone, ouvre ton cours..."),
            ("Travaille",1500, "Travaille sur UNE seule tâche — 25 min !"),
            ("Repose",   300,  "Pause ! Lève-toi, bouge, bois de l'eau..."),
        ],
        "repetitions": 4, "couleur": "#e24b4a"
    }
}


# ============================================================
# 5. FONCTIONS IA & VOIX
# ============================================================
def obtenir_reponse(historique: list, prenom: str, profil: dict) -> str:
    prompt_system = construire_prompt(prenom, profil)
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": prompt_system}] + historique,
            temperature=0.75,
            max_tokens=400,
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Erreur Groq : {type(e).__name__}")
        return "Je suis désolée, une erreur technique s'est produite. 🙏"


def synthese_vocale(texte: str, voix_id: str):
    if not ELEVENLABS_API_KEY:
        return None
    try:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voix_id}",
            headers={"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"},
            json={
                "text": texte,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {"stability": 0.6, "similarity_boost": 0.8}
            },
            timeout=15
        )
        return r.content if r.status_code == 200 else None
    except Exception as e:
        logging.error(f"Erreur ElevenLabs : {type(e).__name__}")
        return None


def bulle_bot(texte: str, heure: str = None):
    heure = heure or datetime.now().strftime("%H:%M")
    texte_html = texte.replace("\n\n", "<br><br>").replace("\n", "<br>")
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-start;align-items:flex-start;margin:6px 0;">
      <div style="width:0;height:0;border-top:10px solid #fff;
                  border-right:10px solid transparent;flex-shrink:0;margin-top:2px;"></div>
      <div style="background:#fff;border-radius:0 18px 18px 18px;padding:12px 16px;
                  max-width:75%;font-family:'Nunito',sans-serif;font-size:15px;
                  line-height:1.75;color:#2d2d2d;box-shadow:0 1px 4px rgba(0,0,0,0.08);
                  word-wrap:break-word;">
        {texte_html}
        <div style="font-size:11px;color:#8a9e8a;text-align:right;margin-top:6px;">{heure}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def bulle_user(texte: str, heure: str = None):
    heure = heure or datetime.now().strftime("%H:%M")
    texte_html = texte.replace("\n\n", "<br><br>").replace("\n", "<br>")
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-end;align-items:flex-start;margin:6px 0;">
      <div style="background:#d9fdd3;border-radius:18px 0 18px 18px;padding:12px 16px;
                  max-width:75%;font-family:'Nunito',sans-serif;font-size:15px;
                  line-height:1.75;color:#111;box-shadow:0 1px 4px rgba(0,0,0,0.08);
                  word-wrap:break-word;">
        {texte_html}
        <div style="font-size:11px;color:#5a8a5a;text-align:right;margin-top:6px;">{heure} ✓✓</div>
      </div>
      <div style="width:0;height:0;border-top:10px solid #d9fdd3;
                  border-left:10px solid transparent;flex-shrink:0;margin-top:2px;"></div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 6. PAGE EXERCICES
# ============================================================
def afficher_exercices():
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a1a2e,#0f3460);
                border-radius:16px;padding:20px 24px;margin-bottom:20px;">
        <h2 style="color:#fff;margin:0;font-size:1.3rem;">🧘 Exercices guidés</h2>
        <p style="color:#c9b8f0;margin:4px 0 0;font-size:0.83rem;">
            Techniques simples pour ton bien-être quotidien
        </p>
    </div>
    """, unsafe_allow_html=True)

    choix = st.selectbox("Choisis un exercice :", list(EXERCICES.keys()))
    ex = EXERCICES[choix]
    couleur = ex["couleur"]

    st.markdown(f"""
    <div style="background:{couleur}18;border-left:4px solid {couleur};
                border-radius:0 12px 12px 0;padding:12px 18px;margin-bottom:20px;">
        <strong style="color:{couleur};">{choix}</strong><br>
        <span style="font-size:13px;color:#6b7280;">{ex['description']}</span><br>
        <span style="font-size:12px;color:#9ca3af;">
            {ex['repetitions']} répétition(s) · {len(ex['etapes'])} étapes
        </span>
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
            prog = (ei + ri * len(etapes)) / (len(etapes) * ex_c["repetitions"])
            st.progress(prog)
            st.markdown(f"""
            <div style="text-align:center;padding:28px 20px;background:{couleur}10;
                        border-radius:20px;margin:12px 0;">
                <div style="font-size:2rem;margin-bottom:8px;">{nom}</div>
                <div style="font-size:1rem;color:#4b5563;line-height:1.7;
                            max-width:380px;margin:0 auto;">{instruction}</div>
                <div style="font-size:2.8rem;font-weight:700;color:{couleur};
                            margin-top:14px;">{duree}s</div>
                <div style="font-size:12px;color:#9ca3af;margin-top:6px;">
                    Répétition {ri + 1} / {ex_c['repetitions']}
                </div>
            </div>
            """, unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("⏭️ Étape suivante", use_container_width=True):
                    st.session_state.ex_etape += 1
                    if st.session_state.ex_etape >= len(etapes):
                        st.session_state.ex_rep  += 1
                        st.session_state.ex_etape = 0
                    st.rerun()
            with col2:
                if st.button("⏹️ Arrêter", use_container_width=True):
                    st.session_state.ex_actif = False
                    st.session_state.ex_etape = 0
                    st.session_state.ex_rep   = 0
                    st.rerun()
        else:
            st.balloons()
            st.success(f"🎉 Bravo ! Tu as terminé {st.session_state.ex_choix} !")
            if st.button("🔄 Recommencer", use_container_width=True):
                st.session_state.ex_actif = False
                st.session_state.ex_etape = 0
                st.session_state.ex_rep   = 0
                st.rerun()


# ============================================================
# 7. PAGE OFFRES
# ============================================================
def afficher_plans():
    st.markdown("""
    <div style="background:linear-gradient(135deg,#1a1a2e,#0f3460);
                border-radius:16px;padding:20px 24px;margin-bottom:24px;">
        <h2 style="color:#fff;margin:0;font-size:1.3rem;">💰 Nos offres</h2>
        <p style="color:#c9b8f0;margin:4px 0 0;font-size:0.83rem;">
            Choisis le plan qui correspond à tes besoins
        </p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    cols    = [col1, col2, col3]
    keys    = list(PLANS.keys())
    borders = [
        "1px solid rgba(255,255,255,0.08)",
        "2px solid #a855f7",
        "1px solid rgba(255,255,255,0.08)"
    ]

    for i, key in enumerate(keys):
        plan = PLANS[key]
        with cols[i]:
            badge = (
                '<div style="background:#a855f7;color:#fff;font-size:11px;'
                'padding:3px 10px;border-radius:20px;display:inline-block;'
                'margin-bottom:10px;">⭐ Populaire</div>'
                if key == "etudiant" else "<div style='height:28px'></div>"
            )
            features_html = "".join([
                f'<div style="color:{"#9FE1CB" if f.startswith("✅") else "#4b5563"};'
                f'font-size:13px;margin:7px 0;padding:4px 0;'
                f'border-bottom:1px solid rgba(255,255,255,0.04);">{f}</div>'
                for f in plan["features"]
            ])
            st.markdown(f"""
            <div style="background:#1a1a2e;border-radius:16px;padding:22px;
                        border:{borders[i]};min-height:340px;">
                {badge}
                <div style="font-size:1rem;font-weight:700;color:#fff;margin-bottom:6px;">
                    {plan['nom']}
                </div>
                <div style="font-size:1.5rem;font-weight:800;color:#a855f7;margin-bottom:16px;">
                    {plan['prix']}
                </div>
                {features_html}
            </div>
            """, unsafe_allow_html=True)

            st.markdown("<br>", unsafe_allow_html=True)
            if key == "gratuit":
                st.button("Plan actuel", key=f"btn_{key}", disabled=True, use_container_width=True)
            elif key == "etudiant":
                if st.button("⭐ 500 FCFA / mois", key=f"btn_{key}", use_container_width=True):
                    st.info("💳 Orange Money · Wave · MTN — bientôt disponible !")
            else:
                if st.button("💎 1 500 FCFA / mois", key=f"btn_{key}", use_container_width=True):
                    st.info("💳 Orange Money · Wave · MTN — bientôt disponible !")

    st.markdown("---")
    st.markdown("### 📱 Paiement Mobile Money")
    st.markdown("""
    <div style="background:#0f3460;border-radius:14px;padding:18px 20px;">
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px;">
            <div style="background:#ff6600;border-radius:8px;padding:8px 16px;
                        color:#fff;font-weight:700;font-size:13px;">🟠 Orange Money</div>
            <div style="background:#00a8e0;border-radius:8px;padding:8px 16px;
                        color:#fff;font-weight:700;font-size:13px;">💙 Wave</div>
            <div style="background:#f5c518;border-radius:8px;padding:8px 16px;
                        color:#000;font-weight:700;font-size:13px;">🟡 MTN MoMo</div>
        </div>
        <p style="color:#9ca3af;font-size:13px;margin:0;">
            Intégration en cours — disponible très bientôt. 🇨🇮
        </p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### ❓ Questions fréquentes")
    with st.expander("Mes données sont-elles confidentielles ?"):
        st.write("Oui. Tes conversations sont chiffrées et anonymisées. Personne ne peut les lire.")
    with st.expander("Puis-je annuler à tout moment ?"):
        st.write("Oui, sans engagement ni frais supplémentaires.")
    with st.expander("Tarifs institutionnels ?"):
        st.write("Oui ! Contactez-nous pour des tarifs pour universités et associations.")


# ============================================================
# 8. CONFIGURATION PAGE
# ============================================================
st.set_page_config(
    page_title="Aura — Ton espace bien-être",
    page_icon="✨",
    layout="wide"
)

# ============================================================
# 9. CSS
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@300;400;500;600;700&family=Crimson+Pro:ital@0;1&display=swap');

html, body, [class*="css"] { font-family: 'Nunito', sans-serif !important; }

.stApp {
    background-color: #ece5dd !important;
    background-image: url("data:image/svg+xml,%3Csvg width='80' height='80' viewBox='0 0 80 80' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none'%3E%3Cg fill='%23c8b8a2' fill-opacity='0.10'%3E%3Cpath d='M50 50v-6h-3v6h-6v3h6v6h3v-6h6v-3h-6zm0-44V0h-3v6h-6v3h6v6h3V9h6V6h-6zM8 50v-6H5v6H0v3h5v6h3v-6h6v-3H8zM8 6V0H5v6H0v3h5v6h3V9h6V6H8z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E") !important;
}
.main .block-container { padding: 0 !important; max-width: 100% !important; }

section[data-testid="stSidebar"] {
    background: #12172b !important;
    min-width: 240px !important; max-width: 240px !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}
section[data-testid="stSidebar"] > div { padding: 0 !important; }
section[data-testid="stSidebar"] * { color: #d4cef0 !important; font-family: 'Nunito', sans-serif !important; }
[data-testid="stSidebarCollapseButton"], [data-testid="collapsedControl"] { display: none !important; }

.sidebar-logo { padding: 22px 18px 14px; border-bottom: 1px solid rgba(255,255,255,0.07); margin-bottom: 6px; }
.sidebar-logo-title { font-size: 1.25rem; font-weight: 700; color: #fff !important; display: flex; align-items: center; gap: 8px; }
.sidebar-logo-sub { font-size: 11px; color: #7c6fa0 !important; font-style: italic; font-family: 'Crimson Pro', serif !important; margin-top: 2px; }
.sidebar-user { font-size: 12px; color: #a89fd4 !important; margin-top: 6px; }

section[data-testid="stSidebar"] .stRadio > div { gap: 5px !important; padding: 0 12px; }
section[data-testid="stSidebar"] .stRadio > div > label {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.07) !important;
    border-radius: 10px !important; padding: 10px 14px !important;
    cursor: pointer; transition: all 0.18s ease;
    font-size: 13px !important; font-weight: 500 !important;
    color: #c4bde8 !important; width: 100% !important; margin: 0 !important;
}
section[data-testid="stSidebar"] .stRadio > div > label:hover {
    background: rgba(124,58,237,0.18) !important;
    border-color: rgba(124,58,237,0.35) !important; color: #fff !important;
}
section[data-testid="stSidebar"] .stRadio input[type="radio"] { display: none !important; }

section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.05) !important; color: #c4bde8 !important;
    border: 1px solid rgba(255,255,255,0.08) !important; border-radius: 10px !important;
    font-size: 12px !important; padding: 7px 10px !important; transition: all 0.18s ease;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.10) !important; color: #fff !important;
}
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,0.07) !important; margin: 8px 0 !important; }

.stat-box {
    background: rgba(255,255,255,0.04); border-radius: 10px;
    padding: 10px 12px; margin: 4px 12px; font-size: 11px;
    color: #9b92c8 !important; border: 1px solid rgba(255,255,255,0.07); line-height: 1.9;
}

.topbar {
    background: linear-gradient(90deg, #1a1a2e 0%, #0f3460 100%);
    padding: 12px 32px; display: flex; align-items: center; gap: 14px;
    box-shadow: 0 1px 8px rgba(0,0,0,0.18); position: sticky; top: 0; z-index: 100;
}
.topbar-avatar {
    width: 42px; height: 42px; border-radius: 50%;
    background: linear-gradient(135deg, #7c3aed, #a855f7);
    display: flex; align-items: center; justify-content: center;
    font-size: 20px; flex-shrink: 0; box-shadow: 0 0 10px rgba(168,85,247,0.35);
}
.topbar-name { font-size: 16px; font-weight: 700; color: #fff; }
.topbar-subtitle { font-size: 11px; color: #c9b8f0; font-style: italic; font-family: 'Crimson Pro', serif; }
.topbar-status { font-size: 11px; color: #a5f3c4; display: flex; align-items: center; gap: 5px; margin-top: 2px; }
.status-dot { width: 6px; height: 6px; border-radius: 50%; background: #a5f3c4; display: inline-block; animation: pulse 2s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

.disclaimer {
    background: rgba(255,251,235,0.9); border-left: 3px solid #f59e0b;
    border-radius: 0 10px 10px 0; padding: 9px 18px; font-size: 0.79rem;
    color: #78350f; margin: 10px 20px; line-height: 1.6;
}
.date-sep {
    text-align: center; font-size: 11px; color: #7a6a58;
    background: rgba(255,255,255,0.65); padding: 4px 16px;
    border-radius: 10px; margin: 8px auto; width: fit-content; display: block;
}
.messages-container { padding: 12px 32px; min-height: 65vh; width: 100%; }

[data-testid="stChatMessage"] {
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 0 !important; margin: 0 !important;
}
[data-testid="stChatMessage"] > div { background: transparent !important; }

div[data-testid="stChatInput"] {
    background: #ddd5cc !important; border: none !important;
    border-top: 1px solid rgba(0,0,0,0.06) !important;
    border-radius: 0 !important; box-shadow: none !important; padding: 12px 32px !important;
}
div[data-testid="stChatInput"] > div {
    background: #fff !important; border-radius: 32px !important;
    border: 1px solid rgba(0,0,0,0.06) !important;
    box-shadow: 0 2px 10px rgba(0,0,0,0.08) !important; padding: 6px 8px 6px 18px !important;
}
div[data-testid="stChatInput"] textarea {
    font-family: 'Nunito', sans-serif !important; font-size: 15px !important;
    color: #2d2d2d !important; background: transparent !important;
    border: none !important; padding: 8px 4px !important; min-height: 42px !important;
}
div[data-testid="stChatInput"] textarea::placeholder { color: #aaa !important; font-style: italic; font-size: 14px !important; }
div[data-testid="stChatInput"] button {
    background: linear-gradient(135deg, #7c3aed, #a855f7) !important;
    border-radius: 50% !important; width: 44px !important; height: 44px !important;
    min-width: 44px !important; box-shadow: 0 2px 8px rgba(124,58,237,0.4) !important;
    transition: all 0.2s ease !important; border: none !important; flex-shrink: 0 !important;
}
div[data-testid="stChatInput"] button:hover { transform: scale(1.06) !important; }
div[data-testid="stChatInput"] button svg { fill: #fff !important; width: 18px !important; height: 18px !important; }

.login-wrapper { min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 20px; }
.login-card {
    background: rgba(255,255,255,0.95); border-radius: 24px; padding: 44px 48px;
    max-width: 480px; width: 100%; text-align: center; box-shadow: 0 8px 40px rgba(0,0,0,0.12);
}
.page-content { padding: 24px 32px; }
.stAlert { border-radius: 12px !important; }
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #c8b8a2; border-radius: 10px; }

@media (max-width: 768px) {
    .topbar { padding: 10px 14px; }
    .topbar-avatar { width: 36px; height: 36px; font-size: 17px; }
    .messages-container { padding: 8px 12px; }
    .page-content { padding: 16px 12px; }
    div[data-testid="stChatInput"] { padding: 10px 12px !important; }
    div[data-testid="stChatInput"] button { width: 40px !important; height: 40px !important; min-width: 40px !important; }
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 10. SESSION STATE
# ============================================================
defaults = {
    "user_id": None, "prenom": None, "messages": [],
    "conversation_initiee": False, "activer_voix": False,
    "voix_id": VOIX_MENTOR, "page": "💬 Chat",
    "profil": {}, "ex_actif": False, "ex_etape": 0, "ex_rep": 0,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ============================================================
# 11. LOGIN
# ============================================================
if st.session_state.user_id is None:
    st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)
    st.markdown("""
    <div class="login-card">
        <div style="font-size:52px;margin-bottom:10px;">✨</div>
        <div style="font-size:2.2rem;font-weight:800;color:#1a1a2e;margin-bottom:4px;">Aura</div>
        <div style="font-size:1rem;color:#6b7280;font-style:italic;font-family:'Crimson Pro',serif;margin-bottom:4px;">
            Ton espace de bien-être & de coaching
        </div>
        <div style="font-size:11px;color:#9ca3af;margin-bottom:28px;">
            Université Alassane Ouattara · Bouaké, Côte d'Ivoire
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("#### 👋 Bienvenue !")
        st.markdown("Entre ton prénom. Ta conversation est **confidentielle** et **chiffrée**. 🔐")
        prenom_input = st.text_input("", placeholder="Ton prénom...", label_visibility="collapsed")
        profil_input = st.selectbox("Style :", ["🧘 Mentor (voix posée)", "🤝 Camarade (voix dynamique)"])
        voix_choisie = VOIX_MENTOR if "Mentor" in profil_input else VOIX_CAMARADE
        voix_on = st.toggle("🔊 Activer la voix", value=False)

        if st.button("✨ Commencer avec Aura", use_container_width=True):
            prenom_nettoye = prenom_input.strip()
            if not valider_prenom(prenom_nettoye):
                st.error("Prénom invalide. Utilise uniquement des lettres (2-50 caractères).")
            else:
                try:
                    uid = obtenir_ou_creer_id_anonyme(prenom_nettoye)
                    st.session_state.user_id      = uid
                    st.session_state.prenom       = prenom_nettoye.capitalize()
                    st.session_state.voix_id      = voix_choisie
                    st.session_state.activer_voix = voix_on
                    st.session_state.profil       = charger_profil(uid)

                    historique = charger_historique(uid)
                    if historique:
                        st.session_state.messages = [
                            {"role": m["role"], "content": m["content"],
                             "horodatage": m.get("horodatage", "")}
                            for m in historique
                        ]
                        st.session_state.conversation_initiee = True
                    else:
                        st.session_state.messages = []
                        st.session_state.conversation_initiee = False

                    journaliser(uid, "connexion")
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))
                except Exception as e:
                    logging.error(f"Erreur login : {type(e).__name__}")
                    st.error("Une erreur est survenue. Réessaie.")

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ============================================================
# 12. VARIABLES ACTIVES
# ============================================================
prenom       = st.session_state.prenom
activer_voix = st.session_state.activer_voix
voix_id      = st.session_state.voix_id
profil       = st.session_state.profil
premium      = est_premium(st.session_state.user_id)

# ============================================================
# 13. TOPBAR
# ============================================================
badge_premium = ' <span style="background:#a855f7;color:#fff;font-size:10px;padding:2px 7px;border-radius:10px;margin-left:6px;">⭐ Premium</span>' if premium else ""
st.markdown(f"""
<div class="topbar">
  <div class="topbar-avatar">✨</div>
  <div style="flex:1;">
    <div class="topbar-name">Aura{badge_premium}</div>
    <div class="topbar-subtitle">Ton espace de bien-être — UAO Bouaké</div>
    <div class="topbar-status"><span class="status-dot"></span> En ligne · disponible 24h/24</div>
  </div>
  <div style="text-align:right;line-height:1.7;">
    <div style="font-size:13px;color:#e0d7f5;font-weight:600;">👤 {prenom}</div>
    <div style="font-size:10px;color:#7c6fa0;">ID : {st.session_state.user_id}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ============================================================
# 14. SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown(f"""
    <div class="sidebar-logo">
        <div class="sidebar-logo-title">✨ Aura</div>
        <div class="sidebar-logo-sub">Coach de bien-être · UAO</div>
        <div class="sidebar-user">👤 {prenom} {'⭐' if premium else ''}</div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio(
        "",
        ["💬 Chat", "🧘 Exercices", "📊 Tableau de bord", "💰 Offres"],
        label_visibility="collapsed"
    )
    st.session_state.page = page

    st.markdown("<hr>", unsafe_allow_html=True)

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🗑️ Nouveau", use_container_width=True):
            st.session_state.messages = []
            st.session_state.conversation_initiee = False
            st.rerun()
    with col_b:
        if st.button("🚪 Changer", use_container_width=True):
            for k in ["user_id","prenom","messages","conversation_initiee","profil"]:
                st.session_state[k] = None if k != "messages" else []
            st.session_state.conversation_initiee = False
            st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)

    stats = compter_messages(st.session_state.user_id)
    autorise, nb_today, limite = verifier_limite_messages(st.session_state.user_id)
    st.markdown(f"""
    <div class="stat-box">
        💬 {stats['nb_messages']} messages total<br>
        📅 {stats['premiere_session']}<br>
        🕐 {stats['derniere_session']}<br>
        📊 Aujourd'hui : {nb_today} / {'∞' if premium else limite}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<hr>", unsafe_allow_html=True)

    activer_voix_sb = st.toggle("🔊 Voix", value=activer_voix)
    st.session_state.activer_voix = activer_voix_sb

    if st.button("🗑️ Effacer historique", use_container_width=True):
        supprimer_historique(st.session_state.user_id)
        st.session_state.messages = []
        st.session_state.conversation_initiee = False
        st.success("Effacé ✓")
        st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown("""
    <div style="padding:0 12px;">
        <div style="font-size:10px;color:#7c6fa0;font-weight:600;
                    text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">
            🆘 Urgences CI
        </div>
        <div style="font-size:12px;color:#c4bde8;line-height:2.2;">
            📞 <strong style="color:#fff;">110 / 111</strong> Police<br>
            🚑 <strong style="color:#fff;">185</strong> SAMU<br>
            🔥 <strong style="color:#fff;">180</strong> Pompiers
        </div>
    </div>
    """, unsafe_allow_html=True)

# ============================================================
# 15. ROUTEUR
# ============================================================
page = st.session_state.page

if page == "🧘 Exercices":
    st.markdown('<div class="page-content">', unsafe_allow_html=True)
    afficher_exercices()
    st.markdown('</div>', unsafe_allow_html=True)

elif page == "📊 Tableau de bord":
    st.markdown('<div class="page-content">', unsafe_allow_html=True)
    afficher_dashboard(st.session_state.user_id, prenom)
    st.markdown('</div>', unsafe_allow_html=True)

elif page == "💰 Offres":
    st.markdown('<div class="page-content">', unsafe_allow_html=True)
    afficher_plans()
    st.markdown('</div>', unsafe_allow_html=True)

else:
    # ── CHAT ──
    st.markdown(f"""
    <div class="disclaimer">
      ⚕️ <strong>Important :</strong> Aura est un outil de soutien émotionnel.
      En cas de crise : <strong>110/111</strong> · <strong>185</strong> · <strong>180</strong>
    </div>
    <div class="date-sep">— {datetime.now().strftime("%A %d %B %Y")} —</div>
    """, unsafe_allow_html=True)

    # Message de bienvenue personnalisé
    if not st.session_state.conversation_initiee:
        if profil and profil.get("notes_aura"):
            msg_bienvenue = (
                f"Bon retour {prenom} ✨\n\n"
                f"Je me souviens de toi. La dernière fois tu traversais des moments "
                f"difficiles — comment tu vas aujourd'hui ?"
            )
        else:
            msg_bienvenue = (
                f"Bonjour {prenom} ✨\n\n"
                f"Je suis **Aura**, ton espace de bien-être. "
                f"Je suis là pour t'écouter, sans jugement et en toute confidentialité.\n\n"
                f"Comment tu te sens aujourd'hui ?"
            )
        st.session_state.messages = [
            {"role": "assistant", "content": msg_bienvenue,
             "horodatage": datetime.now().strftime("%H:%M")}
        ]
        st.session_state.conversation_initiee = True

    # Affichage messages
    st.markdown('<div class="messages-container">', unsafe_allow_html=True)
    for msg in st.session_state.messages:
        h = msg.get("horodatage", "")
        heure = h[11:16] if len(h) >= 16 else (h[:5] if h else datetime.now().strftime("%H:%M"))
        if msg["role"] == "assistant":
            bulle_bot(msg["content"], heure)
        else:
            bulle_user(msg["content"], heure)
    st.markdown('</div>', unsafe_allow_html=True)

    # Saisie
    if prompt := st.chat_input("Exprime-toi librement, je t'écoute..."):

        # Vérification limite
        autorise, nb_today, limite = verifier_limite_messages(st.session_state.user_id)
        if not autorise:
            st.warning(f"⚠️ Limite de {limite} messages/jour atteinte. Passe au plan Étudiant pour des messages illimités !")
            st.stop()

        # Détection crise
        MOTS_CRISE = ["suicid", "mourir", "me tuer", "en finir",
                      "plus envie de vivre", "automutil", "me faire du mal"]
        if any(mot in prompt.lower() for mot in MOTS_CRISE):
            st.error("🆘 **Appelle maintenant :** 📞 110/111 · 🚑 185 · 🔥 180")

        heure_now = datetime.now().strftime("%H:%M")
        bulle_user(prompt, heure_now)
        sauvegarder_conversation(st.session_state.user_id, "user", prompt)
        st.session_state.messages.append(
            {"role": "user", "content": prompt, "horodatage": heure_now}
        )

        historique_groq = [
            {"role": m["role"], "content": m["content"]}
            for m in st.session_state.messages
        ]

        with st.spinner(""):
            reponse = obtenir_reponse(historique_groq, prenom, profil)

        heure_rep = datetime.now().strftime("%H:%M")
        bulle_bot(reponse, heure_rep)

        if st.session_state.activer_voix:
            audio = synthese_vocale(reponse, st.session_state.voix_id)
            if audio:
                st.audio(audio, format="audio/mpeg", autoplay=True)

        sauvegarder_conversation(st.session_state.user_id, "assistant", reponse)
        st.session_state.messages.append(
            {"role": "assistant", "content": reponse, "horodatage": heure_rep}
        )

        # Mise à jour profil en arrière-plan (tous les 5 messages)
        if len(st.session_state.messages) % 10 == 0:
            mettre_a_jour_profil_ia(
                st.session_state.user_id,
                prenom,
                historique_groq,
                st.session_state.profil
            )
            st.session_state.profil = charger_profil(st.session_state.user_id)