from flask import Flask, render_template_string, request, jsonify
import requests
import math

app = Flask(__name__)

# ==========================================
# GLOBAL SCAN STATUS + MAP DATA
# ==========================================
scanStatus = "idle"   # idle | scanning | done
mapping_points = []   # lưu các điểm {angle_deg, distance_cm}

# ==========================================
# NODEJS ENDPOINTS
# ==========================================
NODEJS_UPLOAD_URL = "https://embeddedprogramming-healtheworldserver.up.railway.app/upload_audio"

NODEJS_SCAN_30   = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan30"
NODEJS_SCAN_45   = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan45"
NODEJS_SCAN_90   = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan90"
NODEJS_SCAN_180  = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan180"
NODEJS_SCAN_360  = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan"

# ==========================================
# HOME PAGE
# ==========================================
@app.route("/")
def index():
    html = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Matthew Robot — Auto Active Listening + Scan Map</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {{
      background:#111;
      color:#eee;
      font-family:sans-serif;
      text-align:center;
      padding:20px;
    }}

    h2 {{ color:#0ff; }}
    button {{
      margin:5px;
      padding:10px 18px;
      font-size:15px;
      border:none;
      border-radius:6px;
      cursor:pointer;
    }}

    #scanButtons button {{
      background:#0f0;
      color:#000;
      font-weight:bold;
    }}

    #showDataBtn {{
      background:#ff0;
      color:#000;
      font-weight:bold;
      margin-top:10px;
    }}

    #status {{
      margin-top:15px;
      font-weight:bold;
    }}

    #result {{
      margin-top:20px;
      padding:15px;
      border-radius:8px;
      background:#222;
      min-height:70px;
      text-align:left;
      white-space:pre-wrap;
      max-height:200px;
      overflow:auto;
      font-size:12px;
    }}

    #mapCanvas {{
      margin-top:25px;
      background:#000;
      border:1px solid #555;
    }}

    #camAngleStatus {{
      margin-top:10px;
      color:#0af;
      font-weight:bold;
    }}

    #camControl button {{
      background:#09f;
      color:#000;
      font-weight:bold;
      padding:10px 20px;
    }}
  </style>
</head>

<body>
  <h2>Matthew Robot — Auto Active Listening</h2>

  <div>
    <button id="startBtn">Speak</button>
    <button id="stopBtn" disabled>Stop</button>
  </div>

  <p id="status">Initializing microphone...</p>
  <div id="result"></div>

  <!-- CAMERA CONTROL -->
  <h3 style="margin-top:30px; color:#0af;">Camera Servo Control</h3>

  <div id="camControl">
      <button id="camLeftBtn">Rotate Left +10°</button>
      <button id="camRightBtn">Rotate Right +10°</button>
  </div>

  <p id="camAngleStatus">Current Camera Angle: 0°</p>

  <!-- ============ SCAN BUTTONS ============ -->
  <h3 style="margin-top:30px; color:#0f0;">Scan Environment</h3>

  <div id="scanButtons">
      <button onclick="triggerScan('{NODEJS_SCAN_30}', '30°')">Scan 30°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_45}', '45°')">Scan 45°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_90}', '90°')">Scan 90°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_180}', '180°')">Scan 180°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_360}', '360°')">Scan 360°</button>
  </div>

  <!-- SHOW DATA + MAP -->
  <button id="showDataBtn">Show Data & Draw Map</button>
  <canvas id="mapCanvas" width="400" height="400"></canvas>



<script>
/* ==========================================================
   CAMERA ROTATE CONTROL (NEW)
========================================================== */

let currentCameraAngle = 0;
let isCameraBusy = false;

function updateCamStatus() {
    document.getElementById("camAngleStatus").innerText =
        "Current Camera Angle: " + currentCameraAngle + "°";
}

async function rotateCamera(direction) {
    if (isCameraBusy) {
        alert("Please wait 1 second before clicking again!");
        return;
    }
    isCameraBusy = true;

    if (direction === "left")  currentCameraAngle += 10;
    if (direction === "right") currentCameraAngle -= 10;

    currentCameraAngle = Math.max(0, Math.min(180, currentCameraAngle));
    updateCamStatus();

    const url = `/camera_rotate?direction=${direction}&angle=${currentCameraAngle}`;

    try {
        await fetch(url);
        console.log("Camera rotated:", direction, currentCameraAngle);
    } catch (e) {
        alert("Camera rotate failed!");
    }

    setTimeout(() => isCameraBusy = false, 1000);
}

