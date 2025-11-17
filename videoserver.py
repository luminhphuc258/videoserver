from flask import Flask, render_template_string, request
import requests

app = Flask(__name__)

NODEJS_UPLOAD_URL = "https://embeddedprogramming-healtheworldserver.up.railway.app/upload_audio"

# ENDPOINT SCAN NODEJS
NODEJS_SCAN_30   = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan30"
NODEJS_SCAN_45   = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan45"
NODEJS_SCAN_90   = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan90"
NODEJS_SCAN_180  = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan180"
NODEJS_SCAN_360  = "https://embeddedprogramming-healtheworldserver.up.railway.app/trigger_scan"


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

  <!-- NEW SCAN BUTTONS -->
  <h3 style="margin-top:30px; color:#0f0;">Scan Environment</h3>

  <div id="scanButtons">
      <button onclick="triggerScan('{NODEJS_SCAN_30}', '30°')">Scan 30°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_45}', '45°')">Scan 45°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_90}', '90°')">Scan 90°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_180}', '180°')">Scan 180°</button>
      <button onclick="triggerScan('{NODEJS_SCAN_360}', '360°')">Scan 360°</button>
  </div>

  <canvas id="mapCanvas" width="400" height="400"></canvas>


  <script>

    /* ================================
       SCAN COMMAND TO NODEJS
    ================================ */
    async function triggerScan(url, label) {{
        document.getElementById("status").innerText =
            "Sending scan request " + label + " ...";

        try {{
            await fetch(url, {{ method:"GET" }});
            alert("Robot is scanning " + label);
        }} catch (e) {{
            alert("Cannot send scan command!");
        }}
    }}



    /* =======================================================
         BELOW IS YOUR AUDIO + LISTENING ENGINE — UNTOUCHED
       ======================================================= */

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
       AUTO LISTENING
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
       UPLOAD AUDIO
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


  </script>
</body>
</html>
    """
    return render_template_string(html)


# ROBOT REPORTS SCAN DONE
@app.route("/scan_done", methods=["POST"])
def scan_done():
    print("Robot completed scan.")
    return {"status": "received"}


@app.route("/get_map")
def get_map():
    return {"points": []}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
