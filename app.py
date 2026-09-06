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
HDHR_IP = "192.168.0.169"
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

def count_items(section):
    return sum(len(items) for items in section.values())

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
        '-c:v', 'libx265', '-preset', 'ultrafast', '-tune', 'zerolatency',
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
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>The Hub</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&family=Barlow+Condensed:wght@500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --void:#0A0E14;
  --panel:#111722;
  --panel-2:#18202E;
  --line:#222C3D;
  --ink:#EDF1F7;
  --ink-2:#98A4B8;
  --ink-3:#5C6980;
  --live:#FF9F1C;
  --lib:#7FA8FF;
  --sans:'Barlow','Segoe UI',system-ui,sans-serif;
  --cond:'Barlow Condensed','Segoe UI',system-ui,sans-serif;
}
*{box-sizing:border-box;}
html,body{height:100%;}
body{
  margin:0; background:var(--void); color:var(--ink);
  font-family:var(--sans); font-size:15px; line-height:1.45;
  display:grid; grid-template-rows:auto minmax(0,1fr); height:100dvh; overflow:hidden;
}

/* ---------- header ---------- */
.bar{
  display:flex; align-items:center; gap:20px;
  padding:0 20px; height:60px;
  background:var(--panel); border-bottom:1px solid var(--line);
}
.brand{display:flex; align-items:baseline; gap:9px; flex:0 0 auto;}
.brand b{font-family:var(--cond); font-weight:700; font-size:1.5rem; letter-spacing:.02em;}
.brand span{color:var(--ink-3); font-size:.8rem;}
.bars{display:flex; align-items:flex-end; gap:2px; height:16px; margin-right:2px;}
.bars i{width:3px; background:var(--lib); border-radius:1px; display:block;}
.bars i:nth-child(1){height:5px;}
.bars i:nth-child(2){height:9px;}
.bars i:nth-child(3){height:13px;}
.bars i:nth-child(4){height:16px; background:var(--live);}

.search{position:relative; flex:1 1 auto; max-width:560px; margin-inline:auto;}
.search input{
  width:100%; padding:9px 34px 9px 14px;
  background:var(--void); border:1px solid var(--line); border-radius:8px;
  color:var(--ink); font:inherit; font-size:.92rem; outline:none;
}
.search input::placeholder{color:var(--ink-3);}
.search input:focus{border-color:var(--lib); box-shadow:0 0 0 3px rgba(127,168,255,.14);}
.search kbd{
  position:absolute; right:10px; top:50%; transform:translateY(-50%);
  color:var(--ink-3); font-family:var(--cond); font-size:.85rem; pointer-events:none;
}
.ghost{
  background:none; border:1px solid var(--line); color:var(--ink-2);
  font:inherit; font-size:.85rem; padding:7px 13px; border-radius:8px; cursor:pointer;
}
.ghost:hover{color:var(--ink); border-color:var(--ink-3);}

/* ---------- shell ---------- */
.app{display:grid; grid-template-columns:320px minmax(0,1fr) 330px; min-height:0;}
.rail{
  background:var(--panel); overflow-y:auto; padding:0 12px 28px;
  border-right:1px solid var(--line); min-height:0;
}
.rail.right{border-right:none; border-left:1px solid var(--line);}

.head{
  position:sticky; top:0; z-index:5;
  display:flex; align-items:center; gap:8px;
  padding:16px 4px 9px; margin-bottom:4px;
  background:var(--panel); border-bottom:1px solid var(--line);
}
.head h2{
  margin:0; font-family:var(--cond); font-weight:600; font-size:1.15rem;
  letter-spacing:.01em; color:var(--ink);
}
.head .n{margin-left:auto; font-family:var(--cond); font-size:.95rem; color:var(--ink-3);}
.head .dot{width:7px; height:7px; border-radius:50%; background:var(--live);}