document.getElementById("camLeftBtn").onclick = () => rotateCamera("left");
document.getElementById("camRightBtn").onclick = () => rotateCamera("right");

updateCamStatus();



/* ==========================================================
   SCAN COMMANDS
========================================================== */
async function triggerScan(url, label) {
    document.getElementById("status").innerText =
        "Sending scan request " + label + "...";

    try {
        await fetch(url);
        await fetch("/set_scanning");
        alert("Robot scanning " + label);
    } catch (e) {
        alert("Cannot send scan command!");
    }
}

/* ==========================================================
   SHOW MAP
========================================================== */
document.getElementById("showDataBtn").onclick = async () => {
    try {
        const res = await fetch("/get_map");
        const data = await res.json();
        drawMap(data.points || []);
    } catch (e) {
        alert("Cannot load map!");
    }
};

function drawMap(points) {
    const c = document.getElementById("mapCanvas");
    const ctx = c.getContext("2d");

    ctx.clearRect(0, 0, c.width, c.height);

    const cx = c.width / 2;
    const cy = c.height / 2;

    ctx.fillStyle = "#0f0";
    ctx.beginPath();
    ctx.arc(cx, cy, 5, 0, Math.PI * 2);
    ctx.fill();

    if (!points.length) {
        ctx.fillStyle = "#fff";
        ctx.fillText("No points yet", cx - 40, cy);
        return;
    }

    let maxR = 1;
    points.forEach(p => {
        const d = p.distance_cm || 0;
        if (d > maxR) maxR = d;
    });

    const maxRadiusPx = 160;
    const scale = maxRadiusPx / maxR;

    ctx.fillStyle = "#f44";
    points.forEach(p => {
        const angle = p.angle_deg * Math.PI/180;
        const r = p.distance_cm * scale;
        const x = cx + r * Math.cos(angle);
        const y = cy - r * Math.sin(angle);
        ctx.fillRect(x-2, y-2, 4, 4);
    });

    ctx.strokeStyle = "#444";
    ctx.beginPath();
    ctx.arc(cx, cy, maxRadiusPx, 0, Math.PI*2);
    ctx.stroke();
}


/* ==========================================================
   AUDIO ENGINE (KEEP SAME)
========================================================== */

let manualStream = null;
let mediaRecorder = null;
let audioChunks = [];
let botCallCount = 0;

let listenStream = null;
let audioCtx = null;
let source = null;
let analyser = null;
let rafId = null;
let activeRecorder = null;

function clearCache() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = null;

  if (activeRecorder && activeRecorder.state !== "inactive") {
    try { activeRecorder.stop(); } catch(e){}
  }
  activeRecorder = null;

  if (listenStream) listenStream.getTracks().forEach(t => t.stop());
  listenStream = null;

  if (audioCtx) {
    try { audioCtx.close(); } catch(e){}
  }
  audioCtx = null;
  source = null;
  analyser = null;
  audioChunks = [];
}

async function startRecordingManual() {
  manualStream = await navigator.mediaDevices.getUserMedia({audio:true});
  audioChunks = [];
  mediaRecorder = new MediaRecorder(manualStream);

  mediaRecorder.ondataavailable = e => {
    if (e.data.size > 0) audioChunks.push(e.data);
  };

  mediaRecorder.onstop = () => {
    manualStream.getTracks().forEach(t => t.stop());
    uploadAudio();
  };

  mediaRecorder.start();

  document.getElementById("status").innerText = "Recording (manual)...";
  document.getElementById("startBtn").disabled = true;
  document.getElementById("stopBtn").disabled = false;
}

function stopRecordingManual() {
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  document.getElementById("status").innerText = "Processing (manual)...";
  document.getElementById("startBtn").disabled = false;
  document.getElementById("stopBtn").disabled = true;
}

document.getElementById("startBtn").onclick = startRecordingManual;
document.getElementById("stopBtn").onclick  = stopRecordingManual;

const thresholdAmp = 50;

