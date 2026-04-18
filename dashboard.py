import streamlit as st
import random
from datetime import datetime
from database import (
    sauvegarder_humeur, charger_humeurs,
    supprimer_compte_complet, charger_profil
)

def afficher_dashboard(user_id: str, prenom: str):

    st.markdown("### 📊 Tableau de bord")
    st.markdown(f"*Ton espace personnel, {prenom}*")
    st.markdown("---")

    # ── Profil mémorisé ──
    profil = charger_profil(user_id)
    if profil and any([profil.get("situation"), profil.get("defis"), profil.get("objectifs")]):
        st.markdown("#### 🧠 Ce qu'Aura sait sur toi")
        c1, c2 = st.columns(2)
        champs = [
            ("situation",       "📍 Situation",     "#075e54", c1),
            ("defis",           "⚡ Défis",         "#e53935", c1),
            ("objectifs",       "🎯 Objectifs",     "#1565c0", c2),
            ("humeur_generale", "💭 Humeur",        "#f57f17", c2),
        ]
        for key, label, couleur, col in champs:
            val = profil.get(key,"")
            if val:
                with col:
                    st.markdown(f"""
                    <div style="background:#fff;border-radius:8px;padding:10px 14px;
                                margin-bottom:8px;border-left:3px solid {couleur};
                                box-shadow:0 1px 3px rgba(0,0,0,0.08);">
                        <div style="font-size:11px;color:{couleur};font-weight:700;margin-bottom:3px;">{label}</div>
                        <div style="font-size:13px;color:#333;">{val}</div>
                    </div>
                    """, unsafe_allow_html=True)
        if profil.get("notes_aura"):
            st.markdown(f"""
            <div style="background:#f1f8e9;border-radius:8px;padding:12px 16px;
                        margin-bottom:14px;border-left:3px solid #558b2f;">
                <div style="font-size:11px;color:#558b2f;font-weight:700;margin-bottom:3px;">✨ Notes d'Aura</div>
                <div style="font-size:13px;color:#333;font-style:italic;">{profil['notes_aura']}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Humeur ──
    st.markdown("#### 💭 Comment tu te sens aujourd'hui ?")
    humeurs_options = {
        "😄 Très bien":(5,"😄"), "🙂 Bien":(4,"🙂"),
        "😐 Neutre":(3,"😐"), "😔 Pas top":(2,"😔"), "😢 Mal":(1,"😢"),
    }
    c1, c2 = st.columns([3,1])
    with c1:
        choix = st.select_slider("Humeur", options=list(humeurs_options.keys()),
                                 value="😐 Neutre", label_visibility="collapsed")
        note  = st.text_input("Note (optionnel) :", placeholder="Ex: Examen demain...")
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("💾 Enregistrer", use_container_width=True):
            score, emoji = humeurs_options[choix]
            sauvegarder_humeur(user_id, score, emoji, note)
            st.success("✓")
            st.rerun()

    st.markdown("---")

    # ── Graphique ──
    humeurs = charger_humeurs(user_id, jours=14)
    if humeurs:
        import pandas as pd
        st.markdown("#### 📈 Ton évolution (14 jours)")
        df = pd.DataFrame(humeurs)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        st.line_chart(df["score"], height=130, use_container_width=True)

        scores = [h["score"] for h in humeurs]
        moy    = sum(scores)/len(scores)
        tend   = ("📈 Hausse" if scores[-1]>scores[0]
                  else "📉 Baisse" if scores[-1]<scores[0] else "➡️ Stable")
        c1,c2,c3 = st.columns(3)
        with c1: st.metric("Moyenne", f"{moy:.1f}/5")
        with c2: st.metric("Sessions", len(humeurs))
        with c3: st.metric("Tendance", tend)

        notes = [h for h in humeurs if h.get("note")]
        if notes:
            st.markdown("#### 📝 Dernières notes")
            for h in notes[-3:]:
                st.markdown(f"""
                <div style="background:#fff;border-radius:8px;padding:9px 14px;
                            margin:5px 0;border-left:3px solid #075e54;">
                    <span style="font-size:16px;">{h['emoji']}</span>
                    <span style="font-size:11px;color:#999;margin-left:8px;">{h['date'][:10]}</span><br>
                    <span style="font-size:13px;color:#333;">{h['note']}</span>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("Enregistre ta première humeur pour voir ton évolution 🌱")

    st.markdown("---")

    # ── Conseil ──
    st.markdown("#### 💡 Conseil du jour")
    conseils = [
        "Commence ta journée par 5 minutes de respiration profonde. 🌬️",
        "Découpe ton travail en étapes de 25 minutes. 🎯",
        "Bois 1,5 litre d'eau aujourd'hui. 💧",
        "Fais une pause active toutes les heures. 🚶",
        "Écris 3 choses positives avant de dormir. 🙏",
        "Appelle quelqu'un qui te fait du bien. 📞",
        "Fait vaut mieux que parfait. ✨",
        "Dors 7-8 heures — ton cerveau en a besoin. 😴",
    ]
    random.seed(datetime.now().day)
    st.markdown(f"""
    <div style="background:#fff;border-radius:8px;padding:14px 18px;
                border-left:4px solid #25d366;font-size:14px;color:#333;">
        {random.choice(conseils)}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Données & suppression ──
    st.markdown("#### 🔒 Mes données")
    st.markdown(f"""
    <div style="background:#fff;border-radius:8px;padding:14px 18px;margin-bottom:12px;">
        <div style="font-size:13px;color:#333;line-height:2.2;">
            🔐 <strong>ID anonyme :</strong> <code>{user_id}</code><br>
            ✅ Messages chiffrés · Aucun partage tiers · Suppression possible
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("⚠️ Supprimer définitivement mon compte"):
        st.warning("Action irréversible — toutes tes données seront effacées.")
        confirm = st.text_input("Tape ton prénom pour confirmer :", key="del_confirm")
        if st.button("🗑️ Supprimer mon compte", type="primary"):
            if confirm.strip().lower() == prenom.strip().lower():
                supprimer_compte_complet(user_id)
                st.success("Compte supprimé. 🙏")
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()
            else:
                st.error("Prénom incorrect.")