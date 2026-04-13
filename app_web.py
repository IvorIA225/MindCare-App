import streamlit as st
import requests
import os
from Groq import Groq
from dotenv import load_dotenv
from datetime import datetime
from database import (
    init_db, sauvegarder_message, charger_historique,
    lister_prenoms, supprimer_historique, compter_messages
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
# 2. PROMPT SYSTÈME
# ============================================================
SYSTEM_PROMPT = """Tu es MindCare, un coach mental bienveillant, empathique et professionnel.
Tu accompagnes des personnes dépressives ou traversant des moments difficiles.

Tes principes fondamentaux :
- Écoute active, sans jugement
- Valide toujours les émotions AVANT de proposer une solution
- Utilise des techniques de TCC et de pleine conscience
- Pose une seule question à la fois, jamais plusieurs
- Réponses courtes, chaleureuses et humaines (maximum 3-4 phrases)
- Appelle toujours l'utilisateur par son prénom si tu le connais
- Si la personne exprime des pensées suicidaires ou d'automutilation :
  oriente-la IMMÉDIATEMENT vers le 3114 et exprime ta compassion

Tu parles toujours en français, avec douceur et bienveillance."""

# ============================================================
# 3. FONCTIONS
# ============================================================
def obtenir_reponse(historique: list, prenom: str) -> str:
    prompt_system = SYSTEM_PROMPT
    if prenom:
        prompt_system += f"\n\nLe prénom de l'utilisateur est : {prenom}."
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": prompt_system}] + historique,
            temperature=0.75,
            max_tokens=350,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Je suis désolé, une erreur s'est produite : {str(e)}"


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


def bulle_bot(texte: str):
    heure = datetime.now().strftime("%H:%M")
    texte_html = texte.replace("\n", "<br>")
    st.markdown(f"""
    <div style="display:flex; justify-content:flex-start; margin:6px 0;">
      <div style="
        width:0; height:0;
        border-top:10px solid #ffffff;
        border-right:10px solid transparent;
        flex-shrink:0; margin-top:0;
      "></div>
      <div style="
        background:#ffffff;
        border-radius:0px 16px 16px 16px;
        padding:10px 14px;
        max-width:72%;
        font-family:'Nunito',sans-serif;
        font-size:14px;
        line-height:1.65;
        color:#2d2d2d;
        box-shadow:0 1px 3px rgba(0,0,0,0.1);
      ">
        {texte_html}
        <div style="font-size:10px;color:#8a9e8a;text-align:right;margin-top:6px;">{heure}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


def bulle_user(texte: str):
    heure = datetime.now().strftime("%H:%M")
    texte_html = texte.replace("\n", "<br>")
    st.markdown(f"""
    <div style="display:flex; justify-content:flex-end; margin:6px 0;">
      <div style="
        background:#d9fdd3;
        border-radius:16px 16px 0px 16px;
        padding:10px 14px;
        max-width:72%;
        font-family:'Nunito',sans-serif;
        font-size:14px;
        line-height:1.65;
        color:#111;
        box-shadow:0 1px 3px rgba(0,0,0,0.1);
      ">
        {texte_html}
        <div style="font-size:10px;color:#5a8a5a;text-align:right;margin-top:6px;">{heure} ✓✓</div>
      </div>
      <div style="
        width:0; height:0;
        border-top:10px solid #d9fdd3;
        border-left:10px solid transparent;
        flex-shrink:0; margin-top:0;
      "></div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# 4. CONFIGURATION PAGE
# ============================================================
st.set_page_config(
    page_title="MindCare — Coach Mental",
    page_icon="🌿",
    layout="centered"
)

# ============================================================
# 5. CSS GLOBAL
# ============================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Nunito:wght@300;400;500;600&family=Crimson+Pro:ital@0;1&display=swap');

html, body, [class*="css"] {
    font-family: 'Nunito', sans-serif !important;
}

/* Fond façon papier WhatsApp */
.stApp {
    background-color: #f0ebe3 !important;
    background-image: url("data:image/svg+xml,%3Csvg width='60' height='60' viewBox='0 0 60 60' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none'%3E%3Cg fill='%23c8b8a2' fill-opacity='0.15'%3E%3Cpath d='M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E") !important;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #2d4a3e 0%, #1e3329 100%) !important;
}
section[data-testid="stSidebar"] * {
    color: #c8e6c9 !important;
    font-family: 'Nunito', sans-serif !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 {
    color: #9FE1CB !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255,255,255,0.08) !important;
    color: #c8e6c9 !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 12px !important;
    transition: all 0.2s ease;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,0.18) !important;
}
section[data-testid="stSidebar"] input {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 12px !important;
    color: #E1F5EE !important;
}
section[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.07) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 12px !important;
}

/* Contenu principal */
.main .block-container {
    padding-top: 0 !important;
    padding-bottom: 0 !important;
    max-width: 780px !important;
}

/* Masquer les bulles Streamlit par défaut */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
}
[data-testid="stChatMessage"] > div {
    background: transparent !important;
}