async function startAutoListening() {
  clearCache();
  try {
    listenStream = await navigator.mediaDevices.getUserMedia({audio:true});
  } catch(e) {
    document.getElementById("status").innerText = "Cannot access microphone";
    return;
  }

  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  audioCtx = new AudioCtx();

  source = audioCtx.createMediaStreamSource(listenStream);
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);

  const data = new Uint8Array(analyser.fftSize);

  let triggered = false;
  let recordStart = 0;
  let lastTriggeredLevel = 0;

  function startAutoRecord() {
    if (triggered) return;
    triggered = true;

    audioChunks = [];
    activeRecorder = new MediaRecorder(listenStream);

    activeRecorder.ondataavailable = e => {
      if (e.data.size > 0) audioChunks.push(e.data);
    };
    activeRecorder.onstop = () => {
      uploadAudio(lastTriggeredLevel);
    };
    activeRecorder.start();
    recordStart = Date.now();
  }

  function loop() {
    analyser.getByteTimeDomainData(data);
    let maxAmp = 0;

    for (let i=0; i<data.length; i++) {
      let amp = Math.abs(data[i] - 128);
      if (amp > maxAmp) maxAmp = amp;
    }

    document.getElementById("status").innerText =
      "Listening... Level=" + maxAmp + " (threshold=50)";

    if (!triggered && maxAmp >= thresholdAmp) {
      lastTriggeredLevel = maxAmp;
      startAutoRecord();
    }

    if (triggered && (Date.now() - recordStart >= 2500)) {
      if (activeRecorder && activeRecorder.state !== "inactive") {
        activeRecorder.stop();
      }
      return;
    }

    rafId = requestAnimationFrame(loop);
  }

  loop();
}

window.onload = startAutoListening;


async function uploadAudio(triggerLevel = 0) {
  if (!audioChunks.length) {
    document.getElementById("status").innerText = "No audio data.";
    return;
  }

  const blob = new Blob(audioChunks);
  const form = new FormData();
  form.append("audio", blob, "voice.webm");

  document.getElementById("status").innerText = "Uploading...";

  try {
    const res = await fetch("{NODEJS_UPLOAD_URL}", {
      method: "POST",
      body: form
    });
    const json = await res.json();

    const audioUrl = json.audio_url;

    document.getElementById("result").innerText =
      "Trigger Level: " + triggerLevel + "\\n" +
      "Transcript: " + (json.transcript || "") + "\\n" +
      "Label: " + (json.label || "") + "\\n" +
      "Audio URL: " + (audioUrl || "");

    clearCache();
    document.getElementById("status").innerText = "Robot speaking...";

    if (audioUrl) {
      const audio = new Audio(audioUrl);

      audio.onloadedmetadata = () => {
        const durationMs = audio.duration * 1000;
        audio.play();

        const waitTime = durationMs + 2000;

        setTimeout(() => {
          document.getElementById("status").innerText = "Restarting auto listening...";
          startAutoListening();
        }, waitTime);
      };
    } else {
      setTimeout(startAutoListening, 800);
    }

  } catch (err) {
    document.getElementById("status").innerText = "Upload error: " + err;
  }
}
</script>

</body>
</html>
    """
    return render_template_string(html)



# ============================================================
# ROBOT REPORTS SCAN DONE
# ============================================================
@app.route("/scan_done", methods=["POST"])
def scan_done():
    global scanStatus
    print("📩 Robot reported scan completed.")
    scanStatus = "done"
    return {"status": "ok", "scanStatus": scanStatus}

# ============================================================
# NODEJS tells us that a scan has started
# ============================================================
@app.route("/set_scanning")
def set_scanning():
    global scanStatus, mapping_points
    scanStatus = "scanning"
    mapping_points = []  # clear old map
    print("⚡ Scan started → mapping_points cleared")
    return {"status": "ok", "scanStatus": scanStatus}

# ============================================================
# Client pushes mapping points to server
# ============================================================
@app.route("/push_mapping", methods=["POST"])
def push_mapping():
    global mapping_points
    try:
        data = request.get_json(force=True) or {}
        angle_deg = float(data.get("angle_deg", 0))
        distance_cm = float(data.get("distance_cm", 0))

        mapping_points.append({
            "angle_deg": angle_deg,
            "distance_cm": distance_cm
        })

        print(f"➕ Add point angle={angle_deg}°, dist={distance_cm}cm "
              f"(total={len(mapping_points)})")

        return jsonify({"status": "ok", "count": len(mapping_points)})
    except Exception as e:
        print("❌ push_mapping error:", e)
        return jsonify({"status": "error", "message": str(e)}), 400

# ============================================================
# get scanning status
# ============================================================
@app.route("/get_scanningstatus")
def get_scanningstatus():
    return {"scanStatus": scanStatus}

# ============================================================
# get map data
# ============================================================
@app.route("/get_map")
def get_map():
    return jsonify({"points": mapping_points})

# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
