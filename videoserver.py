from flask import Flask, render_template_string

app = Flask(__name__)

NODEJS_UPLOAD_URL = "https://embeddedprogramming-healtheworldserver.up.railway.app/upload_audio"

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
  </style>
</head>

<body>
  <h2>Matthew Robot — Auto Active Listening</h2>

  <!-- SPEAK/STOP thủ công -->
  <div>
    <button id="startBtn">Speak</button>
    <button id="stopBtn" disabled>Stop</button>
  </div>

  <p id="status">Initializing microphone...</p>
  <div id="result"></div>

  <script>
    /* ================================
       GLOBAL STATE
    ================================ */
    let manualStream = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let botCallCount = 0;

    /* các biến để tránh leak */
    let listenStream = null;
    let audioCtx = null;
    let source = null;
    let analyser = null;
    let rafId = null;
    let activeRecorder = null;

    /* ================================
       CLEAR CACHE AFTER 3 CALLS
    ================================ */
    function clearCache() {{
      console.warn("🔥 CLEAR CACHE TRIGGERED");

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
        audioCtx.close();
      }}
      audioCtx = null;

      source = null;
      analyser = null;

      audioChunks = [];
      document.getElementById("status").innerText = "Cache cleared. Restarting...";
    }}

    /* ================================
       MANUAL RECORD
    ================================ */
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
        document.getElementById("status").innerText = "Processing (manual)...";
        document.getElementById("startBtn").disabled = false;
        document.getElementById("stopBtn").disabled = true;
      }}
    }}

    document.getElementById("startBtn").onclick = startRecordingManual;
    document.getElementById("stopBtn").onclick  = stopRecordingManual;


    /* ================================
       AUTO ACTIVE LISTENING
    ================================ */
    const thresholdAmp = 92;

    async function startAutoListening() {{
      clearCache();   // reset mọi thứ trước khi bắt đầu lại

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
          "Listening... Level=" + maxAmp + " (threshold=40)";

        if (!triggered && maxAmp >= thresholdAmp) {{
          lastTriggeredLevel = maxAmp;
          startAutoRecord();
        }}

        if (triggered && (Date.now() - recordStart >= 5000)) {{
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
    async function uploadAudio(triggerLevel=0) {{
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
          method:"POST",
          body:form
        }});
        const json = await res.json();

        document.getElementById("result").innerText =
          "Trigger Level: " + triggerLevel + "\\n" +
          "Transcript: " + (json.transcript || "") + "\\n" +
          "Label: " + (json.label || "") + "\\n" +
          "Audio URL: " + (json.audio_url || "");

        botCallCount++;

        // 🔥 CLEAR CACHE EVERY 3 CALLS
        if (botCallCount >= 3) {{
          botCallCount = 0;
          clearCache();
          setTimeout(startAutoListening, 1000);
          return;
        }}

        setTimeout(startAutoListening, 800);

      }} catch(err) {{
        document.getElementById("status").innerText = "Upload error: " + err;
      }}
    }}

  </script>
</body>
</html>
    """
    return render_template_string(html)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
