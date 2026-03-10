import os
import subprocess
import requests
from flask import Flask, Response, render_template_string, stream_with_context, jsonify

app = Flask(__name__)

# ====== CONFIGURATION ======
HDHR_IP = "192.168.0.160" 
LISTENING_PORT = 5001                

KNOWN_LABELS = { # Unknown Channels Mapped
    "5003": "VICE", "5004": "SCI", "5051": "ABC East", "5000": "ABC West", 
    "5011": "LMN", "5012": "FXM", "5016": "POP", "5017": "CBS",
    "5014": "POP NETWORK", "5005": "AHC", "5006": "Disney XD", "5008": "LIFE", 
    "5022": "Showtime East", "5029": "FLIX", "5035": "TMC (English)",
    "5038": "TMC (Spanish)", "5044": "Nat Geo WILD", "5047": "BBC",
    "5048": "Sundance TV", "5049": "FIC", "5053": "Fox 23", "53": "FXX", 
}

def get_live_lineup():
    try:
        url = f"http://{HDHR_IP}/lineup.json"
        response = requests.get(url, timeout=5)
        return {str(i['GuideNumber']): KNOWN_LABELS.get(str(i['GuideNumber']), i.get('GuideName', f"Ch {i['GuideNumber']}")) for i in response.json()}
    except:
        return KNOWN_LABELS

INDEX_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>My Home TV Portal</title>
    <style>
        body { background: #0a0a0a; color: #eee; font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; height: 100vh; overflow: hidden; }
        .sidebar { width: 320px; background: #151515; border-right: 1px solid #333; display: flex; flex-direction: column; }
        .sidebar-header { padding: 20px; border-bottom: 1px solid #333; }
        .jump-box { width: 100%; padding: 12px; background: #222; border: 1px solid #444; color: white; border-radius: 4px; box-sizing: border-box; font-size: 16px; margin-top: 10px; }
        .channel-list { flex-grow: 1; overflow-y: auto; padding: 10px; }
        .channel-card { background: #1f1f1f; padding: 15px; margin-bottom: 8px; border-radius: 6px; cursor: pointer; border: 2px solid transparent; }
        .channel-card.active { border-color: #ff0000; background: #333; }
        .main { flex-grow: 1; display: flex; background: #000; position: relative; }
        video { width: 100%; height: 100%; background: #000; }
        .shield-btn { background: #ff0000; color: white; border: none; padding: 10px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 10px; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="sidebar">
        <div class="sidebar-header">
            <h2 style="margin:0; color: #ff0000;">LIVE TV</h2>
            <input type="text" id="channelJump" class="jump-box" placeholder="Enter Channel #..." onkeypress="handleKeyPress(event)">
            <button class="shield-btn" onclick="toggleFullScreen()">FULLSCREEN (F)</button>
        </div>
        <div class="channel-list">
            {% for ch, name in channels.items() %}
            <div class="channel-card" id="card-{{ ch }}" onclick="playChannel('{{ ch }}', this)">
                <span style="font-weight:bold; display:block;">{{ name }}</span>
                <span style="color:#777; font-size:12px;">Channel {{ ch }}</span>
            </div>
            {% endfor %}
        </div>
    </div>
    <div class="main" id="v-scope">
        <video id="player" controls autoplay></video>
    </div>
    <script>
        function toggleFullScreen() {
            const scope = document.getElementById('v-scope');
            if (!document.fullscreenElement) { scope.requestFullscreen(); } 
            else { document.exitFullscreen(); }
        }
        function handleKeyPress(e) {
            if (e.key === 'Enter') {
                const val = document.getElementById('channelJump').value.trim();
                const card = document.getElementById('card-' + val);
                if (card) { playChannel(val, card); card.scrollIntoView(); }
            }
        }
        function playChannel(ch, element) {
            const player = document.getElementById('player');
            document.querySelectorAll('.channel-card').forEach(c => c.classList.remove('active'));
            element.classList.add('active');
            player.src = "/tuner/" + ch;
            player.play();
        }
    </script>
</body>
</html>
"""

@app.route('/tuner/<channel>')
def tuner(channel):
    target_url = f"http://{HDHR_IP}:5004/auto/v{channel}"
    
    # We use libx264 for universal compatibility
    # and "frag_keyframe" to make the MP4 streamable
    ffmpeg_cmd = [
        'ffmpeg', '-i', target_url,
        '-vf', 'scale=-1:1080,hqdn3d=1.5:1.5:6:6,unsharp=3:3:0.5:3:3:0.5',
        '-c:v', 'libx265', '-preset', 'ultrafast', '-tune', 'zerolatency',
        '-crf', '20', '-c:a', 'aac', '-b:a', '192k',
        '-f', 'mp4', 
        '-movflags', 'separate_moof+frag_keyframe+empty_moov+default_base_moof',
        'pipe:1'
    ]
    
    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    
    def generate():
        try:
            while True:
                chunk = process.stdout.read(1024*64)
                if not chunk: break
                yield chunk
        finally:
            process.kill()
            
    # 'video/mp4' is the most "standard" thing on earth
    resp = Response(stream_with_context(generate()), mimetype='video/mp4')
    resp.headers.add('Access-Control-Allow-Private-Network', 'true')
    resp.headers.add('Access-Control-Allow-Origin', '*')
    return resp

@app.route('/')
def index():
    full_lineup = get_live_lineup()
    sorted_lineup = dict(sorted(full_lineup.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0))
    return render_template_string(INDEX_HTML, channels=sorted_lineup)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=LISTENING_PORT)