from flask import Flask, request, jsonify
import requests
import math

app = Flask(__name__)

# ==========================================
# GLOBAL SCAN STATUS + MAP DATA
# ==========================================
scanStatus = "idle"
mapping_points = []

# ==========================================
# NODEJS ENDPOINTS
# ==========================================
NODEJS_BASE = "https://embeddedprogramming-healtheworldserver.up.railway.app"

NODE_UPLOAD = f"{NODEJS_BASE}/upload_audio"
NODE_CAMERA = f"{NODEJS_BASE}/camera_rotate"

SCAN30  = f"{NODEJS_BASE}/trigger_scan30"
SCAN45  = f"{NODEJS_BASE}/trigger_scan45"
SCAN90  = f"{NODEJS_BASE}/trigger_scan90"
SCAN180 = f"{NODEJS_BASE}/trigger_scan180"
SCAN360 = f"{NODEJS_BASE}/trigger_scan"

# ==========================================
# HTML PAGE
# ==========================================
@app.route("/")
def index():
    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Matthew Robot — Active Listening + Scan + Camera</title>

<style>
body {{
    background:#111;
    color:#eee;
    font-family:sans-serif;
    text-align:center;
    padding:20px;
}}
button {{
    padding:10px 20px;
    margin:5px;
    border:none;
    border-radius:6px;
    cursor:pointer;
    font-size:15px;
}}
#result {{
    text-align:left;
    background:#222;
    padding:15px;
    margin-top:20px;
    border-radius:8px;
    min-height:70px;
    max-height:200px;
    overflow:auto;
    white-space:pre-wrap;
    font-size:12px;
}}
#camControl button {{
    background:#09f;
    color:#000;
    font-weight:bold;
}}
#scanButtons button {{
    background:#0f0;
    color:#000;
    font-weight:bold;
}}
</style>
</head>

<body>

<h2 style='color:#0ff;'>Matthew Robot — Auto Active Listening</h2>

<div>
    <button id="startBtn">Speak</button>
    <button id="stopBtn" disabled>Stop</button>
</div>

<p id="status">Loading microphone...</p>

<div id="result"></div>

<!-- CAMERA CONTROL -->
<h3 style='color:#0af;'>Camera Rotate</h3>
<div id="camControl">
    <button id="camLeft20">◀ Rotate Left 20°</button>
    <button id="camRight20">Rotate Right 20° ▶</button>
</div>
<p id="camAngleStatus">Camera ready</p>

<!-- SCAN -->
<h3 style='color:#0f0;'>Scan Environment</h3>
<div id="scanButtons">
      <button onclick="triggerScan('{SCAN30}', '30°')">Scan 30°</button>
      <button onclick="triggerScan('{SCAN45}', '45°')">Scan 45°</button>
      <button onclick="triggerScan('{SCAN90}', '90°')">Scan 90°</button>
      <button onclick="triggerScan('{SCAN180}', '180°')">Scan 180°</button>
      <button onclick="triggerScan('{SCAN360}', '360°')">Scan 360°</button>
</div>

<button id="showDataBtn" style="background:#ff0;color:#000;">Show Map</button>
<canvas id="mapCanvas" width="400" height="400" style="background:#000;margin-top:15px;"></canvas>


<script>
/* ==========================================================
    FIXED CAMERA ROTATE
========================================================== */
async function sendCamera(angle) {{
    try {{
        let url = "{NODE_CAMERA}?angle=" + angle;
        const r = await fetch(url);
        const js = await r.json();
        document.getElementById("camAngleStatus").innerText =
            "Sent angle " + angle + "° → " + js.status;
    }} catch (e) {{
        document.getElementById("camAngleStatus").innerText =
            "Error: " + e;
    }}
}}

document.getElementById("camLeft20").onclick = () => sendCamera(20);
document.getElementById("camRight20").onclick = () => sendCamera(160);


/* ==========================================================
    SCAN BUTTONS
========================================================== */
async function triggerScan(url, label) {{
    document.getElementById("status").innerText = "Sending scan " + label;
    await fetch(url);
    await fetch("/set_scanning");
}}

/* ==========================================================
    SHOW MAP
========================================================== */
document.getElementById("showDataBtn").onclick = async () => {{
    const r = await fetch("/get_map");
    const js = await r.json();
    drawMap(js.points);
}};

function drawMap(points) {{
    const c = document.getElementById("mapCanvas");
    const ctx = c.getContext("2d");
    ctx.clearRect(0,0,c.width,c.height);

    const cx = c.width/2, cy = c.height/2;

    ctx.fillStyle="#0f0";
    ctx.beginPath();
    ctx.arc(cx,cy,5,0,Math.PI*2);
    ctx.fill();

    if (!points.length) return;

    const maxR = Math.max(...points.map(p => p.distance_cm));
    const scale = 160 / maxR;

    ctx.fillStyle="#f44";
    points.forEach(p => {{
        const rad = p.angle_deg * Math.PI / 180;
        const r = p.distance_cm * scale;
        const x = cx + Math.cos(rad)*r;
        const y = cy - Math.sin(rad)*r;
        ctx.fillRect(x-2,y-2,4,4);
    }});
}};


