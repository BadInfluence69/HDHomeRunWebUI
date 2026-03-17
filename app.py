import os
import sys
import subprocess
import urllib.parse
import re
import requests
import json
from datetime import datetime
from flask import Flask, render_template_string, Response, request, stream_with_context, jsonify

app = Flask(__name__)

# ====== CONFIGURATION ======
MEDIA_DIR = os.path.dirname(os.path.abspath(__file__))
EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.mp3', '.wav', '.flac', '.m4a')
HDHR_IP = "192.168.0.163"
LISTENING_PORT = 5001

# --- LINEUP SETTINGS ---
USE_LOCAL_LINEUP = False 
LOCAL_LINEUP_FILE = os.path.join(MEDIA_DIR, "lineup.json")

# This is your persistent map of unencrypted "Ghost" and Premium channels
KNOWN_LABELS = {
    # Premium Movie Neighborhood
    "5020": "Showtime 2", 
    "5021": "Showtime East", 
    "5022": "Showtime East", 
    "5023": "Showtime Showcase", 
    "5024": "Showtime Family Zone",
    "5025": "Showtime Family Zone", 
    "5026": "Showtime Women", 
    "5027": "Showtime Next",
    "5028": "Showtime Extreme", 
    "5029": "FLIX",
    "5030": "The Movie Channel (TMC)", 
    "5031": "HBO East", 
    "5032": "HBO 2",
    "5033": "HBO Signature",
    "5034": "HBO Family",
    "5035": "HBO Comedy",
    "5036": "HBO Action",
    "5037": "HBO Zone",
    "5038": "HBO Latino",
    "5039": "Cinemax (Max East)",
    
    # Discovery & Action Neighborhood
    "5003": "VICE", 
    "5004": "Science Channel (SCI)", 
    "5005": "American Heroes (AHC)", 
    "5006": "Disney XD", 
    "5008": "Lifetime (LIFE)", 
    "5011": "LMN", 
    "5012": "FXM", 
    "5014": "POP NETWORK", 
    "5016": "POP", 
    "5017": "CBS",
    
    # Broadcast & Diginets
    "5000": "ABC West",
    "5051": "ABC East",
    "5040": "Heroes & Icons (H&I)", 
    "5041": "Court TV", 
    "5042": "MeTV",
    "5043": "The Nest", 
    "5044": "Nat Geo WILD", 
    "5045": "ONE", 
    "5046": "HSN", 
    "5047": "BBC",
    "5048": "Sundance TV", 
    "5049": "IFC",
    "5053": "Fox 23", 
    "5054": "CBS KFVS12",
    "53": "FXX"
}

# ====== 1. HELPERS ======
def clean_name(filename):
    name = os.path.splitext(filename)[0]
    bloat_patterns = [r'\b\d{3,4}p\b', r'\bBRRip\b', r'\bBluRay\b', r'\bx264\b', r'\bx265\b', r'\bHEVC\b', r'\b10bit\b']
    name = name.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    for pattern in bloat_patterns:
        name = re.sub(pattern, '', name, flags=re.IGNORECASE)
    return ' '.join(name.split()).strip()

def get_live_lineup():
    """Fetches HDHR data but enforces your custom KNOWN_LABELS names."""
    final_lineup = {}
    
    # 1. Start with your KNOWN_LABELS as the master list
    for ch, name in KNOWN_LABELS.items():
        final_lineup[ch] = name

    # 2. Merge with live data from the tuner
    try:
        resp = requests.get(f"http://{HDHR_IP}/lineup.json", timeout=2)
        if resp.status_code == 200:
            broadcast_data = resp.json()
            for item in broadcast_data:
                ch_num = str(item['GuideNumber'])
                
                # Check if we already mapped this manually
                if ch_num not in final_lineup:
                    name = item.get('GuideName')
                    if not name or name.startswith('Ch '):
                        final_lineup[ch_num] = f"Unknown ({ch_num})"
                    else:
                        final_lineup[ch_num] = name
    except Exception as e:
        print(f"Error fetching HDHR lineup: {e}")

    return final_lineup

