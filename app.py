# app.py - Version Cloud avec stockage S3/GCS
import streamlit as st
import os
import time
import sys
import tempfile
import shutil
from io import StringIO
from genrunzS1 import main_pipeline

# Pour AWS S3 (installer: pip install boto3)
try:
    import boto3
    HAS_S3 = True
except ImportError:
    HAS_S3 = False

# Pour Google Cloud Storage (installer: pip install google-cloud-storage)
try:
    from google.cloud import storage as gcs
    HAS_GCS = True
except ImportError:
    HAS_GCS = False

# Configuration de la page
st.set_page_config(
    page_title="Générateur Vidéo Parcours",
    layout="wide",
    page_icon="🏃"
)

# Style CSS personnalisé (identique à avant)
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
    </style>
""", unsafe_allow_html=True)

# Classe pour capturer les prints en temps réel
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

# Fonctions de stockage cloud
def upload_to_s3(file_path, bucket_name, object_name=None):
    """Upload fichier vers S3"""
    if not HAS_S3:
        return None
    
    if object_name is None:
        object_name = os.path.basename(file_path)
    
    try:
        s3_client = boto3.client('s3')
        s3_client.upload_file(file_path, bucket_name, object_name)
        
        # Générer URL de téléchargement (valide 1 heure)
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': object_name},
            ExpiresIn=3600
        )
        return url
    except Exception as e:
        st.error(f"Erreur S3: {e}")
        return None

def upload_to_gcs(file_path, bucket_name, object_name=None):
    """Upload fichier vers Google Cloud Storage"""
    if not HAS_GCS:
        return None
    
    if object_name is None:
        object_name = os.path.basename(file_path)
    
    try:
        client = gcs.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(object_name)
        
        blob.upload_from_filename(file_path)
        
        # Rendre le fichier public temporairement
        blob.make_public()
        return blob.public_url
    except Exception as e:
        st.error(f"Erreur GCS: {e}")
        return None

# En-tête
st.markdown('<p class="main-header">🎬 Générateur de Vidéo de Parcours GPS/FIT/GPX</p>', unsafe_allow_html=True)

# --------------------------
# Sidebar - Paramètres
# --------------------------
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Mode de stockage
    st.subheader("☁️ Stockage")
    storage_mode = st.selectbox(
        "Mode de stockage",
        ["Local (développement)", "AWS S3", "Google Cloud Storage"],
        help="Choisissez où sauvegarder la vidéo"
    )
    
    if storage_mode == "AWS S3" and HAS_S3:
        bucket_name = st.text_input("Nom du bucket S3", "my-videos-bucket")
    elif storage_mode == "Google Cloud Storage" and HAS_GCS:
        bucket_name = st.text_input("Nom du bucket GCS", "my-videos-bucket")
    else:
        bucket_name = None
    
    st.divider()
    
    st.subheader("📁 Fichiers")
    
    # Upload de fichiers GPS
    uploaded_files = st.file_uploader(
        "📤 Uploader vos fichiers GPS",
        type=["gpx", "fit", "gz"],
        accept_multiple_files=True,
        help="Sélectionnez un ou plusieurs fichiers GPX/FIT"
    )
    
    # OU utiliser un dossier local (pour dev)
    use_local_folder = st.checkbox("Utiliser un dossier local", value=False)
    if use_local_folder:
        folder = st.text_input(
            "Dossier local",
            "/Users/Tibo/Documents/strava/export_prod/activities_test"
        )
    else:
        folder = None
    
    frame_folder = st.text_input("Dossier des frames", "Frame_mercator1")
    
    st.divider()
    
    st.subheader("🎨 Options de rendu")
    max_frames_per_course = st.number_input(
        "Segments par course",
        value=10,
        step=10
    )
    speed_factor = st.slider(
        "⚡ Vitesse de la vidéo",
        1.0, 15.0, 7.0, 0.5
    )
    
    st.divider()
    
    st.subheader("🎵 Audio")
    audio_file = st.file_uploader(
        "📤 Uploader musique (MP3)",
        type=["mp3"]
    )
    
    # OU utiliser fichier local
    use_local_audio = st.checkbox("Utiliser audio local", value=False)
    if use_local_audio:
        music_path = st.text_input(
            "Fichier musique local",
            "/Users/Tibo/audiomachine.mp3"
        )
    else:
        music_path = None
    
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
        value=True
    )
    skip_loading = st.checkbox("⏭️ Skip chargement", value=False)
    skip_frames = st.checkbox("⏭️ Skip génération frames", value=False)

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
    # Vérifier qu'on a des fichiers
    has_files = (uploaded_files and len(uploaded_files) > 0) or (use_local_folder and folder and os.path.exists(folder))
    
    if not has_files:
        st.error("❌ Veuillez uploader des fichiers GPS ou indiquer un dossier local")
    else:
        # Créer dossier temporaire pour le traitement
        with tempfile.TemporaryDirectory() as temp_dir:
            
            # Si fichiers uploadés, les sauver temporairement
            if uploaded_files:
                gps_folder = os.path.join(temp_dir, "gps_data")
                os.makedirs(gps_folder, exist_ok=True)
                
                st.info(f"📥 Sauvegarde de {len(uploaded_files)} fichiers...")
                for uploaded_file in uploaded_files:
                    file_path = os.path.join(gps_folder, uploaded_file.name)
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                
                folder = gps_folder
            
            # Si audio uploadé, le sauver temporairement
            if audio_file:
                music_path = os.path.join(temp_dir, audio_file.name)
                with open(music_path, "wb") as f:
                    f.write(audio_file.getbuffer())
            elif not use_local_audio:
                music_path = None
            
            # Conteneur de progression
            progress_container = st.container()
            
            with progress_container:
                st.markdown(
                    '<div class="info-box">🔄 <strong>Traitement en cours...</strong><br>'
                    'Cela peut prendre quelques minutes.</div>',
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
                    print(f"📁 Mode: {storage_mode}")
                    print("=" * 50)
                    
                    # Générer la vidéo
                    progress_bar.progress(50, text="⚙️ Traitement...")
                    
                    video_path = main_pipeline(
                        folder=folder,
                        skip_frames=skip_frames,
                        skip_loading=skip_loading,
                        frames_folder=os.path.join(temp_dir, frame_folder),
                        speed_factor=speed_factor,
                        music_path=music_path if music_path and os.path.exists(music_path) else None,
                        output_file=os.path.join(temp_dir, output_file),
                        errase_frame_folder=errase_frame_folder,
                        max_frames_per_course=max_frames_per_course
                    )
                    
                    sys.stdout = old_stdout
                    sys.stderr = old_stderr
                    
                    progress_bar.progress(90, text="☁️ Upload vers le cloud...")
                    
                    # Upload vers le cloud si nécessaire
                    cloud_url = None
                    if storage_mode == "AWS S3" and bucket_name:
                        print(f"☁️  Upload vers S3: {bucket_name}")
                        cloud_url = upload_to_s3(video_path, bucket_name)
                    elif storage_mode == "Google Cloud Storage" and bucket_name:
                        print(f"☁️  Upload vers GCS: {bucket_name}")
                        cloud_url = upload_to_gcs(video_path, bucket_name)
                    
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
                    success_msg = f'<div class="success-box">' \
                                 f'<h3 style="margin:0;">✅ Vidéo générée avec succès!</h3><br>' \
                                 f'⏱️ <strong>Temps:</strong> {time_str}<br>' \
                                 f'🎬 <strong>Vitesse:</strong> x{speed_factor}<br>'
                    
                    if cloud_url:
                        success_msg += f'☁️ <strong>Cloud URL:</strong> <a href="{cloud_url}" target="_blank">Télécharger</a><br>'
                    
                    success_msg += f'</div>'
                    st.markdown(success_msg, unsafe_allow_html=True)
                    
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
                            
                            if cloud_url:
                                st.info(f"☁️ Vidéo également disponible sur le cloud (lien valide 1h)")
                
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
st.caption("Made with ❤️ using Streamlit | 🏃 GPS Video Generator Cloud Edition")