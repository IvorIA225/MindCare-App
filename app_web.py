import streamlit as st
import requests
import os
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime
from database import (
    init_db,
    obtenir_ou_creer_id_anonyme,
    sauvegarder_conversation,
    charger_historique,
    lister_prenoms,
    supprimer_historique,
    compter_messages
)

load_dotenv()
init_db()

# ============================================================
# 1. CONFIGURATION
# ============================================================
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
VOIX_MENTOR        = os.getenv("VOIX_MENTOR", "pNInz6obpgDQGcFmaJgB")
VOIX_CAMARADE      = os.getenv("VOIX_CAMARADE", "ErXwobaYiN019PkySvjV")

client = Groq(api_key=GROQ_API_KEY)

# ============================================================
# 2. PROMPT SYSTÈME — Personnalité d'Aura
# ============================================================
SYSTEM_PROMPT = """Tu es Aura, une assistante de bien-être et de coaching mental bienveillante,
empathique et professionnelle. Tu as été conçue spécialement pour accompagner les étudiants
de l'Université Alassane Ouattara (Bouaké, Côte d'Ivoire) dans leur vie académique et personnelle.

Tes principes fondamentaux :
- Écoute active et sans jugement
- Valide toujours les émotions AVANT de proposer une solution
- Utilise des techniques de TCC (Thérapie Cognitive et Comportementale) et de pleine conscience
- Pose une seule question à la fois, jamais plusieurs
- Réponses courtes, chaleureuses et humaines (maximum 3-4 phrases)
- Appelle toujours l'étudiant par son prénom si tu le connais
- Tu comprends les réalités des étudiants africains : pression familiale, manque de ressources,
  stress des examens, isolement, difficultés financières
- Si l'étudiant exprime des pensées suicidaires ou d'automutilation :
  oriente-le IMMÉDIATEMENT vers le 110 ou 111 (Côte d'Ivoire) et exprime ta compassion

Tu parles toujours en français, avec douceur, chaleur et bienveillance.
Tu es Aura — une lumière douce dans les moments difficiles. ✨"""

# ============================================================
# 3. FONCTIONS IA ET VOIX
# ============================================================
def obtenir_reponse(historique: list, prenom: str) -> str:
    prompt_system = SYSTEM_PROMPT
    if prenom:
        prompt_system += f"\n\nL'étudiant(e) s'appelle {prenom}. Utilise son prénom naturellement."
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": prompt_system}] + historique,
            temperature=0.75,
            max_tokens=400,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Je suis désolée, une erreur s'est produite : {str(e)}"


def synthese_vocale(texte: str, voix_id: str):
    if not ELEVENLABS_API_KEY:
        return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voix_id}"
    headers = {"xi-api-key": ELEVENLABS_API_KEY, "Content-Type": "application/json"}
    payload = {
        "text": texte,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.6, "similarity_boost": 0.8}
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        st.warning(f"Voix indisponible : {e}")
    return None