def get_organized_media():
    structured_data = {"MOVIES": {}, "TV_SHOWS": {}, "MUSIC": {}}
    for root, dirs, files in os.walk(MEDIA_DIR):
        media_files = [f for f in files if f.lower().endswith(EXTENSIONS)]
        if media_files:
            path_upper = root.upper()
            category = "MOVIES" if "MOVIE" in path_upper else "TV_SHOWS" if any(x in path_upper for x in ["TV", "SHOW", "SEASON"]) else "MUSIC"
            folder_raw = os.path.basename(root)
            folder_display = clean_name(folder_raw) if root != MEDIA_DIR else "Library Root"
            if folder_display not in structured_data[category]:
                structured_data[category][folder_display] = []
            for f in media_files:
                rel_path = os.path.relpath(os.path.join(root, f), MEDIA_DIR)
                structured_data[category][folder_display].append({
                    "display_name": clean_name(f), "path": rel_path,
                    "is_audio": f.lower().endswith(('.mp3', '.wav', '.flac', '.m4a'))
                })
    return structured_data

# ====== 2. STREAMING & BYPASS ======
@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Private-Network', 'true')
    return response

@app.route('/stream/<path:filename>')
def stream_media(filename):
    filename = urllib.parse.unquote(filename)
    file_path = os.path.abspath(os.path.join(MEDIA_DIR, filename))
    if not os.path.exists(file_path): return "File not found", 404
    
    is_audio = filename.lower().endswith(('.mp3', '.wav', '.flac', '.m4a'))
    should_upscale = request.args.get('upscale', 'false') == 'true'

    if is_audio:
        cmd = ['ffmpeg', '-i', file_path, '-acodec', 'aac', '-b:a', '320k', '-f', 'adts', 'pipe:1']
        mimetype = 'audio/aac'
    elif should_upscale:
        cmd = ['ffmpeg', '-hwaccel', 'cuda', '-hwaccel_output_format', 'cuda', '-i', file_path,
               '-vf', 'scale_cuda=1080:-1', '-c:v', 'hevc_nvenc', '-preset', 'p1', '-tune', 'ull', 
               '-c:a', 'aac', '-b:a', '320k', '-f', 'mp4', '-movflags', 'frag_keyframe+empty_moov+default_base_moof', 'pipe:1']
        mimetype = 'video/mp4'
    else:
        cmd = ['ffmpeg', '-i', file_path, '-vcodec', 'copy', '-acodec', 'aac', '-ab', '320k', '-f', 'mp4', 
               '-movflags', 'frag_keyframe+empty_moov+default_base_moof', 'pipe:1']
        mimetype = 'video/mp4'

    def generate():
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            while True:
                data = process.stdout.read(1024 * 1024)
                if not data: break
                yield data
        finally: process.kill()
    return Response(stream_with_context(generate()), mimetype=mimetype)

@app.route('/tuner/<channel>')
def tuner(channel):
    target_url = f"http://{HDHR_IP}:5004/auto/v{channel}"
    ffmpeg_cmd = [
        'ffmpeg', '-i', target_url,
        '-vf', 'scale=-1:1080,hqdn3d=1.5:1.5:6:6,unsharp=3:3:0.5:3:3:0.5',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-crf', '20', '-c:a', 'aac', '-b:a', '192k',
        '-f', 'mp4', '-movflags', 'separate_moof+frag_keyframe+empty_moov+default_base_moof', 'pipe:1'
    ]
    def generate():
        process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            while True:
                chunk = process.stdout.read(1024*64)
                if not chunk: break
                yield chunk
        finally: process.kill()
    return Response(stream_with_context(generate()), mimetype='video/mp4')

