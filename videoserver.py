from flask import Flask, render_template_string, request
import requests

app = Flask(__name__)

# ==========================================
# GLOBAL SCAN STATUS + MAPPING DATA
# ==========================================
scanStatus = "idle"   # idle | scanning | done
mapping_points = []   # sẽ chứa các point cảm biến gửi lên


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
    html = f"""
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

    #startBtn {{ background:#0af; color:#000; }}
    #stopBtn  {{ background:#f44; color:#000; }}

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
      max-height:250px;
      overflow:auto;
      font-size:13px;
    }}

    #mapCanvas {{
      margin-top:25px;
      background:#000;
      border:1px solid #555;
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

  <!-- ============ SCAN BUTTONS ============ -->
  <h3 style="margin-top:30px; color:#0f0;">Scan Environment</h3>

  <div id="scanButtons">
      <button onclick="triggerScan('{NODEJS_SCAN_30}', '30°')">Scan 30°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_45}', '45°')">Scan 45°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_90}', '90°')">Scan 90°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_180}', '180°')">Scan 180°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_360}', '360°')">Scan 360°</button>
  </div>

  <!-- NÚT SHOW DATA -->
  <button id="showDataBtn">Show Data & Draw Map</button>

  <canvas id="mapCanvas" width="400" height="400"></canvas>

  <script>
    /* ================================
       SEND SCAN COMMAND TO NODEJS
    ================================ */
    async function triggerScan(url, label) {{
        document.getElementById("status").innerText =
            "Sending scan request " + label + " ...";

        try {{
            await fetch(url, {{ method:"GET" }});
            await fetch("/set_scanning");  // tell flask we are scanning
            alert("Robot is scanning " + label);
        }} catch (e) {{
            alert("Cannot send scan command!");
        }}
    }}


    /* ================================
       SHOW DATA + DRAW MAP 2D
    ================================ */
    document.getElementById("showDataBtn").onclick = loadAndDrawMap;

    async function loadAndDrawMap() {{
      document.getElementById("status").innerText = "Loading mapping data...";
      try {{
        const res = await fetch("/get_map");
        const json = await res.json();
        const points = json.points || [];

        // Hiển thị raw data
        document.getElementById("result").innerText =
          "Mapping points (" + points.length + "):\\n" +
          JSON.stringify(points, null, 2);

        // Vẽ map
        drawMap(points);
        document.getElementById("status").innerText = "Map updated from sensor data.";

      }} catch (e) {{
        document.getElementById("status").innerText = "Error loading map: " + e;
      }}
    }}

    function drawMap(points) {{
      const canvas = document.getElementById("mapCanvas");
      const ctx = canvas.getContext("2d");
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;

      // nền
      ctx.fillStyle = "#000";
      ctx.fillRect(0, 0, canvas.width, canvas.height);

      // robot ở giữa
      ctx.fillStyle = "#0f0";
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, Math.PI * 2);
      ctx.fill();

      // scale: 1m = 50px, nếu distanceCm
      const SCALE_PER_M = 50;

      ctx.fillStyle = "#f44";

      points.forEach(p => {{
        let x = 0;
        let y = 0;

        // Nếu server đã có x,y dạng mét
        if (p.x !== undefined && p.y !== undefined) {{
          x = p.x;       // mét
          y = p.y;       // mét
        }}
        // Nếu chỉ có angle + distance cm → convert sang (x,y)
        else if (p.angle !== undefined && p.distance !== undefined) {{
          const angleRad = p.angle * Math.PI / 180.0;
          const distM = p.distance / 100.0;  // cm → m
          x = distM * Math.cos(angleRad);
          y = distM * Math.sin(angleRad);
        }} else {{
          // không đủ data
          return;
        }}

        const px = cx + x * SCALE_PER_M;
        const py = cy - y * SCALE_PER_M;

        ctx.fillRect(px - 1, py - 1, 3, 3);
      }});
    }}


    /* ============================================
       AUDIO ENGINE — GIỮ NGUYÊN
    ============================================ */

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

    function clearCache() {{
      if (rafId) cancelAnimationFrame(rafId);
      rafId = null;

      if (activeRecorder && activeRecorder.state !== "inactive") {{
        try {{ activeRecorder.stop(); }} catch(e){{}}
      }}
      activeRecorder = null;

      if (listenStream) listenStream.getTracks().forEach(t => t.stop());
      listenStream = null;

      if (audioCtx) {{
        try {{ audioCtx.close(); }} catch(e){{}}
      }}
      audioCtx = null;

      source = null;
      analyser = null;
      audioChunks = [];
    }}


    async function startRecordingManual() {{
      manualStream = await navigator.mediaDevices.getUserMedia({{ audio:true }});
      audioChunks = [];
      mediaRecorder = new MediaRecorder(manualStream);

      mediaRecorder.ondataavailable = e => {{
        if (e.data.size > 0) audioChunks.push(e.data);
      }};

      mediaRecorder.onstop = () => {{
        manualStream.getTracks().forEach(t => t.stop());
        uploadAudio();
      }};

      mediaRecorder.start();

      document.getElementById("status").innerText = "Recording (manual)...";
      document.getElementById("startBtn").disabled = true;
      document.getElementById("stopBtn").disabled = false;
    }}

    function stopRecordingManual() {{
      if (mediaRecorder && mediaRecorder.state !== "inactive") {{
        mediaRecorder.stop();
      }}
      document.getElementById("status").innerText = "Processing (manual)...";
      document.getElementById("startBtn").disabled = false;
      document.getElementById("stopBtn").disabled = true;
    }}

    document.getElementById("startBtn").onclick = startRecordingManual;
    document.getElementById("stopBtn").onclick  = stopRecordingManual;


    /* ============================
       AUTO LISTENING
    ============================ */
    const thresholdAmp = 50;

    async function startAutoListening() {{
      clearCache();
      try {{
        listenStream = await navigator.mediaDevices.getUserMedia({{ audio:true }});
      }} catch(e) {{
        document.getElementById("status").innerText = "Cannot access microphone";
        return;
      }}

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

      function startAutoRecord() {{
        if (triggered) return;
        triggered = true;

        audioChunks = [];
        activeRecorder = new MediaRecorder(listenStream);

        activeRecorder.ondataavailable = e => {{
          if (e.data.size > 0) audioChunks.push(e.data);
        }};
        activeRecorder.onstop = () => {{
          uploadAudio(lastTriggeredLevel);
        }};
        activeRecorder.start();
        recordStart = Date.now();
      }}

      function loop() {{
        analyser.getByteTimeDomainData(data);
        let maxAmp = 0;

        for (let i=0; i<data.length; i++) {{
          let amp = Math.abs(data[i] - 128);
          if (amp > maxAmp) maxAmp = amp;
        }}

        document.getElementById("status").innerText =
          "Listening... Level=" + maxAmp + " (threshold=50)";

        if (!triggered && maxAmp >= thresholdAmp) {{
          lastTriggeredLevel = maxAmp;
          startAutoRecord();
        }}

        if (triggered && (Date.now() - recordStart >= 2500)) {{
          if (activeRecorder && activeRecorder.state !== "inactive") {{
            activeRecorder.stop();
          }}
          return;
        }}

        rafId = requestAnimationFrame(loop);
      }}

      loop();
    }}

    window.onload = startAutoListening;


    /* ============================
       UPLOAD AUDIO
    ============================ */
    async function uploadAudio(triggerLevel = 0) {{
      if (!audioChunks.length) {{
        document.getElementById("status").innerText = "No audio data.";
        return;
      }}

      const blob = new Blob(audioChunks);
      const form = new FormData();
      form.append("audio", blob, "voice.webm");

      document.getElementById("status").innerText = "Uploading...";

      try {{
        const res = await fetch("{NODEJS_UPLOAD_URL}", {{
          method: "POST",
          body: form
        }});
        const json = await res.json();

        const audioUrl = json.audio_url;

        document.getElementById("result").innerText =
          "Trigger Level: " + triggerLevel + "\\n" +
          "Transcript: " + (json.transcript || "") + "\\n" +
          "Label: " + (json.label || "") + "\\n" +
          "Audio URL: " + (audioUrl || "");

        clearCache();
        document.getElementById("status").innerText = "Robot speaking...";

        if (audioUrl) {{
          const audio = new Audio(audioUrl);

          audio.onloadedmetadata = () => {{
            const durationMs = audio.duration * 1000;
            audio.play();

            const waitTime = durationMs + 2000;

            setTimeout(() => {{
              document.getElementById("status").innerText = "Restarting auto listening...";
              startAutoListening();
            }}, waitTime);
          }};
        }} else {{
          setTimeout(startAutoListening, 800);
        }}

      }} catch (err) {{
        document.getElementById("status").innerText = "Upload error: " + err;
      }}
    }}
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
    global scanStatus
    scanStatus = "scanning"
    print("⚡ Scan started → scanStatus = scanning")
    return {"status": "ok", "scanStatus": scanStatus}


# ============================================================
# MODULE CẢM BIẾN: GET SCAN STATUS
# ============================================================
@app.route("/get_scanningstatus")
def get_scanningstatus():
    return {"scanStatus": scanStatus}


# ============================================================
# MODULE CẢM BIẾN: PUSH MAPPING DATA
#  - Body có thể là:
#    { "angle": 30, "distance": 120 }
#  - hoặc:
#    {{ "points": [ {{angle, distance}}, ... ] }}
#  - hoặc có sẵn x,y
# ============================================================
@app.route("/push_mapping", methods=["POST"])
def push_mapping():
    global mapping_points
    data = request.get_json(force=True, silent=True) or {}

    # Nếu body có dạng {{ "points": [...] }}
    if isinstance(data.get("points"), list):
        for p in data["points"]:
            if isinstance(p, dict):
                mapping_points.append(p)
    else:
        # Body là 1 point đơn
        if isinstance(data, dict):
            mapping_points.append(data)

    print(f"📍 Received mapping data, total points = {{len(mapping_points)}}")
    return { "status": "ok", "total_points": len(mapping_points) }


# ============================================================
# GET MAP FOR FRONT-END
# ============================================================
@app.route("/get_map")
def get_map():
    return {"points": mapping_points}


# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