def bulle_bot(texte: str, heure: str = None):
    if not heure:
        heure = datetime.now().strftime("%H:%M")
    texte_html = texte.replace("\n\n", "<br><br>").replace("\n", "<br>")
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-start;align-items:flex-start;
                margin:8px 0;width:100%;">
      <div style="width:0;height:0;border-top:10px solid #ffffff;
                  border-right:10px solid transparent;flex-shrink:0;margin-top:2px;"></div>
      <div style="background:#ffffff;border-radius:0px 18px 18px 18px;
                  padding:12px 16px;max-width:70%;
                  font-family:'Nunito',sans-serif;font-size:15px;
                  line-height:1.75;color:#2d2d2d;
                  box-shadow:0 1px 4px rgba(0,0,0,0.10);word-wrap:break-word;">
        {texte_html}
        <div style="font-size:11px;color:#8a9e8a;text-align:right;margin-top:8px;">{heure}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def bulle_user(texte: str, heure: str = None):
    if not heure:
        heure = datetime.now().strftime("%H:%M")
    texte_html = texte.replace("\n\n", "<br><br>").replace("\n", "<br>")
    st.markdown(f"""
    <div style="display:flex;justify-content:flex-end;align-items:flex-start;
                margin:8px 0;width:100%;">
      <div style="background:#d9fdd3;border-radius:18px 0px 18px 18px;
                  padding:12px 16px;max-width:70%;
                  font-family:'Nunito',sans-serif;font-size:15px;
                  line-height:1.75;color:#111;
                  box-shadow:0 1px 4px rgba(0,0,0,0.10);word-wrap:break-word;">
        {texte_html}
        <div style="font-size:11px;color:#5a8a5a;text-align:right;margin-top:8px;">{heure} ✓✓</div>
      </div>
      <div style="width:0;height:0;border-top:10px solid #d9fdd3;
                  border-left:10px solid transparent;flex-shrink:0;margin-top:2px;"></div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 4. CONFIGURATION PAGE
# ============================================================
st.set_page_config(
    page_title="Aura — Ton espace bien-être",
    page_icon="✨",
    layout="wide"
)

# ============================================================
# 5. CSS RESPONSIVE
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@300;400;500;600;700&family=Crimson+Pro:ital@0;1&display=swap');

html, body, [class*="css"] {
    font-family: 'Nunito', sans-serif !important;
}

.stApp {
    background-color: #ece5dd !important;
    background-image: url("data:image/svg+xml,%3Csvg width='80' height='80' viewBox='0 0 80 80' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none'%3E%3Cg fill='%23c8b8a2' fill-opacity='0.12'%3E%3Cpath d='M50 50v-6h-3v6h-6v3h6v6h3v-6h6v-3h-6zm0-44V0h-3v6h-6v3h6v6h3V9h6V6h-6zM8 50v-6H5v6H0v3h5v6h3v-6h6v-3H8zM8 6V0H5v6H0v3h5v6h3V9h6V6H8z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E") !important;
}

.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 60%, #0f3460 100%) !important;
    min-width: 270px !important;
}
section[data-testid="stSidebar"] * {
    color: #e0d7f5 !important;
    font-family: 'Nunito', sans-serif !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #c9b8f0 !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.08) !important;
    color: #e0d7f5 !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 12px !important;
    transition: all 0.2s ease;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.16) !important;
}
section[data-testid="stSidebar"] input {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    border-radius: 12px !important;
    color: #e0d7f5 !important;
}
section[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.18) !important;
    border-radius: 12px !important;
}

.main .block-container { padding: 0 !important; max-width: 100% !important; }

.topbar {
    background: linear-gradient(90deg, #1a1a2e 0%, #0f3460 100%);
    padding: 14px 28px;
    display: flex;
    align-items: center;
    gap: 14px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.2);
    position: sticky;
    top: 0;
    z-index: 100;
}
.topbar-avatar {
    width: 46px; height: 46px; border-radius: 50%;
    background: linear-gradient(135deg, #7c3aed, #a855f7);
    display: flex; align-items: center; justify-content: center;
    font-size: 22px; flex-shrink: 0;
    box-shadow: 0 0 12px rgba(168,85,247,0.4);
}
.topbar-name { font-size: 17px; font-weight: 700; color: #fff; letter-spacing: 0.3px; }
.topbar-subtitle {
    font-size: 11px; color: #c9b8f0;
    font-style: italic; font-family: 'Crimson Pro', serif;
}
.topbar-status {
    font-size: 11px; color: #a5f3c4;
    display: flex; align-items: center; gap: 5px; margin-top: 2px;
}
.status-dot {
    width: 7px; height: 7px; border-radius: 50%;
    background: #a5f3c4; display: inline-block;
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

.disclaimer {
    background: rgba(255,251,235,0.93);
    border-left: 4px solid #f59e0b;
    border-radius: 0 12px 12px 0;
    padding: 10px 20px;
    font-size: 0.82rem;
    color: #78350f;
    margin: 12px 24px;
    line-height: 1.7;
}

.date-sep {
    text-align: center; font-size: 12px; color: #7a6a58;
    background: rgba(255,255,255,0.72); padding: 5px 18px;
    border-radius: 12px; margin: 10px auto;
    width: fit-content; display: block;
}

.messages-container { padding: 10px 28px; min-height: 62vh; }

[data-testid="stChatMessage"] {
    background: transparent !important; border: none !important;
    box-shadow: none !important; padding: 0 !important; margin: 0 !important;
}
[data-testid="stChatMessage"] > div { background: transparent !important; }

div[data-testid="stChatInput"] {
    background: #ece5dd !important; border: none !important;
    border-top: 1px solid rgba(0,0,0,0.08) !important;
    border-radius: 0 !important; box-shadow: none !important;
    padding: 12px 24px !important;
}
div[data-testid="stChatInput"] > div {
    background: #ffffff !important; border-radius: 30px !important;
    border: none !important; box-shadow: 0 2px 8px rgba(0,0,0,0.12) !important;
    padding: 6px 10px !important;
}
div[data-testid="stChatInput"] textarea {
    font-family: 'Nunito', sans-serif !important; font-size: 15px !important;
    color: #333 !important; background: transparent !important;
    border: none !important; padding: 8px 14px !important; line-height: 1.6 !important;
}
div[data-testid="stChatInput"] textarea::placeholder {
    color: #b0a898 !important; font-style: italic;
}
div[data-testid="stChatInput"] button {
    background: linear-gradient(135deg, #7c3aed, #a855f7) !important;
    border-radius: 50% !important;
    width: 46px !important; height: 46px !important; min-width: 46px !important;
    box-shadow: 0 3px 10px rgba(124,58,237,0.4) !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stChatInput"] button:hover {
    transform: scale(1.08) !important;
    box-shadow: 0 4px 14px rgba(124,58,237,0.55) !important;
}
div[data-testid="stChatInput"] button svg {
    fill: #ffffff !important; width: 20px !important; height: 20px !important;
}

.login-wrapper {
    min-height: 100vh; display: flex;
    align-items: center; justify-content: center;
    padding: 20px;
}
.login-card {
    background: rgba(255,255,255,0.94);
    border-radius: 28px; padding: 44px 52px;
    max-width: 500px; width: 100%;
    text-align: center;
    box-shadow: 0 8px 40px rgba(0,0,0,0.14);
}
.login-title { font-size: 2.4rem; font-weight: 800; color: #1a1a2e; margin-bottom: 4px; }
.login-subtitle {
    font-size: 1.05rem; color: #6b7280;
    font-style: italic; font-family: 'Crimson Pro', serif; margin-bottom: 6px;
}
.login-univ { font-size: 12px; color: #9ca3af; margin-bottom: 28px; }

.stat-box {
    background: rgba(255,255,255,0.07); border-radius: 14px;
    padding: 12px 14px; margin: 6px 0; font-size: 0.82rem;
    color: #c9b8f0 !important; border: 1px solid rgba(255,255,255,0.1);
    line-height: 2;
}

.stAlert { border-radius: 14px !important; margin: 8px 24px !important; }

::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #c8b8a2; border-radius: 10px; }

@media (max-width: 768px) {
    .topbar { padding: 10px 14px; }
    .topbar-avatar { width: 38px; height: 38px; font-size: 18px; }
    .topbar-name { font-size: 14px; }
    .messages-container { padding: 8px 10px; }
    .login-card { padding: 30px 20px; }
    div[data-testid="stChatInput"] { padding: 10px 12px !important; }
    div[data-testid="stChatInput"] button {
        width: 42px !important; height: 42px !important; min-width: 42px !important;
    }
}
</style>
""", unsafe_allow_html=True)