# ====== 3. UNIFIED INTERFACE ======
INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>The Hub | Unified Media</title>
    <style>
        * { box-sizing: border-box; }
        body { background: #050505; color: #fff; font-family: 'Segoe UI', sans-serif; margin: 0; display: grid; grid-template-columns: 320px 1fr 320px; height: 100vh; overflow: hidden; }
        .sidebar { background: #0c0c0c; border-right: 1px solid #1a1a1a; overflow-y: auto; padding: 20px; z-index: 20; }
        .sidebar-right { border-right: none; border-left: 1px solid #1a1a1a; }
        #center-zone { display: flex; flex-direction: column; background: #000; padding: 10px; overflow: hidden; align-items: center; justify-content: flex-start; }
        #search-box { width: 100%; max-width: 800px; padding: 12px; margin-bottom: 15px; background: #111; border: 1px solid #333; border-radius: 20px; color: #fff; outline: none; text-align: center; z-index: 30; }
        h2 { color: #444; font-size: 0.8em; text-transform: uppercase; letter-spacing: 2px; border-bottom: 1px solid #1a1a1a; padding-bottom: 8px; margin-top: 30px; }
        .live-tv-header { color: #ff0000 !important; }
        .folder-label { color: #00ffcc; font-size: 0.7em; margin-top: 15px; opacity: 0.5; }
        .file-link { display: block; padding: 8px 12px; margin: 2px 0; border-radius: 4px; color: #888; text-decoration: none; font-size: 0.9em; cursor: pointer; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .file-link:hover { background: #1a1a1a; color: #fff; }
        .file-link.active { background: #00ffcc; color: #000; font-weight: 600; }
        .live-link.active { background: #ff0000; color: #fff; }
        #player-container { width: 100%; height: 75vh; position: relative; overflow: hidden; border-radius: 8px; background: #000; }
        video { width: 100%; height: 100%; object-fit: contain; }
        #now-playing-info { margin-top: 15px; text-align: center; }
        .hidden { display: none !important; }
    </style>
</head>
<body>
    <div class="sidebar">
        <h2 class="live-tv-header">📡 Live Tuner</h2>
        <div id="live-list">
            {% for ch, name in live_channels.items() %}
                <div class="file-link live-link" onclick="playLive('{{ ch }}', this, '{{ name }}')">📺 {{ ch }}: {{ name }}</div>
            {% endfor %}
        </div>
        <h2>Movies</h2>
        <div id="movie-list">
            {% for folder, items in library.MOVIES.items() %}
                <div class="folder-label">{{ folder }}</div>
                {% for item in items %}
                    <div class="file-link" onclick="playMedia('{{ item.path|urlencode }}', this, false, '{{ item.display_name|replace("'", "\\\\'") }}')">🎬 {{ item.display_name }}</div>
                {% endfor %}
            {% endfor %}
        </div>
    </div>
    <div id="center-zone">
        <input type="text" id="search-box" placeholder="Search Channels or Media..." onkeyup="filterAll()">
        <div id="player-container"><video id="player" controls autoplay></video></div>
        <div id="now-playing-info">
            <div id="now-playing" style="font-size: 1.1em; font-weight: bold; color: #eee;">System Standby</div>
            <label style="font-size:0.8em; color:#444; margin-top:10px; display:block;">
                <input type="checkbox" id="upscale-check"> Live Master 1080p Upscaler (GPU)
            </label>
        </div>
    </div>
    <div class="sidebar sidebar-right">
        <h2>TV Series</h2>
        <div id="tv-list">
            {% for folder, items in library.TV_SHOWS.items() %}
                <div class="folder-label">{{ folder }}</div>
                {% for item in items %}
                    <div class="file-link" onclick="playMedia('{{ item.path|urlencode }}', this, false, '{{ item.display_name|replace("'", "\\\\'") }}')">📺 {{ item.display_name }}</div>
                {% endfor %}
            {% endfor %}
        </div>
    </div>
    <script>
        function filterAll() {
            let input = document.getElementById('search-box').value.toLowerCase();
            document.querySelectorAll('.file-link').forEach(item => {
                const text = item.innerText.toLowerCase();
                item.classList.toggle('hidden', !text.includes(input));
            });
        }
        function playMedia(path, element, isAudio, cleanName) {
            document.querySelectorAll('.file-link').forEach(el => el.classList.remove('active'));
            element.classList.add('active');
            const player = document.getElementById('player');
            const useUpscale = document.getElementById('upscale-check').checked;
            document.getElementById('now-playing').innerText = cleanName;
            player.src = window.location.origin + "/stream/" + path + (isAudio ? "" : "?upscale=" + useUpscale);
            player.play();
        }
        function playLive(ch, element, name) {
            document.querySelectorAll('.file-link').forEach(el => el.classList.remove('active'));
            element.classList.add('active');
            const player = document.getElementById('player');
            document.getElementById('now-playing').innerText = "LIVE: " + name;
            player.src = window.location.origin + "/tuner/" + ch;
            player.play();
        }
    </script>
</body>     
</html>
"""

@app.route('/')
def index():
    lineup = get_live_lineup()
    sorted_lineup = dict(sorted(lineup.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 9999))
    return render_template_string(INDEX_HTML, library=get_organized_media(), live_channels=sorted_lineup)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=LISTENING_PORT, threaded=True)
