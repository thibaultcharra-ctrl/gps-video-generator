# genrunzS1.py
# -*- coding: utf-8 -*-
from gencarte import main_pipeline
import os, glob, gzip, shutil, math, datetime
import pandas as pd, numpy as np, pytz, gpxpy, fitdecode
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import (
    VideoFileClip, 
    AudioFileClip, 
    ImageSequenceClip, 
    concatenate_videoclips,
    ImageClip
)
try:
    # Try newer moviepy syntax
    from moviepy.video.fx.speedx import speedx
    from moviepy.audio.fx.audio_loop import audio_loop
    from moviepy.audio.fx.audio_fadein import audio_fadein
    from moviepy.audio.fx.audio_fadeout import audio_fadeout
except ImportError:
    # Fallback to older moviepy syntax
    from moviepy.video import fx as vfx
    from moviepy.audio import fx as afx
    speedx = vfx.speedx
    audio_loop = afx.audio_loop
    audio_fadein = afx.audio_fadein
    audio_fadeout = afx.audio_fadeout


# ===============================
# Utility Functions
# ===============================

def haversine(lat1, lon1, lat2, lon2):
    """Calculate distance between two points on Earth (in km)"""
    R = 6378.137
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    bb = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return bb


def green_shade(i, total):
    """Generate gradient color from green to orange"""
    import colorsys
    t = i / max(total - 1, 1)
    if t < 0.5:
        k = t / 0.5
        h = (230 + (270 - 230) * k) / 360
    else:
        k = (t - 0.5) / 0.5
        h = (270 + (120 - 270) * k) / 360
    s = 0.65
    v = 0.5
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r*255), int(g*255), int(b*255))


def read_gpx(filepath):
    """Read GPX file and return DataFrame with lat/lon"""
    with open(filepath, "r") as f:
        gpx = gpxpy.parse(f)
    points = []
    for track in gpx.tracks:
        for seg in track.segments:
            for p in seg.points:
                points.append([p.latitude, p.longitude])
    return pd.DataFrame(points, columns=["lat", "lon"]) if points else pd.DataFrame(columns=["lat","lon"])


def read_fit(filepath):
    """Read FIT file and return DataFrame with lat/lon"""
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
    """Check if any point in route is near the center"""
    if df.empty:
        return False
    for _, row in df.iterrows():
        if haversine(row["lat"], row["lon"], center_lat, center_lon) <= max_distance_km:
            return True
    return False


def decompress_gz(filepath):
    """Decompress .gz file"""
    outpath = filepath[:-3]
    if not os.path.exists(outpath):
        with gzip.open(filepath, "rb") as f_in:
            with open(outpath, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)
    return outpath


def get_gpx_start_time(filepath):
    """Extract start time from GPX file"""
    with open(filepath, "r") as f:
        gpx = gpxpy.parse(f)
    for track in gpx.tracks:
        for seg in track.segments:
            for p in seg.points:
                if p.time:
                    return p.time
    return None


def get_fit_start_time(filepath):
    """Extract start time from FIT file"""
    with fitdecode.FitReader(filepath) as fit:
        for frame in fit:
            if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "record":
                ts = frame.get_value("timestamp", fallback=None)
                if ts:
                    return ts
    return None


def is_valid_frame(frame_path):
    """Check if image file is valid"""
    try:
        with Image.open(frame_path) as img:
            img.verify()
        return True
    except (IOError, OSError):
        return False


# Mercator projection
R = 6378137

def latlon_to_mercator(lat, lon):
    """Convert lat/lon to Mercator coordinates"""
    x = math.radians(lon) * R
    y = math.log(math.tan(math.pi/4 + math.radians(lat)/2)) * R
    return x, y


def latlon_to_pixel(lat, lon, center_lat, center_lon, img_width, img_height, zoom, SUPER_SCALE=2):
    """Convert lat/lon to pixel coordinates on map"""
    scale = 2**zoom
    x_c, y_c = latlon_to_mercator(center_lat, center_lon)
    x, y = latlon_to_mercator(lat, lon)
    meters_per_pixel = 2 * math.pi * R / (256 * scale)
    px = (img_width/2 + (x - x_c)/meters_per_pixel) * SUPER_SCALE
    py = (img_height/2 - (y - y_c)/meters_per_pixel) * SUPER_SCALE
    return int(px), int(py)


def interpolate_points(points, max_points):
    """Interpolate points to have at most max_points"""
    if len(points) <= max_points:
        return points
    if max_points == 1:
        return [points[0]]
    indices = [int(i*(len(points)-1)/(max_points-1)) for i in range(max_points)]
    return [points[i] for i in indices]

