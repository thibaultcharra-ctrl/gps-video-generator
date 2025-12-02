# -*- coding: utf-8 -*-

import os, glob, gzip, shutil, math, datetime, argparse
import pandas as pd, numpy as np, pytz, gpxpy, fitdecode
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageSequenceClip, AudioFileClip, VideoFileClip, concatenate_videoclips, vfx, afx
from moviepy.video.VideoClip import ImageClip
import subprocess
import streamlit as st

 

# ===============================
# Setup Command-line Arguments
# ===============================
parser = argparse.ArgumentParser(description="Control the video creation process.")
parser.add_argument('--skip_frames', action='store_true', help="Skip frame generation")
parser.add_argument('--skip_effects', action='store_true', help="Skip applying effects (like speed)")
parser.add_argument('--skip_audio', action='store_true', help="Skip adding audio")
parser.add_argument('--skip_write', action='store_true', help="Skip writing the final video")
parser.add_argument('--skip_loading_files', action='store_true', help="Skip loading the GPX and FIT files")
parser.add_argument('--skip_clip', action='store_true', help="Skip creating the image sequence clip")
parser.add_argument('--skip_test', action='store_true', help="loading test folder instead of full activities")
args = parser.parse_args()

skip_frames = args.skip_frames
skip_effects = args.skip_effects
skip_audio = args.skip_audio
skip_video_write = args.skip_write
skip_loading_files = args.skip_loading_files
skip_clip = args.skip_clip
skip_test = args.skip_test

# je rajoute apres 2eme comit.
# ===============================
# Configurations
# ===============================
if not skip_test:
    folder = "/Users/Tibo/Documents/strava/export_prod/activities_full"  # or _test
else :
    folder = "/Users/Tibo/Documents/strava/export_prod/activities_test"  # or _test

frames_folder = "frames_mercator14"
os.makedirs(frames_folder, exist_ok=True)

center_lat, center_lon = 48.8504, 2.2181
max_distance_km = 100
max_frames_per_course = 120
img_width, img_height = 800, 534 #previously 1200, 800
zoom = 13
speed_factor = 7.0
fps_final = 24
music_path = "/Users/Tibo/audiomachine.mp3"
output_file = "video_final_mercator21NOV.mp4"
background_map_path = "/Users/Tibo/Vibecoding/fond14.png" # previously 13
# background_map = Image.open(background_map_path).resize((img_width, img_height))

start_date_limit = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
temp_video_path = "temptout_video.mp4"

SUPER_SCALE = 2   # SuperSampling pour améliorer la qualité du rendu (anti-aliasing)
HI_W = img_width * SUPER_SCALE
HI_H = img_height * SUPER_SCALE
background_map = Image.open(background_map_path).resize((HI_W, HI_H), Image.LANCZOS)


# ===============================
# Fonctions utilitaires
# ===============================

def haversine(lat1, lon1, lat2, lon2):
    R = 6378.137
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    bb = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return bb

def blue_shade(i, total):
    import colorsys
    h, s, v = 2/3, 1.0, 1.0 - (i / max(total-1,1))*0.7
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r*255), int(g*255), int(b*255))

def real_basename(path):
    base = os.path.basename(path)
    if base.endswith(".fit.gz"):
        return base[:-7]   # retire ".fit.gz"
    return os.path.splitext(base)[0]


def green_shade(i, total):
    import colorsys
    t = i / max(total - 1, 1)

    # --- Phase 1 : Bleu → Violet (0 → 0.5)
    if t < 0.5:
        k = t / 0.5
        # Bleu profond ≈ 230° → Violet foncé ≈ 270°
        h = (230 + (270 - 230) * k) / 360
    # --- Phase 2 : Violet → Vert sombre (0.5 → 1)
    else:
        k = (t - 0.5) / 0.5
        # Violet foncé 270° → Vert sombre 120°
        h = (270 + (120 - 270) * k) / 360

    # Saturation modérée pour éviter le fluo
    s = 0.65

    # Valeur sombre et élégante
    v = 0.5

    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r*255), int(g*255), int(b*255))

