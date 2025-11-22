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
# HOME PAGE — NO F-STRING HERE
# ==========================================
@app.route("/")
def index():

    html = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Matthew Robot — Active Listening + Scan Map</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">

  <style>
    body { background:#111; color:#eee; font-family:sans-serif; text-align:center; padding:20px; }
    button { padding:10px 18px; margin:5px; border:none; border-radius:6px; cursor:pointer; font-size:15px; }
    #result { text-align:left; background:#222; padding:15px; margin-top:20px; border-radius:8px;
              min-height:70px; max-height:200px; overflow:auto; white-space:pre-wrap; font-size:12px; }
    #camControl button { background:#09f; color:#000; font-weight:bold; }
    #scanButtons button { background:#0f0; color:#000; font-weight:bold; }
  </style>
</head>

<body>
  <h2 style='color:#0ff;'>Matthew Robot — Auto Active Listening</h2>

  <div>
    <button id="startBtn">Speak</button>
    <button id="stopBtn" disabled>Stop</button>
  </div>

  <p id="status">Initializing microphone...</p>
  <div id="result"></div>

  <!-- CAMERA -->
  <h3 style='color:#0af;'>Camera Servo Control</h3>

  <div id="camControl">
      <button id="camLeft20">Rotate Left 20°</button>
      <button id="camRight20">Rotate Right 20°</button>
  </div>

  <p id="camAngleStatus">Camera rotation commands ready</p>

  <!-- SCAN BUTTONS -->
  <h3 style='color:#0f0;'>Scan Environment</h3>

  <div id="scanButtons">
      <button onclick="triggerScan('%%SCAN30%%', '30°')">Scan 30°</button>
      <button onclick="triggerScan('%%SCAN45%%', '45°')">Scan 45°</button>
      <button onclick="triggerScan('%%SCAN90%%', '90°')">Scan 90°</button>
      <button onclick="triggerScan('%%SCAN180%%', '180°')">Scan 180°</button>
      <button onclick="triggerScan('%%SCAN360%%', '360°')">Scan 360°</button>
  </div>

  <br>
  <button id="showDataBtn" style="background:#ff0;color:#000;">Show Map</button>

  <canvas id="mapCanvas" width="400" height="400" style="background:#000;margin-top:15px;"></canvas>


<script>
/* CAMERA ROTATION */
document.getElementById("camLeft20").onclick = async () => {
    const res = await fetch("%%NODE_CAMERA%%?direction=left&angle=20");
    const js = await res.json();
    document.getElementById("camAngleStatus").innerText =
        "Sent: LEFT 20° → " + js.status;
};

document.getElementById("camRight20").onclick = async () => {
    const res = await fetch("%%NODE_CAMERA%%?direction=right&angle=20");
    const js = await res.json();
    document.getElementById("camAngleStatus").innerText =
        "Sent: RIGHT 20° → " + js.status;
};


/* SCAN */
async function triggerScan(url, label) {
    document.getElementById("status").innerText = "Sending scan " + label + "...";
    await fetch(url);
    await fetch("/set_scanning");
}


/* SHOW MAP */
document.getElementById("showDataBtn").onclick = async () => {
    const r = await fetch("/get_map");
    const js = await r.json();
    drawMap(js.points);
};

function drawMap(points) {
    const c = document.getElementById("mapCanvas");
    const ctx = c.getContext("2d");
    ctx.clearRect(0,0,c.width,c.height);

    const cx = c.width/2;
    const cy = c.height/2;

    ctx.fillStyle="#0f0";
    ctx.beginPath();
    ctx.arc(cx,cy,5,0,Math.PI*2);
    ctx.fill();

    if (!points.length) return;

    let maxR = Math.max(...points.map(p => p.distance_cm));
    const scale = 160 / maxR;

    ctx.fillStyle="#f44";
    points.forEach(p => {
        const rad = p.angle_deg * Math.PI/180;
        const r = p.distance_cm * scale;
        const x = cx + Math.cos(rad)*r;
        const y = cy - Math.sin(rad)*r;
        ctx.fillRect(x-2,y-2,4,4);
    });
}
</script>

</body>
</html>
"""

    # SAFE VARIABLE INSERTION
    html = html.replace("%%NODE_CAMERA%%", NODE_CAMERA)
    html = html.replace("%%SCAN30%%", SCAN30)
    html = html.replace("%%SCAN45%%", SCAN45)
    html = html.replace("%%SCAN90%%", SCAN90)
    html = html.replace("%%SCAN180%%", SCAN180)
    html = html.replace("%%SCAN360%%", SCAN360)

    return html


# ==========================================
# BACKEND SCAN HANDLERS
# ==========================================
@app.route("/scan_done", methods=["POST"])
def scan_done():
    global scanStatus
    scanStatus = "done"
    return {"status": "ok"}


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
# RUN SERVER
# ==========================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