.group{margin-bottom:10px;}
.group h3{
  margin:14px 0 4px; padding:0 10px;
  font-weight:500; font-size:.75rem; color:var(--ink-3); letter-spacing:.01em;
}
.row{
  display:flex; align-items:center; gap:10px; width:100%;
  padding:7px 10px; margin:1px 0; border:0; border-radius:8px;
  background:none; color:var(--ink-2); font:inherit; font-size:.9rem;
  text-align:left; cursor:pointer;
}
.row .t{overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
.row .num{
  flex:0 0 auto; min-width:3.4ch; text-align:right;
  font-family:var(--cond); font-weight:600; font-size:1rem;
  font-variant-numeric:tabular-nums; color:var(--ink-3);
}
.row:hover{background:var(--panel-2); color:var(--ink);}
.row:focus-visible{outline:2px solid var(--lib); outline-offset:-2px;}
.row.on{background:rgba(127,168,255,.13); color:var(--ink); box-shadow:inset 2px 0 0 var(--lib);}
.row.live.on{background:rgba(255,159,28,.13); box-shadow:inset 2px 0 0 var(--live);}
.row.live.on .num{color:var(--live);}
.empty{padding:10px; color:var(--ink-3); font-size:.85rem;}

/* ---------- stage ---------- */
.stage{
  display:flex; flex-direction:column; gap:16px; align-items:center;
  padding:22px; min-height:0; overflow:auto;
}
.frame{
  position:relative; width:100%; max-width:1280px; aspect-ratio:16/9;
  max-height:calc(100dvh - 200px);
  background:#000; border:1px solid var(--line); border-radius:12px; overflow:hidden;
}
video{display:block; width:100%; height:100%; object-fit:contain; background:#000;}
.veil{
  position:absolute; inset:0; display:flex; flex-direction:column;
  align-items:center; justify-content:center; gap:14px;
  background:radial-gradient(circle at 50% 45%, #10161F 0%, #05080C 70%);
  color:var(--ink-3); text-align:center; padding:20px;
}
.veil.off{display:none;}
.veil p{margin:0; font-size:.92rem; max-width:34ch;}
.veil strong{display:block; color:var(--ink); font-family:var(--cond); font-size:1.4rem; font-weight:600;}
.eq{display:flex; align-items:flex-end; gap:4px; height:34px;}
.eq i{width:5px; height:10px; border-radius:2px; background:var(--ink-3); display:block;}
.eq.go i{background:var(--live); animation:pulse 1s ease-in-out infinite;}
.eq.go i:nth-child(2){animation-delay:.12s;}
.eq.go i:nth-child(3){animation-delay:.24s;}
.eq.go i:nth-child(4){animation-delay:.36s;}
.eq.go i:nth-child(5){animation-delay:.48s;}
@keyframes pulse{0%,100%{height:9px;opacity:.5;} 50%{height:32px;opacity:1;}}

.strip{
  display:grid; grid-template-columns:auto minmax(0,1fr) auto; align-items:center; gap:18px;
  width:100%; max-width:1280px;
  padding:12px 16px; background:var(--panel); border:1px solid var(--line); border-radius:10px;
}
.badge{
  display:flex; align-items:center; gap:7px;
  font-family:var(--cond); font-weight:600; font-size:1rem; color:var(--ink-3);
}
.badge i{width:8px; height:8px; border-radius:50%; background:var(--ink-3); display:block;}
.strip.live .badge{color:var(--live);}
.strip.live .badge i{background:var(--live); animation:blink 2s ease-in-out infinite;}
.strip.file .badge{color:var(--lib);}
.strip.file .badge i{background:var(--lib);}
@keyframes blink{0%,100%{opacity:1;} 50%{opacity:.25;}}
#title{font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;}
#mode{color:var(--ink-3); font-size:.85rem; text-align:right;}

.toggle{display:flex; align-items:center; gap:10px; color:var(--ink-2); font-size:.88rem; cursor:pointer;}
.toggle input{position:absolute; opacity:0; width:0; height:0;}
.track{
  width:38px; height:21px; border-radius:11px; background:var(--panel-2);
  border:1px solid var(--line); position:relative; transition:background .15s, border-color .15s;
}
.track::after{
  content:""; position:absolute; top:2px; left:2px; width:15px; height:15px;
  border-radius:50%; background:var(--ink-3); transition:transform .15s, background .15s;
}
.toggle input:checked + .track{background:rgba(127,168,255,.22); border-color:var(--lib);}
.toggle input:checked + .track::after{transform:translateX(17px); background:var(--lib);}
.toggle input:focus-visible + .track{outline:2px solid var(--lib); outline-offset:2px;}
.hint{color:var(--ink-3); font-size:.8rem;}

.hide{display:none !important;}
::-webkit-scrollbar{width:10px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--line); border-radius:5px; border:3px solid var(--panel);}
::-webkit-scrollbar-thumb:hover{background:var(--ink-3);}

@media (max-width:1280px){ .app{grid-template-columns:260px minmax(0,1fr) 270px;} }
@media (max-width:1000px){
  body{overflow:auto;}
  .app{grid-template-columns:1fr; grid-auto-rows:min-content;}
  .rail{border:0; border-top:1px solid var(--line); max-height:none;}
  .frame{max-height:none;}
  .bar{flex-wrap:wrap; height:auto; padding:10px 14px; gap:10px;}
  .search{order:3; flex-basis:100%; max-width:none;}
}
@media (prefers-reduced-motion:reduce){ *{animation:none !important; transition:none !important;} }
</style>
</head>
<body>

<header class="bar">
  <div class="brand">
    <span class="bars"><i></i><i></i><i></i><i></i></span>
    <b>The Hub</b>
    <span>{{ ip }}</span>
  </div>
  <div class="search">
    <input id="q" type="search" placeholder="Search channels, movies, shows and music" autocomplete="off">
    <kbd>/</kbd>
  </div>
  <button class="ghost" onclick="location.reload()">Refresh lineup</button>
</header>

<div class="app">

  <aside class="rail">
    <div class="head"><span class="dot"></span><h2>Live tuner</h2><span class="n">{{ live_channels|length }}</span></div>
    <div class="sec" data-empty="No channels match.">
      <div class="group">
        {% for ch, name in live_channels.items() %}
        <button class="row live" data-kind="live" data-ch="{{ ch }}" data-name="{{ name|e }}">
          <span class="num">{{ ch }}</span><span class="t">{{ name }}</span>
        </button>
        {% endfor %}
      </div>
    </div>

    <div class="head"><h2>Movies</h2><span class="n">{{ counts.MOVIES }}</span></div>
    <div class="sec" data-empty="No movies match.">
      {% for folder, items in library.MOVIES.items() %}
      <div class="group">
        <h3>{{ folder }}</h3>
        {% for item in items %}
        <button class="row" data-kind="file" data-path="{{ item.path|urlencode }}" data-audio="{{ 'y' if item.is_audio else 'n' }}" data-name="{{ item.display_name|e }}">
          <span class="t">{{ item.display_name }}</span>
        </button>
        {% endfor %}
      </div>
      {% else %}
      <p class="empty">Nothing here yet. Drop files into a folder with "movie" in its name.</p>
      {% endfor %}
    </div>
  </aside>

  <main class="stage">
    <div class="frame">
      <video id="player" controls playsinline preload="none"></video>
      <div class="veil" id="veil">
        <span class="eq" id="eq"><i></i><i></i><i></i><i></i><i></i></span>
        <p><strong id="veilTitle">Nothing playing</strong>Pick a channel on the left or a title from either rail.</p>
      </div>
    </div>

    <div class="strip" id="strip">
      <span class="badge"><i></i><span id="src">Standby</span></span>
      <span id="title">Nothing playing</span>
      <span id="mode">Idle</span>
    </div>

    <div class="strip" style="grid-template-columns:auto minmax(0,1fr);">
      <label class="toggle">
        <input type="checkbox" id="up"><span class="track"></span>
        <span>Upscale library video to 1080p on the GPU</span>
      </label>
      <span class="hint">Re-encodes with NVENC. Live tuner channels always upscale.</span>
    </div>
  </main>

  <aside class="rail right">
    <div class="head"><h2>TV series</h2><span class="n">{{ counts.TV_SHOWS }}</span></div>
    <div class="sec" data-empty="No episodes match.">
      {% for folder, items in library.TV_SHOWS.items() %}
      <div class="group">
        <h3>{{ folder }}</h3>
        {% for item in items %}
        <button class="row" data-kind="file" data-path="{{ item.path|urlencode }}" data-audio="{{ 'y' if item.is_audio else 'n' }}" data-name="{{ item.display_name|e }}">
          <span class="t">{{ item.display_name }}</span>
        </button>
        {% endfor %}
      </div>
      {% else %}
      <p class="empty">No shows found. Folders need "tv", "show" or "season" in the path.</p>
      {% endfor %}
    </div>

    <div class="head"><h2>Music</h2><span class="n">{{ counts.MUSIC }}</span></div>
    <div class="sec" data-empty="No tracks match.">
      {% for folder, items in library.MUSIC.items() %}
      <div class="group">
        <h3>{{ folder }}</h3>
        {% for item in items %}
        <button class="row" data-kind="file" data-path="{{ item.path|urlencode }}" data-audio="{{ 'y' if item.is_audio else 'n' }}" data-name="{{ item.display_name|e }}">
          <span class="t">{{ item.display_name }}</span>
        </button>
        {% endfor %}
      </div>
      {% else %}
      <p class="empty">No tracks found.</p>
      {% endfor %}
    </div>
  </aside>

</div>

<script>
var player = document.getElementById('player');
var strip  = document.getElementById('strip');
var veil   = document.getElementById('veil');
var eq     = document.getElementById('eq');
var upBox  = document.getElementById('up');
var q      = document.getElementById('q');
var current = null;

function setVeil(show, heading, body, busy){
  veil.classList.toggle('off', !show);
  eq.classList.toggle('go', !!busy);
  if(show){
    document.getElementById('veilTitle').textContent = heading;
    veil.querySelector('p').lastChild.textContent = body;
  }
}

function mark(el){
  document.querySelectorAll('.row.on').forEach(function(r){ r.classList.remove('on'); });
  if(el) el.classList.add('on');
}

function play(item, el){
  current = item;
  mark(el);
  strip.className = 'strip ' + (item.kind === 'live' ? 'live' : 'file');
  document.getElementById('src').textContent = item.kind === 'live' ? 'Live' : (item.audio ? 'Track' : 'Library');
  document.getElementById('title').textContent = item.name;
  document.getElementById('mode').textContent =
    item.kind === 'live' ? 'Tuning channel ' + item.ch + ', denoised and sharpened to 1080p'
    : item.audio ? 'Transcoding audio to AAC 320k'
    : upBox.checked ? 'Upscaling to 1080p on the GPU'
    : 'Streaming the original video, audio only re-encoded';

  setVeil(true, item.kind === 'live' ? 'Tuning in' : 'Starting', 'ffmpeg is spinning up. This takes a couple of seconds.', true);

  player.src = item.kind === 'live'
    ? '/tuner/' + item.ch
    : '/stream/' + item.path + (item.audio ? '' : '?upscale=' + upBox.checked);
  player.play().catch(function(){});
}

document.addEventListener('click', function(e){
  var el = e.target.closest('.row');
  if(!el) return;
  play({
    kind: el.dataset.kind,
    ch: el.dataset.ch,
    path: el.dataset.path,
    audio: el.dataset.audio === 'y',
    name: el.dataset.name
  }, el);
});

player.addEventListener('playing', function(){
  if(current && current.audio){
    setVeil(true, current.name, 'Audio only. Nothing to show here.', true);
  } else {
    setVeil(false);
  }
});
player.addEventListener('waiting', function(){
  if(current && !current.audio) setVeil(true, 'Buffering', 'Waiting on the stream to catch up.', true);
});
player.addEventListener('error', function(){
  if(!current) return;
  setVeil(true, 'Stream failed', 'ffmpeg stopped or the source is unreachable. Try another title.', false);
  document.getElementById('mode').textContent = 'Stopped';
});

upBox.addEventListener('change', function(){
  if(current && current.kind === 'file' && !current.audio){
    play(current, document.querySelector('.row.on'));
  }
});

q.addEventListener('input', function(){
  var term = q.value.trim().toLowerCase();
  document.querySelectorAll('.sec').forEach(function(sec){
    var shown = 0;
    sec.querySelectorAll('.group').forEach(function(g){
      var hits = 0;
      g.querySelectorAll('.row').forEach(function(r){
        var ok = r.textContent.toLowerCase().indexOf(term) !== -1;
        r.classList.toggle('hide', !ok);
        if(ok) hits++;
      });
      g.classList.toggle('hide', hits === 0);
      shown += hits;
    });
    var note = sec.querySelector('.miss');
    if(shown === 0 && term){
      if(!note){
        note = document.createElement('p');
        note.className = 'empty miss';
        note.textContent = sec.dataset.empty;
        sec.appendChild(note);
      }
      note.classList.remove('hide');
    } else if(note){
      note.classList.add('hide');
    }
  });
});

document.addEventListener('keydown', function(e){
  if(e.key === '/' && document.activeElement !== q){ e.preventDefault(); q.focus(); }
  if(e.key === 'Escape' && document.activeElement === q){ q.value = ''; q.dispatchEvent(new Event('input')); q.blur(); }
});
</script>
</body>
</html>
"""

@app.route('/')
def index():
    lineup = get_live_lineup()
    sorted_lineup = dict(sorted(lineup.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 9999))
    library = get_organized_media()
    counts = {
        "MOVIES": count_items(library["MOVIES"]),
        "TV_SHOWS": count_items(library["TV_SHOWS"]),
        "MUSIC": count_items(library["MUSIC"]),
    }
    return render_template_string(
        INDEX_HTML,
        library=library,
        live_channels=sorted_lineup,
        counts=counts,
        ip=HDHR_IP,
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=LISTENING_PORT, threaded=True)