# ============================================================
# 6. SESSION STATE
# ============================================================
for key, val in {
    "user_id": None,
    "prenom": None,
    "messages": [],
    "conversation_initiee": False,
    "activer_voix": False,
    "voix_id": VOIX_MENTOR,
}.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ============================================================
# 7. ÉCRAN DE LOGIN
# ============================================================
if st.session_state.user_id is None:

    st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)
    st.markdown("""
    <div class="login-card">
        <div style="font-size:56px;margin-bottom:10px;">✨</div>
        <div class="login-title">Aura</div>
        <div class="login-subtitle">Ton espace de bien-être & de coaching</div>
        <div class="login-univ">Université Alassane Ouattara · Bouaké, Côte d'Ivoire</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("#### 👋 Bienvenue !")
        st.markdown(
            "Entre ton prénom pour commencer. "
            "Ta conversation est **confidentielle** et **anonymisée**. 🔐"
        )
        prenom_input = st.text_input(
            "", placeholder="Ton prénom...", label_visibility="collapsed"
        )
        profil_input = st.selectbox(
            "Style d'accompagnement :",
            ["🧘 Mentor (voix posée)", "🤝 Camarade (voix dynamique)"]
        )
        voix_choisie = VOIX_MENTOR if "Mentor" in profil_input else VOIX_CAMARADE
        voix_on = st.toggle("🔊 Activer la voix", value=False)

        if st.button("✨ Commencer avec Aura", use_container_width=True):
            if prenom_input.strip():
                uid = obtenir_ou_creer_id_anonyme(prenom_input.strip())
                st.session_state.user_id      = uid
                st.session_state.prenom       = prenom_input.strip()
                st.session_state.voix_id      = voix_choisie
                st.session_state.activer_voix = voix_on

                # Charger historique existant (mémoire long terme)
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
                st.rerun()
            else:
                st.warning("Merci d'entrer ton prénom pour continuer. 🙏")

    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ============================================================
# 8. VARIABLES DE SESSION ACTIVES
# ============================================================
prenom       = st.session_state.prenom
activer_voix = st.session_state.activer_voix
voix_id      = st.session_state.voix_id

# ============================================================
# 9. BARRE DU HAUT
# ============================================================
st.markdown(f"""
<div class="topbar">
  <div class="topbar-avatar">✨</div>
  <div style="flex:1;">
    <div class="topbar-name">Aura</div>
    <div class="topbar-subtitle">Ton espace de bien-être — UAO Bouaké</div>
    <div class="topbar-status">
      <span class="status-dot"></span> En ligne · disponible 24h/24
    </div>
  </div>
  <div style="font-size:13px;color:#c9b8f0;text-align:right;line-height:1.8;">
    👤 {prenom}<br>
    <span style="font-size:10px;opacity:0.6;">ID : {st.session_state.user_id}</span>
  </div>
</div>

<div class="disclaimer">
  ⚕️ <strong>Important :</strong> Aura est un outil de soutien émotionnel,
  pas un substitut à un professionnel de santé. En cas de crise :
  <strong>110 / 111</strong> Police · <strong>185</strong> SAMU · <strong>180</strong> Pompiers
</div>

<div class="date-sep">— {datetime.now().strftime("%A %d %B %Y")} —</div>
""", unsafe_allow_html=True)

# ============================================================
# 10. SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## ✨ Aura")
    st.markdown(f"*Bonjour, **{prenom}** !*")
    st.markdown("---")

    if st.button("🗑️ Nouvelle conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_initiee = False
        st.rerun()

    if st.button("🚪 Changer d'utilisateur", use_container_width=True):
        st.session_state.user_id             = None
        st.session_state.prenom              = None
        st.session_state.messages            = []
        st.session_state.conversation_initiee = False
        st.rerun()

    st.markdown("---")

    stats = compter_messages(st.session_state.user_id)
    st.markdown(f"""
    <div class="stat-box">
        👤 <strong style="color:#e0d7f5">{prenom}</strong><br>
        🔐 ID : <code style="font-size:10px;color:#c9b8f0">{st.session_state.user_id}</code><br>
        💬 {stats['nb_messages']} messages envoyés<br>
        📅 Depuis : {stats['premiere_session']}<br>
        🕐 Dernière : {stats['derniere_session']}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### ⚙️ Paramètres")
    activer_voix_sidebar = st.toggle("🔊 Voix activée", value=activer_voix)
    st.session_state.activer_voix = activer_voix_sidebar

    st.markdown("---")
    if st.button("🗑️ Effacer mon historique", use_container_width=True):
        supprimer_historique(st.session_state.user_id)
        st.session_state.messages            = []
        st.session_state.conversation_initiee = False
        st.success("Historique effacé. ✓")
        st.rerun()

    st.markdown("---")
    st.markdown("### 🆘 Urgences — Côte d'Ivoire")
    st.markdown("📞 **110 / 111** — Police Secours")
    st.markdown("🚑 **185** — SAMU")
    st.markdown("🔥 **180** — Sapeurs Pompiers")

# ============================================================
# 11. MESSAGE DE BIENVENUE
# ============================================================
if not st.session_state.conversation_initiee:
    msg_bienvenue = (
        f"Bonjour {prenom} ✨\n\n"
        f"Je suis **Aura**, ton espace de bien-être et de soutien. "
        f"Je suis là pour t'écouter, sans jugement et en toute confidentialité.\n\n"
        f"Comment tu te sens aujourd'hui ?"
    )
    st.session_state.messages = [
        {"role": "assistant", "content": msg_bienvenue,
         "horodatage": datetime.now().strftime("%H:%M")}
    ]
    st.session_state.conversation_initiee = True

# ============================================================
# 12. AFFICHAGE DES MESSAGES
# ============================================================
st.markdown('<div class="messages-container">', unsafe_allow_html=True)

for msg in st.session_state.messages:
    horodatage = msg.get("horodatage", "")
    # Extraire HH:MM si format datetime complet
    if horodatage and len(horodatage) > 5:
        heure = horodatage[11:16] if len(horodatage) >= 16 else horodatage[:5]
    else:
        heure = horodatage or datetime.now().strftime("%H:%M")

    if msg["role"] == "assistant":
        bulle_bot(msg["content"], heure)
    else:
        bulle_user(msg["content"], heure)

st.markdown('</div>', unsafe_allow_html=True)

# ============================================================
# 13. SAISIE ET RÉPONSE
# ============================================================
if prompt := st.chat_input("💬  Exprime-toi librement, je t'écoute..."):

    MOTS_CRISE = [
        "suicid", "mourir", "me tuer", "en finir",
        "plus envie de vivre", "automutil", "me faire du mal", "je veux mourir"
    ]
    if any(mot in prompt.lower() for mot in MOTS_CRISE):
        st.error("""
        🆘 **Si tu es en danger immédiat, appelle maintenant :**
        - 📞 **110 / 111** — Police Secours
        - 🚑 **185** — SAMU (Aide Médicale Urgente)
        - 🔥 **180** — Sapeurs Pompiers
        """)

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

    with st.spinner("Aura réfléchit... ✨"):
        reponse = obtenir_reponse(historique_groq, prenom)

    heure_rep = datetime.now().strftime("%H:%M")
    bulle_bot(reponse, heure_rep)

    if st.session_state.activer_voix:
        audio_data = synthese_vocale(reponse, st.session_state.voix_id)
        if audio_data:
            st.audio(audio_data, format="audio/mpeg", autoplay=True)

    sauvegarder_conversation(st.session_state.user_id, "assistant", reponse)
    st.session_state.messages.append(
        {"role": "assistant", "content": reponse, "horodatage": heure_rep}
    )