/* ==========================================================
    ACTIVE LISTENING (KEEP OLD CODE)
========================================================== */
let manualStream=null, mediaRecorder=null, audioChunks=[];
let listenStream=null, audioCtx=null, source=null, analyser=null;
let rafId=null, activeRecorder=null;

function clearCache(){{
    if (rafId) cancelAnimationFrame(rafId);
    if (activeRecorder && activeRecorder.state!=="inactive") activeRecorder.stop();
    if (listenStream) listenStream.getTracks().forEach(t=>t.stop());
    if (audioCtx) audioCtx.close();
}}

async function startRecordingManual(){{
    manualStream=await navigator.mediaDevices.getUserMedia({audio:true});
    audioChunks=[];
    mediaRecorder=new MediaRecorder(manualStream);

    mediaRecorder.ondataavailable=e=>{{ if(e.data.size>0) audioChunks.push(e.data); }};
    mediaRecorder.onstop=()=>{{ manualStream.getTracks().forEach(t=>t.stop()); uploadAudio(); }};

    mediaRecorder.start();

    document.getElementById("status").innerText="Recording...";
    document.getElementById("startBtn").disabled=true;
    document.getElementById("stopBtn").disabled=false;
}}

function stopRecordingManual(){{
    if(mediaRecorder && mediaRecorder.state!=="inactive") mediaRecorder.stop();
    document.getElementById("status").innerText="Processing...";
    document.getElementById("startBtn").disabled=false;
    document.getElementById("stopBtn").disabled=true;
}}

document.getElementById("startBtn").onclick=startRecordingManual;
document.getElementById("stopBtn").onclick=stopRecordingManual;

const thresholdAmp = 50;

/* AUTO LISTENING */
async function startAutoListening(){{
    clearCache();

    try {{
        listenStream=await navigator.mediaDevices.getUserMedia({audio:true});
    }} catch(e) {{
        document.getElementById("status").innerText="Mic error";
        return;
    }}

    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    audioCtx=new AudioCtx();
    source=audioCtx.createMediaStreamSource(listenStream);
    analyser=audioCtx.createAnalyser();
    analyser.fftSize=1024;
    source.connect(analyser);

    const data=new Uint8Array(analyser.fftSize);
    let triggered=false;
    let recordStart=0;

    function loop(){{
        analyser.getByteTimeDomainData(data);
        let maxAmp=0;
        for(let i=0;i<data.length;i++) maxAmp=Math.max(maxAmp, Math.abs(data[i]-128));

        if(!triggered && maxAmp>=thresholdAmp){{
            triggered=true;
            audioChunks=[];
            activeRecorder=new MediaRecorder(listenStream);
            activeRecorder.ondataavailable=e=>{{ if(e.data.size>0) audioChunks.push(e.data); }};
            activeRecorder.onstop=()=> uploadAudio(maxAmp);
            activeRecorder.start();
            recordStart=Date.now();
        }}

        if(triggered && (Date.now()-recordStart>=2500)){{
            activeRecorder.stop();
            return;
        }}

        rafId=requestAnimationFrame(loop);
    }}

    loop();
}}

window.onload=startAutoListening;


/* ==========================================================
    SEND AUDIO TO NODE SERVER
========================================================== */
async function uploadAudio(level=0){{
    if(!audioChunks.length){{
        document.getElementById("status").innerText="No audio";
        return;
    }}

    const blob=new Blob(audioChunks);
    const form=new FormData();
    form.append("audio", blob, "voice.webm");

    document.getElementById("status").innerText="Uploading...";

    try {{
        const res=await fetch("{NODE_UPLOAD}", {{method:"POST", body:form}});
        const js=await res.json();

        document.getElementById("result").innerText =
            "Level: " + level + "\\n" +
            "Transcript: " + js.transcript + "\\n" +
            "Label: " + js.label + "\\n" +
            "Audio URL: " + js.audio_url;

        const audio=new Audio(js.audio_url);
        audio.play();

        setTimeout(startAutoListening, 3000);

    }} catch(e) {{
        document.getElementById("status").innerText="Upload error " + e;
    }}
}}
</script>

</body>
</html>
"""
    return html


# ==========================================
# BACKEND SCAN HANDLERS
# ==========================================
@app.route("/set_scanning")
def set_scanning():
    global scanStatus, mapping_points
    scanStatus = "scanning"
    mapping_points = []
    return {"status": "ok"}

@app.route("/push_mapping", methods=["POST"])
def push_mapping():
    global mapping_points
    data = request.get_json(force=True)
    mapping_points.append({
        "angle_deg": float(data["angle_deg"]),
        "distance_cm": float(data["distance_cm"])
    })
    return {"status": "ok"}

@app.route("/get_map")
def get_map():
    return jsonify({"points": mapping_points})

# ==========================================
# RUN
# ==========================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
