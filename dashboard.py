import streamlit as st
from datetime import datetime
from database import (
    sauvegarder_humeur, charger_humeurs,
    supprimer_compte_complet, charger_profil
)

def afficher_dashboard(user_id: str, prenom: str):
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#1a1a2e,#0f3460);
                border-radius:16px;padding:20px 24px;margin-bottom:20px;">
        <h2 style="color:#fff;margin:0;font-size:1.3rem;">📊 Tableau de bord</h2>
        <p style="color:#c9b8f0;margin:4px 0 0;font-size:0.83rem;">
            Ton espace personnel, {prenom}
        </p>
    </div>
    """, unsafe_allow_html=True)

    # ── Profil Aura ──
    profil = charger_profil(user_id)
    if profil and any([profil.get("situation"), profil.get("defis"), profil.get("objectifs")]):
        st.markdown("### 🧠 Ce qu'Aura sait sur toi")
        col1, col2 = st.columns(2)
        with col1:
            if profil.get("situation"):
                st.markdown(f"""
                <div style="background:rgba(124,58,237,0.12);border-radius:10px;
                            padding:12px 16px;margin-bottom:10px;
                            border-left:3px solid #7c3aed;">
                    <div style="font-size:11px;color:#7c3aed;font-weight:700;
                                text-transform:uppercase;margin-bottom:4px;">Situation</div>
                    <div style="font-size:14px;color:#2d2d2d;">{profil['situation']}</div>
                </div>
                """, unsafe_allow_html=True)
            if profil.get("defis"):
                st.markdown(f"""
                <div style="background:rgba(229,75,75,0.10);border-radius:10px;
                            padding:12px 16px;margin-bottom:10px;
                            border-left:3px solid #e24b4b;">
                    <div style="font-size:11px;color:#e24b4b;font-weight:700;
                                text-transform:uppercase;margin-bottom:4px;">Défis</div>
                    <div style="font-size:14px;color:#2d2d2d;">{profil['defis']}</div>
                </div>
                """, unsafe_allow_html=True)
        with col2:
            if profil.get("objectifs"):
                st.markdown(f"""
                <div style="background:rgba(29,158,117,0.12);border-radius:10px;
                            padding:12px 16px;margin-bottom:10px;
                            border-left:3px solid #1D9E75;">
                    <div style="font-size:11px;color:#1D9E75;font-weight:700;
                                text-transform:uppercase;margin-bottom:4px;">Objectifs</div>
                    <div style="font-size:14px;color:#2d2d2d;">{profil['objectifs']}</div>
                </div>
                """, unsafe_allow_html=True)
            if profil.get("humeur_generale"):
                st.markdown(f"""
                <div style="background:rgba(245,158,11,0.12);border-radius:10px;
                            padding:12px 16px;margin-bottom:10px;
                            border-left:3px solid #f59e0b;">
                    <div style="font-size:11px;color:#f59e0b;font-weight:700;
                                text-transform:uppercase;margin-bottom:4px;">Humeur générale</div>
                    <div style="font-size:14px;color:#2d2d2d;">{profil['humeur_generale']}</div>
                </div>
                """, unsafe_allow_html=True)
        if profil.get("notes_aura"):
            st.markdown(f"""
            <div style="background:#f8f7ff;border-radius:10px;padding:12px 16px;
                        margin-bottom:16px;border:1px solid rgba(124,58,237,0.2);">
                <div style="font-size:11px;color:#7c3aed;font-weight:700;margin-bottom:4px;">
                    ✨ Notes d'Aura
                </div>
                <div style="font-size:13px;color:#4b5563;font-style:italic;">
                    {profil['notes_aura']}
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Humeur du jour ──
    st.markdown("### 💭 Comment tu te sens aujourd'hui ?")
    humeurs_options = {
        "😄 Très bien": (5, "😄"),
        "🙂 Bien":      (4, "🙂"),
        "😐 Neutre":    (3, "😐"),
        "😔 Pas top":   (2, "😔"),
        "😢 Mal":       (1, "😢"),
    }
    col1, col2 = st.columns([3, 1])
    with col1:
        choix = st.select_slider(
            "Humeur",
            options=list(humeurs_options.keys()),
            value="😐 Neutre",
            label_visibility="collapsed"
        )
        note = st.text_input(
            "Une note (optionnel) :",
            placeholder="Ex: Examen demain, un peu stressé..."
        )
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if st.button("💾 Enregistrer", use_container_width=True):
            score, emoji = humeurs_options[choix]
            sauvegarder_humeur(user_id, score, emoji, note)
            st.success("✓ Enregistré !")
            st.rerun()

    st.markdown("---")

    # ── Graphique humeur ──
    humeurs = charger_humeurs(user_id, jours=14)
    if humeurs:
        import pandas as pd
        st.markdown("### 📈 Ton évolution (14 jours)")
        df = pd.DataFrame(humeurs)
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date")
        st.line_chart(df["score"], height=140, use_container_width=True)

        scores = [h["score"] for h in humeurs]
        moy    = sum(scores) / len(scores)
        tend   = "📈 En hausse" if scores[-1] > scores[0] else ("📉 En baisse" if scores[-1] < scores[0] else "➡️ Stable")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Moyenne", f"{moy:.1f} / 5")
        with col2:
            st.metric("Sessions", len(humeurs))
        with col3:
            st.metric("Tendance", tend)

        notes = [h for h in humeurs if h.get("note")]
        if notes:
            st.markdown("### 📝 Dernières notes")
            for h in notes[-3:]:
                st.markdown(f"""
                <div style="background:#f8f7ff;border-radius:10px;
                            padding:10px 14px;margin:6px 0;
                            border-left:3px solid #7c3aed;">
                    <span style="font-size:16px;">{h['emoji']}</span>
                    <span style="font-size:11px;color:#9ca3af;margin-left:8px;">{h['date'][:10]}</span><br>
                    <span style="font-size:13px;color:#374151;">{h['note']}</span>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("Enregistre ta première humeur pour voir ton évolution 🌱")

    st.markdown("---")

    # ── Conseil du jour ──
    import random
    st.markdown("### 💡 Conseil du jour")
    conseils = [
        "Commence ta journée par 5 minutes de respiration profonde. 🌬️",
        "Découpe ton travail en petites étapes de 25 minutes. 🎯",
        "Bois au moins 1,5 litre d'eau aujourd'hui. 💧",
        "Fais une pause active toutes les heures. 🚶",
        "Écris 3 choses positives avant de dormir. 🙏",
        "Appelle quelqu'un qui te fait du bien. 📞",
        "Tu n'as pas à être parfait(e). Fait vaut mieux que parfait. ✨",
        "Dors 7 à 8 heures — ton cerveau en a besoin. 😴",
        "Une chose à la fois. La multitâche épuise. 🎯",
    ]
    random.seed(datetime.now().day)
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,rgba(124,58,237,0.08),rgba(168,85,247,0.08));
                border-radius:14px;padding:16px 20px;border-left:4px solid #7c3aed;font-size:15px;color:#374151;">
        {random.choice(conseils)}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # ── Confidentialité ──
    st.markdown("### 🔒 Mes données & confidentialité")
    st.markdown(f"""
    <div style="background:#f0fdf4;border-radius:12px;padding:16px 20px;
                border:1px solid rgba(29,158,117,0.2);margin-bottom:16px;">
        <div style="font-size:13px;color:#374151;line-height:2;">
            🔐 <strong>ID anonyme :</strong> <code>{user_id}</code><br>
            ✅ Tes messages sont <strong>chiffrés</strong> en base de données<br>
            ✅ Ton prénom n'est <strong>jamais</strong> partagé avec des tiers<br>
            ✅ Aucune publicité ciblée<br>
            ✅ Tu peux supprimer ton compte à tout moment
        </div>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("⚠️ Supprimer mon compte définitivement"):
        st.warning("Cette action supprime **toutes** tes données de façon irréversible.")
        confirmation = st.text_input("Tape ton prénom pour confirmer :", key="confirm_delete")
        if st.button("🗑️ Supprimer définitivement", type="primary"):
            if confirmation.strip().lower() == prenom.strip().lower():
                supprimer_compte_complet(user_id)
                st.success("Compte supprimé. Prends soin de toi. 🙏")
                for k in list(st.session_state.keys()):
                    del st.session_state[k]
                st.rerun()
            else:
                st.error("Prénom incorrect. Suppression annulée.")