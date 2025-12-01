# app.py - Version avec intégration Strava
import streamlit as st
import os
import time
import sys
import tempfile
from io import StringIO
from datetime import datetime, timedelta
from genrunzS1 import main_pipeline
from strava_connector import StravaConnector, get_strava_auth_url, exchange_code_for_token

# Configuration de la page
st.set_page_config(
    page_title="Générateur Vidéo Parcours",
    layout="wide",
    page_icon="🏃"
)

# Style CSS
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #FF6B35;
        margin-bottom: 1rem;
    }
    .stProgress > div > div > div > div {
        background-color: #FF6B35;
    }
    .success-box {
        padding: 1.5rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 2px solid #c3e6cb;
        color: #155724;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1.5rem;
        border-radius: 0.5rem;
        background-color: #d1ecf1;
        border: 2px solid #bee5eb;
        color: #0c5460;
        margin: 1rem 0;
    }
    .strava-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fc4c02;
        color: white;
        text-align: center;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Logger pour les prints
class StreamlitLogger:
    def __init__(self, text_area):
        self.text_area = text_area
        self.logs = []
        
    def write(self, text):
        if text.strip():
            self.logs.append(text)
            display_logs = self.logs[-50:]
            self.text_area.code('\n'.join(display_logs), language='bash')
    
    def flush(self):
        pass

# En-tête
st.markdown('<p class="main-header">🎬 Générateur de Vidéo de Parcours GPS</p>', unsafe_allow_html=True)

# --------------------------
# Sidebar - Configuration Strava
# --------------------------
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Source des données
    st.subheader("📂 Source des données")
    data_source = st.radio(
        "Choisir la source",
        ["🗂️ Dossier local", "🏃 Strava API"],
        help="Choisissez d'où récupérer vos fichiers GPS"
    )
    
    st.divider()
    
    # Configuration selon la source
    if data_source == "🏃 Strava API":
        st.subheader("🔐 Authentification Strava")
        
        # Instructions pour obtenir les credentials
        with st.expander("ℹ️ Comment obtenir vos credentials Strava"):
            st.markdown("""
            **Étapes:**
            1. Allez sur [strava.com/settings/api](https://www.strava.com/settings/api)
            2. Créez une application
            3. Notez votre **Client ID** et **Client Secret**
            4. Utilisez l'URL d'autorisation ci-dessous pour obtenir un code
            5. Échangez le code contre un refresh token
            
            **Authorization Callback Domain:** `localhost`
            """)
        
        # Credentials Strava
        client_id = st.text_input(
            "Client ID",
            value=st.session_state.get('strava_client_id', ''),
            type="password"
        )
        client_secret = st.text_input(
            "Client Secret",
            value=st.session_state.get('strava_client_secret', ''),
            type="password"
        )
        
        # Sauvegarder dans session_state
        if client_id:
            st.session_state['strava_client_id'] = client_id
        if client_secret:
            st.session_state['strava_client_secret'] = client_secret
        
        # Étape 1: Obtenir le code d'autorisation
        if client_id and not st.session_state.get('strava_refresh_token'):
            st.markdown("**Étape 1: Autorisation**")
            auth_url = get_strava_auth_url(client_id)
            st.markdown(f'[🔗 Cliquez ici pour autoriser l\'application]({auth_url})')
            
            st.markdown("**Étape 2: Entrez le code**")
            st.caption("Après autorisation, vous serez redirigé vers une URL contenant un code")
            auth_code = st.text_input("Code d'autorisation", key="auth_code")
            
            if st.button("Échanger le code contre un token") and auth_code:
                try:
                    with st.spinner("Échange du code..."):
                        tokens = exchange_code_for_token(client_id, client_secret, auth_code)
                        st.session_state['strava_refresh_token'] = tokens['refresh_token']
                        st.session_state['strava_access_token'] = tokens['access_token']
                        st.success("✅ Token obtenu avec succès!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erreur: {e}")
        
        # Si on a un refresh token
        if st.session_state.get('strava_refresh_token'):
            st.success("✅ Connecté à Strava")
            
            refresh_token = st.text_input(
                "Refresh Token",
                value=st.session_state['strava_refresh_token'],
                type="password",
                help="Token sauvegardé"
            )
            
            if st.button("🔄 Déconnecter"):
                st.session_state.pop('strava_refresh_token', None)
                st.session_state.pop('strava_access_token', None)
                st.rerun()
            
            st.divider()
            
            # Filtres Strava
            st.subheader("🔍 Filtres")
            
            date_range = st.date_input(
                "Période",
                value=(datetime.now() - timedelta(days=30), datetime.now()),
                help="Sélectionnez la période des activités"
            )
            
            activity_types = st.multiselect(
                "Types d'activités",
                ["Run", "Ride", "Walk", "Hike", "VirtualRide", "VirtualRun"],
                default=["Run", "Ride"],
                help="Sélectionnez les types d'activités à inclure"
            )
            
            max_activities = st.number_input(
                "Nombre max d'activités",
                min_value=1,
                max_value=500,
                value=50,
                help="Limite le nombre d'activités téléchargées"
            )
            
            folder = None  # Sera créé temporairement
    
    else:  # Dossier local
        st.subheader("📁 Fichiers locaux")
        folder = st.text_input(
            "Chemin du dossier",
            "/Users/Tibo/Documents/strava/export_prod/activities_test"
        )
        
        if folder and not os.path.exists(folder):
            st.warning("⚠️ Ce dossier n'existe pas")
    
    st.divider()
    
    # Paramètres communs
    st.subheader("🎨 Rendu")
    frame_folder = st.text_input("Dossier des frames", "Frame_mercator1")
    max_frames_per_course = st.number_input("Segments par course", value=10, step=10)
    speed_factor = st.slider("⚡ Vitesse", 1.0, 15.0, 7.0, 0.5)
    
    st.divider()
    
    st.subheader("🎵 Audio")
    music_path = st.text_input("Fichier musique", "/Users/Tibo/audiomachine.mp3")
    
    st.divider()
    
    st.subheader("💾 Sortie")
    output_file = st.text_input("Nom du fichier", "video_final.mp4")
    
    st.divider()
    
    st.subheader("🔧 Options")
    errase_frame_folder = st.checkbox("🗑️ Supprimer frames existantes", value=True)
    skip_loading = st.checkbox("⏭️ Skip chargement", value=False)
    skip_frames = st.checkbox("⏭️ Skip génération frames", value=False)