def add_copyright(img, text="©RunnerSuresnois"):
    """
    Ajoute un copyright en bas à gauche de l'image.
    img = image PIL
    Retourne une image PIL
    """
    image = img.copy()
    draw = ImageDraw.Draw(image)
    # couleur et style
    font_size = max(16, image.width // 40)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except:
        font = ImageFont.load_default()
    margin = 10
    x = margin
    y = image.height - font_size - margin
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    return image


# ===============================
# MAIN PIPELINE
# ===============================
def main_pipeline(
    folder,
    frames_folder="frames_mercator14",
    skip_frames=False,
    skip_effects=False,
    skip_audio=False,
    skip_write=False,
    skip_loading=False,
    skip_clip=False,
    errase_frame_folder=False,
    speed_factor=7.0,
    max_frames_per_course = 120,
    music_path="audiomachine.mp3",
    output_file="video_final.mp4"):
    
    """
    Main pipeline to generate video from GPS data
    
    Args:
        folder: Path to folder containing .gpx/.fit files
        skip_frames: Skip frame generation (use existing)
        skip_effects: Skip speed effects
        skip_audio: Skip audio addition
        skip_write: Skip final video write
        skip_loading: Skip file loading
        skip_clip: Skip video clip creation
        speed_factor: Video speed multiplier
        music_path: Path to background music
        output_file: Output video filename
    """

    # Configuration
    os.makedirs(frames_folder, exist_ok=True)

    center_lat, center_lon = 48.8504, 2.2181  # Paris
    max_distance_km = 100
    img_width, img_height = 800, 534
    zoom = 13
    fps_final = 24
    # background_map_path = "fond14.png"
    SUPER_SCALE = 2
    HI_W = img_width * SUPER_SCALE
    HI_H = img_height * SUPER_SCALE
    
    # if not os.path.exists(background_map_path):
    #     raise FileNotFoundError(f"Background map not found: {background_map_path}") 
    # background_map = Image.open(background_map_path).resize((HI_W, HI_H), Image.LANCZOS)
    background_map = generate_map_image(img_width, img_height, center_lat, center_lon, zoom)
    background_map = add_copyright(background_map)
    start_date_limit = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    temp_video_path = "temptout_video.mp4"

    frames = []
    distance_accum = 0.0
    cumulative_img = background_map.copy()
    cumulative_draw = ImageDraw.Draw(cumulative_img)

    # -----------------------
    # Load files
    # -----------------------
    if not skip_loading:
        print("Loading GPS files...")
        gpx_files = sorted(glob.glob(os.path.join(folder, "*.gpx")))
        fit_files = sorted(glob.glob(os.path.join(folder, "*.fit")))
        gz_files  = sorted(glob.glob(os.path.join(folder, "*.fit.gz")))

        decompressed = [decompress_gz(gz) for gz in gz_files]
        candidates = fit_files + decompressed + gpx_files

        def base_no_ext(path):
            name = os.path.basename(path)
            for ext in [".fit.gz", ".fit", ".gpx"]:
                if name.endswith(ext):
                    return name[:-len(ext)]
            return os.path.splitext(name)[0]

        ext_priority = [".fit", ".gpx"]
        by_base = {}
        for ext in ext_priority:
            for f in candidates:
                if not f.lower().endswith(ext):
                    continue
                base = base_no_ext(f)
                if base not in by_base:
                    by_base[base] = f
        for f in candidates:
            base = base_no_ext(f)
            if base not in by_base:
                by_base[base] = f

        all_files = sorted(by_base.values())
        total = len(all_files)
        print(f"Found {total} GPS files")
    else:
        all_files = []
        total = 0

    # -----------------------
    # Generate frames
    # -----------------------
    if not skip_frames and all_files:
        print("Generating frames...")
        # Delete existing frames folder and recreate it
        if not errase_frame_folder:
            if os.path.exists(frames_folder):
                shutil.rmtree(frames_folder)
            os.makedirs(frames_folder, exist_ok=True)
        for i, file in enumerate(all_files):
            print(f"Processing {i+1}/{total}: {os.path.basename(file)}")
            ext = file.split(".")[-1].lower()
            df = None
            start_time = None

            # Get start time
            if ext == "gpx": 
                start_time = get_gpx_start_time(file)
            elif ext == "fit": 
                start_time = get_fit_start_time(file)
            
            if start_time is None: 
                continue
            if start_time.tzinfo is None: 
                start_time = start_time.replace(tzinfo=datetime.timezone.utc)
            if start_time < start_date_limit: 
                continue

            # Read GPS data
            try:
                if ext == "gpx": 
                    df = read_gpx(file)
                elif ext == "fit": 
                    df = read_fit(file)
            except Exception as e:
                print(f"  Error reading file: {e}")
                continue
            
            if df is None or df.shape[0] < 2: 
                continue
            if not is_near_center(df, center_lat, center_lon, max_distance_km): 
                continue

            # Draw route
            color = green_shade(i, total)
            points = df[["lat","lon"]].values.tolist()
            points = interpolate_points(points, max_frames_per_course)

            for j in range(1, len(points)):
                x0, y0 = latlon_to_pixel(*points[j-1], center_lat, center_lon, img_width, img_height, zoom, SUPER_SCALE)
                x1, y1 = latlon_to_pixel(*points[j], center_lat, center_lon, img_width, img_height, zoom, SUPER_SCALE)
                cumulative_draw.line([x0, y0, x1, y1], fill=color, width=3)
                
                lat0, lon0 = points[j-1]
                lat1, lon1 = points[j]
                distance_accum += haversine(lat0, lon0, lat1, lon1)

                # Create frame with marker
                frame_hi = cumulative_img.copy().convert("RGBA")
                overlay = Image.new("RGBA", (HI_W, HI_H), (0,0,0,0))
                draw_overlay = ImageDraw.Draw(overlay)
                r = 7 * SUPER_SCALE
                draw_overlay.ellipse((x1-r, y1-r, x1+r, y1+r), fill=(255,140,0,140))
                draw_overlay.ellipse((x1-r-1, y1-r-1, x1+r+1, y1+r+1), outline=(0,0,0,255), width=1*SUPER_SCALE)
                frame_hi = Image.alpha_composite(frame_hi, overlay)
                frame = frame_hi.resize((img_width, img_height), Image.LANCZOS).convert("RGB")

                # Add distance text
                draw_frame = ImageDraw.Draw(frame)
                text = f"{round(distance_accum):d} km"
                try:
                    font = ImageFont.truetype("/Library/Fonts/Arial.ttf", 32)
                except:
                    font = ImageFont.load_default()
                draw_frame.text((img_width-8, img_height-8), text, fill=(0,0,0), font=font, anchor="rd")
                draw_frame.text((img_width-10, img_height-10), text, fill=(255,165,0), font=font, anchor="rd")

                # Save frame
                frame_path = os.path.join(frames_folder, f"frame_{i:03d}_{j:03d}.png")
                frame.save(frame_path)
                if is_valid_frame(frame_path):
                    frames.append(np.array(frame))

    # Load existing frames if skipped
    if (skip_frames or not frames) and os.path.exists(frames_folder):
        print("Loading existing frames...")
        frame_files = sorted(glob.glob(os.path.join(frames_folder, "*.png")))
        for fp in frame_files:
            if is_valid_frame(fp):
                frame_array = np.array(Image.open(fp))
                if len(frame_array.shape) == 2: 
                    frame_array = np.stack([frame_array]*3, axis=-1)
                frames.append(frame_array)
        print(f"Loaded {len(frames)} frames")

    if not frames: 
        raise ValueError("No frames available")

    # -----------------------
    # Create video
    # -----------------------
    if not skip_clip:
        print("Creating video clip...")
        clip_main = ImageSequenceClip(frames, fps=fps_final)
        clip_last = ImageClip(frames[-1]).set_duration(2).set_fps(fps_final)
        clip_final = concatenate_videoclips([clip_main, clip_last], method="compose")
        clip_final.write_videofile(temp_video_path, codec="libx264", fps=fps_final)
    else:
        if os.path.exists(temp_video_path):
            clip_final = VideoFileClip(temp_video_path)
        else:
            clip_final = None

    # Apply speed effect
    if clip_final and not skip_effects and speed_factor != 1.0:
        print(f"Applying speed factor: {speed_factor}x")
        try:
            clip_final = speedx(clip_final, speed_factor)
        except TypeError:
            # Fallback for different moviepy versions
            clip_final = clip_final.fx(speedx, speed_factor)

    # Add audio
    if clip_final and not skip_audio and os.path.exists(music_path):
        print("Adding audio...")
        try:
            audio = AudioFileClip(music_path)
            audio = audio.subclip(0, min(audio.duration, clip_final.duration))
            
            # Apply audio effects with version compatibility
            try:
                audio = audio_fadein(audio, 1.0)
                audio = audio_fadeout(audio, 2.0)
            except TypeError:
                audio = audio.fx(audio_fadein, 1.0)
                audio = audio.fx(audio_fadeout, 2.0)
            
            if audio.duration < clip_final.duration:
                try:
                    audio = audio_loop(audio, duration=clip_final.duration)
                except TypeError:
                    audio = audio.fx(audio_loop, duration=clip_final.duration)
            
            clip_final = clip_final.set_audio(audio)
        except Exception as e:
            print(f"Warning: Could not add audio - {e}")
            print("Continuing without audio...")

    # Write final video
    if clip_final and not skip_write:
        print(f"Writing final video: {output_file}")
        clip_final.write_videofile(output_file, codec="libx264", audio_codec="aac", fps=fps_final)
        print("Done!")

    return output_file


if __name__ == "__main__":
    # Example usage
    output = main_pipeline(
        folder="GPS_DATA",  # Replace with your folder path
        skip_frames=False,
        speed_factor=7.0,
        music_path="audiomachine.mp3",
        output_file="video_final.mp4"
    )
    print(f"Video created: {output}")