def read_gpx(filepath):
    with open(filepath, "r") as f:
        gpx = gpxpy.parse(f)
    points = []
    for track in gpx.tracks:
        for seg in track.segments:
            for p in seg.points:
                points.append([p.latitude, p.longitude])
    return pd.DataFrame(points, columns=["lat", "lon"]) if points else pd.DataFrame(columns=["lat","lon"])

def catmull_rom_spline(P0, P1, P2, P3, n_points=20):
    """Retourne une liste de points interpolés entre P1 et P2."""
    alpha = 0.5  # tension
    t0 = 0
    t1 = ((P1[0]-P0[0])**2 + (P1[1]-P0[1])**2)**0.5**alpha + t0
    t2 = ((P2[0]-P1[0])**2 + (P2[1]-P1[1])**2)**0.5**alpha + t1
    t3 = ((P3[0]-P2[0])**2 + (P3[1]-P2[1])**2)**0.5**alpha + t2

    def interpolate(ti, t):
        return ((ti - t) / (ti - t0))

    t_values = np.linspace(t1, t2, n_points)
    curve = []

    for t in t_values:
        A1 = ((t1-t)/(t1-t0))*np.array(P0) + ((t-t0)/(t1-t0))*np.array(P1)
        A2 = ((t2-t)/(t2-t1))*np.array(P1) + ((t-t1)/(t2-t1))*np.array(P2)
        A3 = ((t3-t)/(t3-t2))*np.array(P2) + ((t-t2)/(t3-t2))*np.array(P3)

        B1 = ((t2-t)/(t2-t0))*A1 + ((t-t0)/(t2-t0))*A2
        B2 = ((t3-t)/(t3-t1))*A2 + ((t-t1)/(t3-t1))*A3

        C = ((t2-t)/(t2-t1))*B1 + ((t-t1)/(t2-t1))*B2
        curve.append(C.tolist())

    return curve


