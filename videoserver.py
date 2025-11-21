from flask import Flask, render_template_string, request, jsonify
import requests
import math

app = Flask(__name__)

# ==========================================
# GLOBAL SCAN STATUS + MAP
# ==========================================
scanStatus = "idle"
mapping_points = []

# ==========================================
# NODEJS ENDPOINTS
# ==========================================
NODE_BASE = "https://embeddedprogramming-healtheworldserver.up.railway.app"

NODE_UPLOAD = f"{NODE_BASE}/upload_audio"
NODE_CAMERA_ROTATE = f"{NODE_BASE}/camera_rotate"

SCAN_30  = f"{NODE_BASE}/trigger_scan30"
SCAN_45  = f"{NODE_BASE}/trigger_scan45"
SCAN_90  = f"{NODE_BASE}/trigger_scan90"
SCAN_180 = f"{NODE_BASE}/trigger_scan180"
SCAN_360 = f"{NODE_BASE}/trigger_scan"

# ==========================================
# HOME PAGE
# ==========================================
@app.route("/")
def index():

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Matthew Robot — Auto Active Listening + Scan Map</title>

<style>
body {{
    background:#111;
    color:#eee;
    text-align:center;
    font-family:sans-serif;
}}
button {{
    margin:4px;
    padding:10px 15px;
    cursor:pointer;
    border:none;
    border-radius:6px;
}}
#result {{
    background:#222;
    padding:10px;
    margin-top:15px;
    height:120px;
    overflow:auto;
    white-space:pre-wrap;
}}
#mapCanvas {{
    margin-top:20px;
    background:#000;
    border:1px solid #555;
}}
</style>
</head>

<body>

<h2 style="color:#0ff;">Matthew Robot — Auto Active Listening</h2>

<button id="startBtn">Speak</button>
<button id="stopBtn" disabled>Stop</button>
<p id="status">Initializing...</p>

<div id="result"></div>

<h3 style="color:#0af;margin-top:25px;">Camera Control</h3>
<button id="camLeftBtn">Rotate Left +10°</button>
<button id="camRightBtn">Rotate Right +10°</button>
<p id="camAngleStatus">Current Camera Angle: 0°</p>

<h3 style="color:#0f0;margin-top:25px;">Scan Area</h3>
<button onclick="triggerScan('{SCAN_30}','30°')">Scan 30°</button>
<button onclick="triggerScan('{SCAN_45}','45°')">Scan 45°</button>
<button onclick="triggerScan('{SCAN_90}','90°')">Scan 90°</button>
<button onclick="triggerScan('{SCAN_180}','180°')">Scan 180°</button>
<button onclick="triggerScan('{SCAN_360}','360°')">Scan 360°</button>

<button id="showDataBtn" style="background:#ff0;color:#000;margin-top:10px;">
    Show Data & Draw Map
</button>

<canvas id="mapCanvas" width="400" height="400"></canvas>

<script>
/* ================================
   CAMERA ROTATION TO NODEJS SERVER
================================ */
let currentCameraAngle = 0;
let camBusy = false;

function updateCamText() {{
    document.getElementById("camAngleStatus").innerText =
        "Current Camera Angle: " + currentCameraAngle + "°";
}}

async function rotateCamera(dir) {{
    if (camBusy) return alert("WAIT!");

    camBusy = true;

    if (dir === "left") currentCameraAngle += 10;
    if (dir === "right") currentCameraAngle -= 10;

    currentCameraAngle = Math.max(0, Math.min(180, currentCameraAngle));
    updateCamText();

    const url = "{NODE_CAMERA_ROTATE}" + 
                "?direction=" + dir +
                "&angle=" + currentCameraAngle;

    try {{
        await fetch(url);
        console.log("Sent to NodeJS:", url);
    }} catch (e) {{
        alert("Camera rotate failed!");
    }}

    setTimeout(()=> camBusy=false, 1000);
}}

document.getElementById("camLeftBtn").onclick  = ()=> rotateCamera("left");
document.getElementById("camRightBtn").onclick = ()=> rotateCamera("right");

updateCamText();

/* ================================
   TRIGGER SCAN
================================ */
async function triggerScan(url, label) {{
    document.getElementById("status").innerText = "Sending scan " + label;
    await fetch(url);
    await fetch("/set_scanning");
    alert("Robot scanning " + label);
}}

