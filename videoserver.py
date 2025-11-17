from flask import Flask, render_template_string, request

app = Flask(__name__)

NODEJS_UPLOAD_URL = "https://embeddedprogramming-healtheworldserver.up.railway.app/upload_audio"

# Endpoint NodeJS để request cho server publish MQTT scan command
NODEJS_SCAN_URL = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan"

@app.route("/")
def index():
    html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Matthew Robot — Auto Active Listening</title>
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
      margin:10px;
      padding:10px 20px;
      font-size:16px;
      border:none;
      border-radius:6px;
      cursor:pointer;
    }}

    #startBtn {{ background:#0af; color:#000; }}
    #stopBtn  {{ background:#f44; color:#000; }}

    #scanBtn {{
      background:#0f0; 
      color:#000;
      font-weight:bold;
      margin-top:20px;
    }}

    #stopBtn:disabled,
    #startBtn:disabled {{ opacity:0.5; cursor:not-allowed; }}

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
    }}

    /* MAP CANVAS */
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

  <!-- NEW BUTTON: SCAN TO MAP -->
  <button id="scanBtn">Scan to Map 2D</button>

  <!-- MAP CANVAS -->
  <canvas id="mapCanvas" width="400" height="400"></canvas>

  <script>

    /* ================================
       GLOBAL STATE
    ================================ */
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


    /* ================================
       CLEAR ALL AUDIO OBJECTS
    ================================ */
    function clearCache() {{
      console.warn("🔥 CLEAR CACHE");

      if (rafId) cancelAnimationFrame(rafId);
      rafId = null;

      if (activeRecorder && activeRecorder.state !== "inactive") {{
        try {{ activeRecorder.stop(); }} catch(e){{}}
      }}
      activeRecorder = null;

      if (listenStream) {{
        listenStream.getTracks().forEach(t => t.stop());
      }}
      listenStream = null;

      if (audioCtx) {{
        try {{ audioCtx.close(); }} catch(e){{}}
      }}
      audioCtx = null;

      source = null;
      analyser = null;

      audioChunks = [];
    }}


    /* ================================
       MANUAL RECORD
    ================================ */
    async function startRecordingManual() {{
      manualStream = await navigator.mediaDevices.getUserMedia({{ audio:true }});
      audioChunks = [];

      mediaRecorder = new MediaRecorder(manualStream);
      mediaRecorder.ondataavailable = e => {{ if (e.data.size > 0) audioChunks.push(e.data); }};
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


    /* ================================
       AUTO ACTIVE LISTENING
    ================================ */
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


    /* ================================
       UPLOAD AUDIO + WAIT FOR BOT
    ================================ */
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



    /* ======================================================
       NEW FEATURE — SEND SCAN COMMAND TO SERVER
    ====================================================== */

    document.getElementById("scanBtn").onclick = async () => {{
      document.getElementById("status").innerText = "Requesting robot to scan...";

      try {{
        await fetch("{NODEJS_SCAN_URL}", {{ method: "POST" }});
        alert("Robot bắt đầu quay 360° để quét map!");
      }} catch (e) {{
        alert("Lỗi: không gửi được scan command.");
      }}
    }};


    /* ======================================================
       WHEN ROBOT REPORTS SCAN DONE → FETCH MAP + DRAW
    ====================================================== */

    async function fetchMapAndDraw() {{
      try {{
        const res = await fetch("/get_map");
        const points = await res.json();
        drawMap(points);
      }} catch (e) {{
        console.log("Map fetch error", e);
      }}
    }}

    function drawMap(points) {{
      const c = document.getElementById("mapCanvas");
      const ctx = c.getContext("2d");

      ctx.clearRect(0,0,400,400);

      // robot ở giữa
      ctx.fillStyle = "#0f0";
      ctx.beginPath();
      ctx.arc(200,200,5,0,Math.PI*2);
      ctx.fill();

      const scale = 50; // 1m = 50px

      ctx.fillStyle = "#f44";

      points.forEach(p => {{
        let sx = 200 + p.x * scale;
        let sy = 200 - p.y * scale;
        ctx.fillRect(sx, sy, 3, 3);
      }});
    }}

  </script>
</body>
</html>
    """
    return render_template_string(html)



# Endpoint để robot ESP32 báo "scan done"
@app.route("/scan_done", methods=["POST"])
def scan_done():
    print("Robot completed scan.")
    return {"status": "received"}


# Endpoint giả để server trả map (bạn sẽ dùng NodeJS real API)
@app.route("/get_map")
def get_map():
    # tạm trả rỗng
    return {"points": []}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