def decompress_gz(filepath):
    outpath = filepath[:-3]
    if not os.path.exists(outpath):
        with gzip.open(filepath, "rb") as f_in:
            with open(outpath, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
    return outpath

def read_fit(filepath):
    points = []
    with fitdecode.FitReader(filepath) as fit:
        for frame in fit:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            if frame.name != "record":
                continue
            lat = frame.get_value("position_lat", fallback=None)
            lon = frame.get_value("position_long", fallback=None)
            if lat is None or lon is None:
                continue
            lat = lat * (180 / 2**31)
            lon = lon * (180 / 2**31)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                continue
            points.append([lat, lon])
    return pd.DataFrame(points, columns=["lat", "lon"]) if points else pd.DataFrame(columns=["lat","lon"])

def is_near_center(df, center_lat, center_lon, max_distance_km):
    if df.empty:
        print("DataFrame is empty")
        return False
    for _, row in df.iterrows():
        if haversine(row["lat"], row["lon"], center_lat, center_lon) <= max_distance_km:
            #print(row["lat"])
            #print(row["lon"])
            #print(max_distance_km)
            #print(haversine(row["lat"], row["lon"], center_lat, center_lon) )
            return True
    return False

def get_gpx_start_time(filepath):
    with open(filepath, "r") as f:
        gpx = gpxpy.parse(f)
    for track in gpx.tracks:
        for seg in track.segments:
            for p in seg.points:
                if p.time:
                    return p.time
    return None

def get_fit_start_time(filepath):
    with fitdecode.FitReader(filepath) as fit:
        for frame in fit:
            if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "record":
                ts = frame.get_value("timestamp", fallback=None)
                if ts:
                    return ts
    return None

def smooth_trace(points, density=10):
    """Interpole chaque segment via spline Catmull–Rom."""
    if len(points) < 4:
        return points

    smoothed = []
    for i in range(1, len(points)-2):
        P0, P1, P2, P3 = points[i-1], points[i], points[i+1], points[i+2]
        seg = catmull_rom_spline(P0, P1, P2, P3, n_points=density)
        smoothed.extend(seg)

    return smoothed

# ===============================
# Valid Frame Checker
# ===============================
def is_valid_frame(frame_path):
    """Check if the frame file is valid (not corrupted or empty)."""
    try:
        with Image.open(frame_path) as img:
            img.verify()  # Verifies if the image is valid
        return True
    except (IOError, OSError):
        print(f"Warning: {frame_path} is invalid or corrupted.")
        return False

# ===============================
# Mercator -> pixel
# ===============================
R = 6378137
def latlon_to_mercator(lat, lon):
    x = math.radians(lon) * R
    y = math.log(math.tan(math.pi/4 + math.radians(lat)/2)) * R
    return x, y

def latlon_to_pixel(lat, lon, center_lat, center_lon, img_width, img_height, zoom):
    scale = 2**zoom
    x_c, y_c = latlon_to_mercator(center_lat, center_lon)
    x, y = latlon_to_mercator(lat, lon)
    meters_per_pixel = 2 * math.pi * R / (256 * scale)
    px = (img_width/2 + (x - x_c)/meters_per_pixel) * SUPER_SCALE
    py = (img_height/2 - (y - y_c)/meters_per_pixel) * SUPER_SCALE
    return int(px), int(py)

def interpolate_points(points, max_points):
    if len(points) <= max_points:
        return points
    if max_points == 1:
        return [points[0]]
    indices = [int(i*(len(points)-1)/(max_points-1)) for i in range(max_points)]
    return [points[i] for i in indices]

# ===============================
# Charger fichiers (with flag to skip)
# ===============================
if not skip_loading_files:
    # --- load raw lists ---
    gpx_files = sorted(glob.glob(os.path.join(folder, "*.gpx")))
    fit_files = sorted(glob.glob(os.path.join(folder, "*.fit")))
    gz_files  = sorted(glob.glob(os.path.join(folder, "*.fit.gz")))

    # --- decompress gz first, collect resulting .fit paths ---
    decompressed = []
    for gz in gz_files:
        outpath = gz[:-3]
        if not os.path.exists(outpath):
            decompress_gz(gz)
        decompressed.append(outpath)

    # --- combine candidates (use decompressed .fit instead of .fit.gz) ---
    candidates = []
    candidates += fit_files
    candidates += decompressed
    candidates += gpx_files
    print(f"Total files to process: {len(candidates)}")
    

    # --- helper to get base name without any of the recognized extensions ---
    def base_no_ext(path):
        name = os.path.basename(path)
        if name.endswith(".fit.gz"):
            return name[:-7]
        if name.endswith(".fit"):
            return name[:-4]
        if name.endswith(".gpx"):
            return name[:-4]
        return os.path.splitext(name)[0]

    # --- pick one file per base, with extension priority (.fit preferred over .gpx) ---
    ext_priority = [".fit", ".gpx"]  # order of preference
    by_base = {}

    # iterate by priority so higher-priority exts win
    for ext in ext_priority:
        for f in candidates:
            if not f.lower().endswith(ext):
                continue
            base = base_no_ext(f)
            if base in by_base:
                continue
            by_base[base] = f

    # any remaining bases (unrecognized ext), add them
    for f in candidates:
        base = base_no_ext(f)
        if base not in by_base:
            by_base[base] = f

    # final list
    all_files = sorted(by_base.values())
    total = len(all_files)
    print(f"Total files to process after removing duplicates: {total}")


#    total = 0

frames = []
distance_accum = 0.0  # km
cumulative_img = background_map.copy()
cumulative_draw = ImageDraw.Draw(cumulative_img)

def frames_exist():
    return len(os.listdir(frames_folder)) > 0


if not skip_frames:
    print("Génération des frames...")

    for i, file in enumerate(all_files):
        
        ext = file.split(".")[-1].lower()
        df = None
        start_time = None
        points = []

        if ext == "gpx":
            start_time = get_gpx_start_time(file)
        elif ext == "fit":
            start_time = get_fit_start_time(file)

        if start_time is None:
            print(f"Impossible de déterminer la date de {file}, ignoré")
            continue
        # --- FIX TZ AWARE / NAIVE ---
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=datetime.timezone.utc)

        if start_time < start_date_limit:
            print(f"{file} avant 2025, ignoré")
            continue

        try:
            if ext == "gpx":
                df = read_gpx(file)
            elif ext == "fit":
                df = read_fit(file)
        except Exception as e:
            print(f"Erreur lecture {file}: {e}")
            continue

        if df is None or df.shape[0] < 2:
            continue

        if not is_near_center(df, center_lat, center_lon, max_distance_km):
            print(f"Ignoré {file}, trop loin du centre")
            continue

        color = green_shade(i, total)

        points = df[["lat", "lon"]].values.tolist()
        points = interpolate_points(points, max_frames_per_course)
        # points = smooth_trace(points, density=5)   # ou 10 si tu veux très smooth, mais ça ajoute bcp de points

        for j in range(1, len(points)):

            # ======== CONVERSION LAT/LON -> PIXELS ========
            x0, y0 = latlon_to_pixel(*points[j-1], center_lat, center_lon, img_width, img_height, zoom)
            x1, y1 = latlon_to_pixel(*points[j],   center_lat, center_lon, img_width, img_height, zoom)

            # ======== TRAÇAGE SUR LA CARTE CUMULATIVE ========
            cumulative_draw.line([x0, y0, x1, y1], fill=color, width=3)

            # ======== CALCUL DISTANCE ========
            lat0, lon0 = points[j-1]
            lat1, lon1 = points[j]
            distance_accum += haversine(lat0, lon0, lat1, lon1)*1  # facteur ajusté pour Mercator

            # ======== CRÉATION FRAME INDIVIDUELLE ========
            # --- FRAME HI-RES ---
            frame_hi = cumulative_img.copy().convert("RGBA")
            # --- Overlay du point orange hi-res ---
            overlay = Image.new("RGBA", (HI_W, HI_H), (0,0,0,0))
            draw_overlay = ImageDraw.Draw(overlay)
            r = 7 * SUPER_SCALE
            orange_transparent = (255, 140, 0, 140)
            draw_overlay.ellipse(
                (x1 - r, y1 - r, x1 + r, y1 + r),
                fill=orange_transparent)
            # Cercle noir autour (plus fin, plus serré)
            draw_overlay.ellipse(
            (x1 - r - 1, y1 - r - 1, x1 + r + 1, y1 + r + 1),
            outline=(0, 0, 0, 255),
            width=1 * SUPER_SCALE)


            # Fusion overlay
            frame_hi = Image.alpha_composite(frame_hi, overlay)
            # ======== DOWNSCALE AVEC ANTI-ALIASING (LANCZOS) ========
            frame = frame_hi.resize((img_width, img_height), Image.LANCZOS)
            # Convertir en RGB
            frame = frame.convert("RGB")


            # ======== TEXTE: KM (IMPORTANT : après alpha_composite) ========
            draw_frame = ImageDraw.Draw(frame)

            text = f"{round(distance_accum):d} km"
            text_x = img_width - 10
            text_y = img_height - 10

            font = ImageFont.truetype("/Library/Fonts/Arial.ttf", 32)

            # Ombre
            draw_frame.text((text_x+2, text_y+2), text, fill=(0, 0, 0), font=font, anchor="rd")
            # Texte orange
            draw_frame.text((text_x, text_y), text, fill=(255, 165, 0), font=font, anchor="rd")

            # ======== SAVE FRAME ========
            frame_path = os.path.join(frames_folder, f"frame_{i:03d}_{j:03d}.png")
            frame.save(frame_path)

            # Convert to NumPy array and append
            frame_array = np.array(frame)
            if len(frame_array.shape) == 2:
                frame_array = np.stack([frame_array]*3, axis=-1)

            if is_valid_frame(frame_path):
                frames.append(frame_array)

        print(f"Course {file} ajoutée avec {len(points)} segments --> {i+1} / {total} frames générées.")
    print(f"Total frames générées: {len(frames)}") 