/* ================================
   SHOW MAP
================================ */
document.getElementById("showDataBtn").onclick = async ()=>{{
    let r = await fetch("/get_map");
    let data = await r.json();
    drawMap(data.points || []);
}};

function drawMap(points) {{
    const c = document.getElementById("mapCanvas");
    const ctx = c.getContext("2d");
    ctx.clearRect(0,0,c.width,c.height);
    const cx=c.width/2, cy=c.height/2;

    ctx.fillStyle="#0f0";
    ctx.beginPath();
    ctx.arc(cx,cy,5,0,6.28);
    ctx.fill();

    if (!points.length) {{
        ctx.fillStyle="#fff";
        ctx.fillText("No data", cx-20, cy);
        return;
    }}

    let maxR=1;
    points.forEach(p=> maxR = Math.max(maxR, p.distance_cm));

    let scale = 150 / maxR;
    ctx.fillStyle="#f33";

    points.forEach(p=>{{
        let a = p.angle_deg * Math.PI/180;
        let r = p.distance_cm * scale;
        let x = cx + r * Math.cos(a);
        let y = cy - r * Math.sin(a);
        ctx.fillRect(x-2,y-2,4,4);
    }});
}}

/* ================================
   AUDIO AUTO-LISTENING
================================ */
let mediaStream=null, rec=null, chunks=[];
const TH=50;

async function uploadAudio() {{
    if (!chunks.length) return;
    let blob = new Blob(chunks);
    let fd = new FormData();
    fd.append("audio", blob, "voice.webm");

    document.getElementById("status").innerText="Uploading...";

    let res = await fetch("{NODE_UPLOAD}", {{
        method:"POST",
        body: fd
    }});
    let json = await res.json();

    document.getElementById("result").innerText =
        "Transcript: "+json.transcript+"\\nLabel: "+json.label+"\\nURL: "+json.audio_url;

    if (json.audio_url) {{
        let audio=new Audio(json.audio_url);
        audio.play();
        audio.onended=()=> startAuto();
    }} else {{
        startAuto();
    }}
}}

async function startAuto() {{
    chunks=[];
    if (mediaStream) mediaStream.getTracks().forEach(t=>t.stop());
    mediaStream = await navigator.mediaDevices.getUserMedia({{audio:true}});

    let ctx = new AudioContext();
    let src = ctx.createMediaStreamSource(mediaStream);
    let ana = ctx.createAnalyser();
    src.connect(ana);
    ana.fftSize=1024;
    let buf = new Uint8Array(1024);
    let triggered=false;
    let startTime=0;

    function loop() {{
        ana.getByteTimeDomainData(buf);
        let level=0;
        for (let i=0;i<buf.length;i++)
            level=Math.max(level, Math.abs(buf[i]-128));

        document.getElementById("status").innerText="Listening... lvl="+level;

        if (!triggered && level>=TH) {{
            triggered=true;
            chunks=[];
            rec=new MediaRecorder(mediaStream);
            rec.ondataavailable=e=>chunks.push(e.data);
            rec.onstop=uploadAudio;
            rec.start();
            startTime=Date.now();
        }}

        if (triggered && Date.now()-startTime > 2500) {{
            if (rec && rec.state!=="inactive") rec.stop();
            return;
        }}

        requestAnimationFrame(loop);
    }}

    loop();
}}

document.getElementById("startBtn").onclick=startAuto;
document.getElementById("stopBtn").onclick=()=> rec?.stop();

window.onload=startAuto;

</script>
</body>
</html>
"""

    return render_template_string(html)

# ============================================================
@app.route("/set_scanning")
def set_scanning():
    global scanStatus, mapping_points
    scanStatus = "scanning"
    mapping_points = []
    return {"status":"ok"}

# ============================================================
@app.route("/push_mapping", methods=["POST"])
def push_mapping():
    global mapping_points
    data = request.get_json()
    mapping_points.append({
        "angle_deg": float(data["angle_deg"]),
        "distance_cm": float(data["distance_cm"])
    })
    return {"status":"ok", "count":len(mapping_points)}

# ============================================================
@app.route("/get_map")
def get_map():
    return jsonify({"points": mapping_points})

# ============================================================
# Flask OWN endpoint: not used except debug
@app.route("/camera_rotate")
def cam_rotate_local():
    return {"status": "ignored", "reason": "frontend now calls NodeJS directly"}

# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