# --------------------------
# Zone principale
# --------------------------
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    # Vérifier que la configuration est complète
    can_generate = False
    
    if data_source == "🏃 Strava API":
        if st.session_state.get('strava_refresh_token'):
            can_generate = True
        else:
            st.warning("⚠️ Veuillez d'abord vous connecter à Strava")
    else:
        if folder and os.path.exists(folder):
            can_generate = True
        else:
            st.warning("⚠️ Veuillez indiquer un dossier valide")
    
    generate_button = st.button(
        "🚀 Générer la vidéo",
        type="primary",
        use_container_width=True,
        disabled=not can_generate
    )

if generate_button:
    # Créer dossier temporaire
    with tempfile.TemporaryDirectory() as temp_dir:
        
        # Si source = Strava, télécharger les activités
        if data_source == "🏃 Strava API":
            st.info("📥 Téléchargement des activités depuis Strava...")
            
            try:
                connector = StravaConnector(
                    client_id=st.session_state['strava_client_id'],
                    client_secret=st.session_state['strava_client_secret'],
                    refresh_token=st.session_state['strava_refresh_token']
                )
                
                # Récupérer infos athlète
                athlete = connector.get_athlete_info()
                st.success(f"✅ Connecté: {athlete['firstname']} {athlete['lastname']}")
                
                # Télécharger activités
                strava_folder = os.path.join(temp_dir, "strava_activities")
                
                after_date = datetime.combine(date_range[0], datetime.min.time()) if len(date_range) > 0 else None
                before_date = datetime.combine(date_range[1], datetime.max.time()) if len(date_range) > 1 else None
                
                downloaded_files = connector.download_activities(
                    output_folder=strava_folder,
                    after=after_date,
                    before=before_date,
                    activity_types=activity_types,
                    max_activities=max_activities
                )
                
                if not downloaded_files:
                    st.error("❌ Aucune activité téléchargée")
                    st.stop()
                
                st.success(f"✅ {len(downloaded_files)} activités téléchargées")
                folder = strava_folder
                
            except Exception as e:
                st.error(f"❌ Erreur Strava: {e}")
                st.stop()
        
        # Conteneur de progression
        progress_container = st.container()
        
        with progress_container:
            st.markdown(
                '<div class="info-box">🔄 <strong>Traitement en cours...</strong><br>'
                'Génération de la vidéo en cours...</div>',
                unsafe_allow_html=True
            )
            
            progress_bar = st.progress(0, text="🚀 Initialisation...")
            
            # Métriques
            st.markdown("### 📊 Progression")
            metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
            
            with metrics_col1:
                status_metric = st.empty()
            with metrics_col2:
                phase_metric = st.empty()
            with metrics_col3:
                time_metric = st.empty()
            
            # Logs
            log_expander = st.expander("📋 Logs techniques", expanded=True)
            with log_expander:
                log_area = st.empty()
            
            try:
                start_time = time.time()
                
                # Logger
                logger = StreamlitLogger(log_area)
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = logger
                sys.stderr = logger
                
                progress_bar.progress(10, text="📂 Chargement...")
                status_metric.metric("📁 Statut", "Chargement")
                phase_metric.metric("🔄 Phase", "1/5")
                
                print("=" * 50)
                print("🚀 DÉMARRAGE DU PIPELINE")
                print(f"📂 Source: {data_source}")
                print(f"📁 Dossier: {folder}")
                print("=" * 50)
                
                # Générer la vidéo
                progress_bar.progress(50, text="⚙️ Traitement...")
                
                video_path = main_pipeline(
                    folder=folder,
                    skip_frames=skip_frames,
                    skip_loading=skip_loading,
                    frames_folder=os.path.join(temp_dir, frame_folder),
                    speed_factor=speed_factor,
                    music_path=music_path if os.path.exists(music_path) else None,
                    output_file=os.path.join(temp_dir, output_file),
                    errase_frame_folder=errase_frame_folder,
                    max_frames_per_course=max_frames_per_course
                )
                
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                
                progress_bar.progress(100, text="✅ Terminé!")
                
                # Temps écoulé
                elapsed_time = time.time() - start_time
                minutes = int(elapsed_time // 60)
                seconds = int(elapsed_time % 60)
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                
                status_metric.metric("✅ Statut", "Terminé", delta="100%")
                phase_metric.metric("🎉 Phase", "5/5", delta="Complet")
                time_metric.metric("⏱️ Temps", time_str)
                
                st.balloons()
                
                # Message de succès
                st.markdown(
                    f'<div class="success-box">'
                    f'<h3 style="margin:0;">✅ Vidéo générée avec succès!</h3><br>'
                    f'📂 <strong>Source:</strong> {data_source}<br>'
                    f'⏱️ <strong>Temps:</strong> {time_str}<br>'
                    f'🎬 <strong>Vitesse:</strong> x{speed_factor}'
                    f'</div>',
                    unsafe_allow_html=True
                )
                
                # Affichage vidéo
                if os.path.exists(video_path):
                    st.markdown("### 🎥 Aperçu")
                    st.video(video_path)
                    
                    # Téléchargement
                    st.markdown("### 📥 Téléchargement")
                    col_dl1, col_dl2, col_dl3 = st.columns([1, 2, 1])
                    with col_dl2:
                        with open(video_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Télécharger la vidéo",
                                data=f,
                                file_name=output_file,
                                mime="video/mp4",
                                use_container_width=True
                            )
            
            except Exception as e:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                
                progress_bar.progress(0, text="❌ Erreur")
                status_metric.metric("❌ Statut", "Erreur")
                
                st.error(f"❌ Erreur: {str(e)}")
                
                with st.expander("🔍 Détails"):
                    st.code(str(e))

# Footer
st.divider()

help_col1, help_col2 = st.columns(2)

with help_col1:
    with st.expander("📖 Guide Strava"):
        st.markdown("""
        **Configuration Strava:**
        1. Créez une app sur [strava.com/settings/api](https://www.strava.com/settings/api)
        2. Copiez Client ID et Client Secret
        3. Autorisez l'application
        4. Sélectionnez vos activités
        5. Générez votre vidéo!
        """)

with help_col2:
    with st.expander("🎯 Formats supportés"):
        st.markdown("""
        **Dossier local:**
        - GPX, FIT, FIT.GZ
        
        **Strava:**
        - Toutes activités avec GPS
        - Run, Ride, Walk, Hike, etc.
        """)

st.divider()
st.caption("Made with ❤️ using Streamlit | 🏃 GPS Video Generator v3.0 - Powered by Strava")