# Récupérer les frames existantes si skip_frames est True ou si elles existent déjà
if skip_frames or not frames:
    if frames_exist():
        print(f"Les frames existent déjà dans {frames_folder}.")
        frames_paths = sorted(glob.glob(os.path.join(frames_folder, "*.png")))
        frames = []
        for fp in frames_paths:
            if is_valid_frame(fp):
                frame_array = np.array(Image.open(fp))
                if len(frame_array.shape) == 2:
                    frame_array = np.stack([frame_array]*3, axis=-1)
                frames.append(frame_array)
        print(f"Valid frames count: {len(frames)}")
    else:
        if skip_frames:
            raise ValueError("Aucune frame existante à récupérer, et --skip_frames est activé.")
        # Sinon, frames restera vide et l'erreur sera levée plus bas


step_echantillion = 1 # Sélectionner un frame sur trois
frames = frames[::step_echantillion]  # Cela garde tous les éléments aux indices multiples de 3 (0, 3, 6, etc.)    
print(f"after triming by {step_echantillion}, new frames count: {len(frames)}")


if not frames:
    raise ValueError("Aucune frame trouvée ou générée. Vérifiez le dossier.")

# ===============================
# Créer la vidéo (only if flag is False)
# ===============================
if not skip_clip:
    # Step 1: Create the Image Sequence Clip
    
    print("Step 1: Creating image sequence clip...")
    clip_main = ImageSequenceClip(frames, fps=fps_final)
    # Dernier frame fixe 2s
    last_img = frames[-1]
    clip_last = ImageClip(last_img).set_duration(2)
    clip_last = clip_last.set_fps(fps_final)
    # Concat
    clip_final = concatenate_videoclips([clip_main, clip_last], method="compose")
    print("Image sequence clip created.")
    # Save the clip as a temporary video file
    clip_final.write_videofile(temp_video_path, codec="libx264", fps=fps_final)