/* Barre verte du haut */
.topbar {
    background: #2d4a3e;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 0;
}
.topbar-avatar {
    width: 40px; height: 40px;
    border-radius: 50%;
    background: #5DCAA5;
    display: flex; align-items: center; justify-content: center;
    font-size: 20px;
}
.topbar-name { font-size: 15px; font-weight: 600; color: #fff; }
.topbar-status { font-size: 11px; color: #9FE1CB; }

/* Disclaimer */
.disclaimer {
    background: rgba(255,251,240,0.92);
    border-left: 4px solid #e8c96a;
    border-radius: 0 12px 12px 0;
    padding: 9px 14px;
    font-size: 0.78rem;
    color: #7a6020;
    margin: 10px 16px;
    line-height: 1.6;
}

/* Séparateur de date */
.date-sep {
    text-align: center;
    font-size: 11px;
    color: #7a6a58;
    background: rgba(255,255,255,0.7);
    padding: 4px 14px;
    border-radius: 10px;
    margin: 8px auto;
    width: fit-content;
    display: block;
}

/* Zone de saisie style WhatsApp */
div[data-testid="stChatInput"] {
    background: #f0ebe3 !important;
    border: none !important;
    border-top: 1px solid rgba(0,0,0,0.08) !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 10px 14px !important;
}
div[data-testid="stChatInput"] > div {
    background: #ffffff !important;
    border-radius: 26px !important;
    border: none !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.12) !important;
    padding: 4px 8px !important;
}
div[data-testid="stChatInput"] textarea {
    font-family: 'Nunito', sans-serif !important;
    font-size: 14px !important;
    color: #333 !important;
    background: transparent !important;
    border: none !important;
    padding: 6px 10px !important;
}
div[data-testid="stChatInput"] button {
    background: #2d4a3e !important;
    border-radius: 50% !important;
    width: 40px !important;
    height: 40px !important;
    box-shadow: 0 2px 6px rgba(45,74,62,0.4) !important;
}
div[data-testid="stChatInput"] button:hover {
    background: #1D9E75 !important;
}
div[data-testid="stChatInput"] button svg {
    fill: #ffffff !important;
}

/* Stat box sidebar */
.stat-box {
    background: rgba(255,255,255,0.07);
    border-radius: 14px;
    padding: 12px 14px;
    margin: 6px 0;
    font-size: 0.82rem;
    color: #9FE1CB !important;
    border: 1px solid rgba(255,255,255,0.1);
    line-height: 2;
}

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #c8b8a2; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ============================================================
# 6. BARRE DU HAUT
# ============================================================
st.markdown("""
<div class="topbar">
  <div class="topbar-avatar">🌿</div>
  <div>
    <div class="topbar-name">MindCare — Coach Mental</div>
    <div class="topbar-status">● En ligne · disponible</div>
  </div>
</div>
<div class="disclaimer">
  ⚕️ <strong>Important :</strong> Outil de soutien émotionnel uniquement.
  En cas de crise appelez le <strong>3114</strong> (France) ou vos urgences locales.
</div>
<div class="date-sep">— Aujourd'hui —</div>
""", unsafe_allow_html=True)

# ============================================================
# 7. SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## 🌿 MindCare")
    st.markdown("---")
    etudiant = st.text_input("👤 Votre prénom :", placeholder="Ex: Aminata")
    profil = st.selectbox(
        "🎭 Style d'accompagnement :",
        ["🧘 Mentor (voix posée)", "🤝 Camarade (voix dynamique)"]
    )
    voix_id = VOIX_MENTOR if "Mentor" in profil else VOIX_CAMARADE
    activer_voix = st.toggle("🔊 Activer la voix", value=False)
    st.markdown("---")
    if st.button("🗑️ Nouvelle conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_initiee = False
        st.rerun()
    st.markdown("---")
    st.markdown("### 📂 Historique")
    prenoms_enregistres = lister_prenoms()
    if prenoms_enregistres:
        prenom_selectionne = st.selectbox(
            "Charger une session :",
            ["— Nouvelle session —"] + prenoms_enregistres
        )
        if prenom_selectionne != "— Nouvelle session —":
            stats = compter_messages(prenom_selectionne)
            st.markdown(f"""
            <div class="stat-box">
                👤 <strong style="color:#E1F5EE">{prenom_selectionne}</strong><br>
                💬 {stats['nb_messages']} messages envoyés<br>
                📅 Depuis le {stats['premiere_session'][:10] if stats['premiere_session'] else 'N/A'}<br>
                🕐 Dernière : {stats['derniere_session'][:10] if stats['derniere_session'] else 'N/A'}
            </div>
            """, unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("📥 Charger", use_container_width=True):
                    historique_charge = charger_historique(prenom_selectionne)
                    st.session_state.messages = [
                        {"role": m["role"], "content": m["content"]}
                        for m in historique_charge
                    ]
                    st.session_state.conversation_initiee = True
                    st.rerun()
            with col2:
                if st.button("🗑️ Supprimer", use_container_width=True):
                    supprimer_historique(prenom_selectionne)
                    st.success("Supprimé !")
                    st.rerun()
    else:
        st.caption("Aucun historique enregistré.")
    st.markdown("---")
    st.markdown("### 🆘 Urgences")
    st.markdown("📞 **3114** — Prévention suicide")
    st.markdown("🚑 **15** — SAMU")
    st.markdown("👮 **17** — Police secours")
    st.markdown("🔥 **18** — Pompiers")

# ============================================================
# 8. INITIALISATION HISTORIQUE
# ============================================================
if "messages" not in st.session_state:
    st.session_state.messages = []

if "conversation_initiee" not in st.session_state:
    st.session_state.conversation_initiee = False

if not st.session_state.conversation_initiee:
    prenom_affiche = etudiant if etudiant else "vous"
    message_bienvenue = (
        f"Bonjour {prenom_affiche} 🌿\n\n"
        f"Je suis **MindCare**, votre coach mental. "
        f"Je suis là pour vous écouter, sans jugement et en toute confidentialité.\n\n"
        f"Comment vous sentez-vous en ce moment ?"
    )
    st.session_state.messages = [
        {"role": "assistant", "content": message_bienvenue}
    ]
    st.session_state.conversation_initiee = True

# ============================================================
# 9. AFFICHAGE DES MESSAGES (bulles WhatsApp)
# ============================================================
for message in st.session_state.messages:
    if message["role"] == "assistant":
        bulle_bot(message["content"])
    else:
        bulle_user(message["content"])

# ============================================================
# 10. SAISIE ET RÉPONSE
# ============================================================
if prompt := st.chat_input("Exprimez-vous librement..."):

    MOTS_CRISE = [
        "suicid", "mourir", "me tuer", "en finir",
        "plus envie de vivre", "automutil", "me faire du mal"
    ]
    if any(mot in prompt.lower() for mot in MOTS_CRISE):
        st.error("""
        🆘 **Si vous êtes en danger immédiat, appelez maintenant :**
        - 📞 **3114** — Numéro national prévention suicide (24h/24)
        - 🚑 **15** — SAMU · 👮 **17** — Police
        """)

    bulle_user(prompt)
    sauvegarder_message(etudiant, "user", prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    historique_groq = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.messages
    ]

    with st.spinner(""):
        reponse = obtenir_reponse(historique_groq, etudiant)

    bulle_bot(reponse)

    if activer_voix:
        audio_data = synthese_vocale(reponse, voix_id)
        if audio_data:
            st.audio(audio_data, format="audio/mpeg", autoplay=True)

    sauvegarder_message(etudiant, "assistant", reponse)
    st.session_state.messages.append({"role": "assistant", "content": reponse})

    st.markdown("---")
st.caption("⚠️ **Avertissement Important :** MindCare est un assistant de bien-être utilisant l'IA. Il ne remplace en aucun cas un suivi médical ou psychologique professionnel. En cas de crise, contactez les services d'urgence.")
