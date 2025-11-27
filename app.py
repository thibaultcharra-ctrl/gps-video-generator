# app.py - Version avec logs en temps réel
import streamlit as st
import os
import time
import sys
import threading
from io import StringIO
from genrunzS1 import main_pipeline

# Configuration de la page
st.set_page_config(
    page_title="Générateur Vidéo Parcours",
    layout="wide",
    page_icon="🏃"
)

# Style CSS personnalisé
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
    .log-container {
        background-color: #1e1e1e;
        color: #00ff00;
        padding: 1rem;
        border-radius: 0.5rem;
        font-family: 'Courier New', monospace;
        font-size: 0.85rem;
        max-height: 400px;
        overflow-y: auto;
    }
    </style>
""", unsafe_allow_html=True)

# Classe pour capturer les prints en temps réel
class StreamlitLogger:
    def __init__(self, text_area):
        self.text_area = text_area
        self.logs = []
        
    def write(self, text):
        if text.strip():  # Ignorer les lignes vides
            self.logs.append(text)
            # Afficher les 50 dernières lignes
            display_logs = self.logs[-50:]
            self.text_area.code('\n'.join(display_logs), language='bash')
    
    def flush(self):
        pass

# En-tête
st.markdown('<p class="main-header">🎬 Générateur de Vidéo de Parcours GPS/FIT/GPX</p>', unsafe_allow_html=True)

# --------------------------
# Sidebar - Paramètres
# --------------------------
with st.sidebar:
    st.header("⚙️ Configuration")
    
    st.subheader("📁 Fichiers")
    folder = st.text_input(
        "Archive Strava (GPX/FIT/FIT.GZ)",
        "/Users/Tibo/Documents/strava/export_prod/activities_test"
    )
    frame_folder = st.text_input("Dossier des frames", "Frame_mercator1")
    
    st.divider()
    
    st.subheader("🎨 Options de rendu")
    max_frames_per_course = st.number_input(
        "Segments par course",
        value=10,
        step=10,
        help="Nombre de points par tracé GPS"
    )
    speed_factor = st.slider(
        "⚡ Vitesse de la vidéo",
        1.0, 15.0, 7.0, 0.5,
        help="Multiplicateur de vitesse (x1, x2, x3...)"
    )
    
    st.divider()
    
    st.subheader("🎵 Audio")
    music_path = st.text_input(
        "Fichier musique (MP3)",
        "/Users/Tibo/audiomachine.mp3"
    )
    
    st.divider()
    
    st.subheader("💾 Sortie")
    output_file = st.text_input(
        "Nom du fichier final",
        "video_final.mp4"
    )
    
    st.divider()
    
    st.subheader("🔧 Options avancées")
    errase_frame_folder = st.checkbox(
        "🗑️ Supprimer les frames existantes",
        value=False,
        help="Efface le dossier de frames avant génération"
    )
    skip_loading = st.checkbox(
        "⏭️ Skip chargement des fichiers",
        value=False
    )
    skip_frames = st.checkbox(
        "⏭️ Skip génération des frames",
        value=False,
        help="Utilise les frames déjà générées"
    )
    
    st.divider()
    st.caption("📍 Centre: Paris (48.8504, 2.2181)")
    st.caption("📏 Rayon: 100 km")

# --------------------------
# Zone principale
# --------------------------
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    generate_button = st.button(
        "🚀 Générer la vidéo",
        type="primary",
        use_container_width=True
    )

if generate_button:
    if not folder or not os.path.exists(folder):
        st.error("❌ Le dossier n'existe pas ou n'a pas été indiqué")
    else:
        # Conteneur principal de progression
        progress_container = st.container()
        
        with progress_container:
            # Message d'information initial
            st.markdown(
                '<div class="info-box">🔄 <strong>Traitement en cours...</strong><br>'
                'Cela peut prendre quelques minutes selon le nombre de fichiers.</div>',
                unsafe_allow_html=True
            )
            
            # Barre de progression principale avec texte dynamique
            progress_bar = st.progress(0, text="🚀 Initialisation...")
            
            # Métriques en temps réel
            st.markdown("### 📊 Progression")
            metrics_col1, metrics_col2, metrics_col3 = st.columns(3)
            
            with metrics_col1:
                status_metric = st.empty()
            with metrics_col2:
                phase_metric = st.empty()
            with metrics_col3:
                time_metric = st.empty()
            
            # Zone d'informations détaillées
            info_expander = st.expander("ℹ️ Informations détaillées", expanded=False)
            with info_expander:
                detail_text = st.empty()
            
            # Zone de logs EN TEMPS RÉEL
            log_expander = st.expander("📋 Logs techniques (en temps réel)", expanded=True)
            with log_expander:
                log_area = st.empty()
            
            try:
                start_time = time.time()
                
                # Créer le logger personnalisé
                logger = StreamlitLogger(log_area)
                
                # Rediriger stdout et stderr
                old_stdout = sys.stdout
                old_stderr = sys.stderr
                sys.stdout = logger
                sys.stderr = logger
                
                # Phase 1: Chargement (0-20%)
                if not skip_loading:
                    progress_bar.progress(10, text="📂 Chargement des fichiers GPS...")
                    status_metric.metric("📁 Statut", "Chargement")
                    phase_metric.metric("🔄 Phase", "1/5")
                    detail_text.info("🔍 Recherche et analyse des fichiers GPS dans le dossier...")
                    print("=" * 50)
                    print("🚀 DÉMARRAGE DU PIPELINE")
                    print("=" * 50)
                
                # Phase 2: Nettoyage frames (20-30%)
                if errase_frame_folder:
                    progress_bar.progress(20, text="🗑️ Nettoyage des frames...")
                    detail_text.info("🧹 Suppression des anciennes frames...")
                    print("\n🗑️  Nettoyage du dossier de frames...")
                
                # Phase 3: Génération frames (30-60%)
                if not skip_frames:
                    progress_bar.progress(35, text="🎨 Génération des frames...")
                    status_metric.metric("🎨 Statut", "Frames")
                    phase_metric.metric("🔄 Phase", "2/5")
                    detail_text.info("🖼️ Création des images pour chaque segment de parcours...")
                    print("\n🎨 Génération des frames en cours...")
                
                # Appel de la fonction principale
                progress_bar.progress(50, text="⚙️ Traitement en cours...")
                print("\n⚙️  Traitement principal...")
                
                video_path = main_pipeline(
                    folder=folder,
                    skip_frames=skip_frames,
                    skip_loading=skip_loading,
                    frames_folder=frame_folder,
                    speed_factor=speed_factor,
                    music_path=music_path,
                    output_file=output_file,
                    errase_frame_folder=errase_frame_folder,
                    max_frames_per_course=max_frames_per_course
                )
                
                # Restaurer stdout/stderr
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                
                # Phase 4: Compilation vidéo (60-80%)
                progress_bar.progress(70, text="🎬 Compilation de la vidéo...")
                status_metric.metric("🎬 Statut", "Compilation")
                phase_metric.metric("🔄 Phase", "3/5")
                detail_text.info("🎥 Assemblage des frames en vidéo...")
                
                # Phase 5: Ajout audio (80-95%)
                if os.path.exists(music_path):
                    progress_bar.progress(85, text="🎵 Ajout de l'audio...")
                    status_metric.metric("🎵 Statut", "Audio")
                    phase_metric.metric("🔄 Phase", "4/5")
                    detail_text.info("🎶 Intégration de la musique de fond...")
                
                # Phase 6: Finalisation (95-100%)
                progress_bar.progress(95, text="✨ Finalisation...")
                status_metric.metric("✨ Statut", "Finalisation")
                phase_metric.metric("🔄 Phase", "5/5")
                detail_text.info("🎁 Derniers ajustements...")
                
                # Terminé!
                progress_bar.progress(100, text="✅ Terminé!")
                
                # Calcul du temps écoulé
                elapsed_time = time.time() - start_time
                minutes = int(elapsed_time // 60)
                seconds = int(elapsed_time % 60)
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                
                # Mise à jour des métriques finales
                status_metric.metric("✅ Statut", "Terminé", delta="100%")
                phase_metric.metric("🎉 Phase", "5/5", delta="Complet")
                time_metric.metric("⏱️ Temps", time_str)
                
                # Animation de succès
                st.balloons()
                
                # Message de succès stylisé
                st.markdown(
                    f'<div class="success-box">'
                    f'<h3 style="margin:0;">✅ Vidéo générée avec succès!</h3><br>'
                    f'📁 <strong>Fichier:</strong> <code>{video_path}</code><br>'
                    f'⏱️ <strong>Temps de traitement:</strong> {time_str}<br>'
                    f'🎬 <strong>Vitesse:</strong> x{speed_factor}<br>'
                    f'📊 <strong>Segments par course:</strong> {max_frames_per_course}'
                    f'</div>',
                    unsafe_allow_html=True
                )
                
                # Affichage de la vidéo
                if os.path.exists(video_path):
                    st.markdown("### 🎥 Aperçu de la vidéo")
                    st.video(video_path)
                    
                    # Bouton de téléchargement stylisé
                    st.markdown("### 📥 Téléchargement")
                    col_dl1, col_dl2, col_dl3 = st.columns([1, 2, 1])
                    with col_dl2:
                        with open(video_path, "rb") as f:
                            st.download_button(
                                label="⬇️ Télécharger la vidéo",
                                data=f,
                                file_name=os.path.basename(video_path),
                                mime="video/mp4",
                                use_container_width=True
                            )
                
            except Exception as e:
                # Restaurer stdout/stderr en cas d'erreur
                sys.stdout = old_stdout
                sys.stderr = old_stderr
                
                # Gestion des erreurs
                progress_bar.progress(0, text="❌ Erreur détectée")
                status_metric.metric("❌ Statut", "Erreur")
                
                st.markdown(
                    f'<div style="padding:1.5rem;border-radius:0.5rem;background-color:#f8d7da;'
                    f'border:2px solid #f5c6cb;color:#721c24;margin:1rem 0;">'
                    f'<h3 style="margin:0;">❌ Une erreur est survenue</h3><br>'
                    f'<code>{str(e)}</code>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                
                # Afficher les détails de l'erreur
                with st.expander("🔍 Détails techniques de l'erreur"):
                    st.code(str(e))
                    st.error("Vérifiez que tous les chemins sont corrects et que les fichiers existent.")

# --------------------------
# Section d'aide
# --------------------------
st.divider()

help_col1, help_col2, help_col3 = st.columns(3)

with help_col1:
    with st.expander("📖 Guide d'utilisation"):
        st.markdown("""
        **Étapes:**
        1. 📁 Indiquez le dossier contenant vos fichiers GPS
        2. ⚙️ Ajustez les paramètres (vitesse, segments...)
        3. 🚀 Cliquez sur "Générer la vidéo"
        4. ⏳ Patientez pendant le traitement
        5. 📥 Téléchargez votre vidéo!
        """)

with help_col2:
    with st.expander("🎯 Formats supportés"):
        st.markdown("""
        - **GPX** 📍 Fichiers GPS standard
        - **FIT** ⌚ Fichiers Garmin/Strava
        - **FIT.GZ** 📦 Fichiers FIT compressés
        
        *Tous les fichiers doivent être dans le même dossier.*
        """)

with help_col3:
    with st.expander("⚙️ Paramètres avancés"):
        st.markdown("""
        - **Segments par course**: Plus = vidéo plus détaillée
        - **Vitesse**: Multiplie la vitesse de lecture
        - **Skip frames**: Réutilise les frames existantes
        - **Effacer frames**: Repart de zéro
        """)

# Footer
st.divider()
st.caption("Made with ❤️ using Streamlit | 🏃 GPS Video Generator v2.0")