else:
    print("Skipping clip creation and instead loading it if possible")
    # Reload the saved temporary video file to apply effects
    if os.path.exists(temp_video_path):
        clip = VideoFileClip(temp_video_path)
    else:
        print("Temporary video file not found. Cannot proceed without clip creation.")


# Step 2: Apply speed effect (optional)
if not skip_effects and speed_factor != 1.0:
    print(f"Step 2: Applying speed effect with factor {speed_factor}...")
    clip_final = clip_final.fx(lambda c: c.speedx(factor=speed_factor))
    print(f"Speed effect applied.")
else:
    print("Skipping speed effect.")

# Step 3: Add audio (if audio path exists)
if os.path.exists(music_path) and not skip_audio:
    print("Step 3: Adding audio...")
    audio = AudioFileClip(music_path).subclip(0, clip_final.duration)
    audio = audio.audio_fadein(1.0).audio_fadeout(2.0)
    if audio.duration < clip_final.duration:
        audio = afx.audio_loop(audio, duration=clip_final.duration)
    clip_final = clip_final.set_audio(audio)
    print("Audio added.")
else:
    print("Skipping audio addition.")

# Step 4: Write the final video to a file
if not skip_video_write:
    print(f"Step 4: Writing the final video to {output_file}...")
    clip_final.write_videofile(
    output_file,
    codec="libx264",
    audio_codec="aac",
    fps=fps_final,
    audio_bitrate="192k",
    bitrate="5000k",
    ffmpeg_params=[
        "-pix_fmt", "yuv420p",      # Format universel
        "-profile:v", "main",       # Compatible VLC
        "-level", "4.0",
    ]
    )
    print(f"🎉 Video generated: {output_file}")
# try with more or less bitrate