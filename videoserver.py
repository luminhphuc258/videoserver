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
      <title>Matthew Robot — Active Listening</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        body {{
          background:#111;
          color:#eee;
          font-family:sans-serif;
          text-align:center;
          padding:20px;
        }}
        #speakBtn {{
          padding:12px 26px;
          font-size:18px;
          border:none;
          background:#0af;
          color:#000;
          border-radius:8px;
          cursor:pointer;
        }}
        #status {{
          margin-top:18px;
          font-size:18px;
          color:#0ff;
          font-weight:bold;
        }}
        #result {{
          margin-top:20px;
          padding:15px;
          border-radius:8px;
          background:#222;
          min-height:60px;
          text-align:left;
          white-space:pre-wrap;
        }}
      </style>
    </head>

    <body>
      <h2>Matthew Robot — Active Listening Mode</h2>

      <button id="speakBtn">🎤 Speak</button>

      <p id="status">Idle.</p>
      <div id="result"></div>

      <script>
        let audioContext;
        let processor;
        let stream;
        let mediaRecorder;
        let chunks = [];

        // === Anti-noise settings ===
        let vadThreshold = 0.04;       // Avoid fan noise
        let vadCount = 0;
        let vadRequired = 80;           // Must speak >= 150ms

        let isRecording = false;

        document.getElementById("speakBtn").onclick = startListening;

        async function startListening() {{
          document.getElementById("status").innerText = "🎧 Listening...";
          document.getElementById("result").innerText = "";

          stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
          audioContext = new (window.AudioContext || window.webkitAudioContext)();
          processor = audioContext.createScriptProcessor(1024, 1, 1);

          const source = audioContext.createMediaStreamSource(stream);
          source.connect(processor);
          processor.connect(audioContext.destination);

          chunks = [];
          mediaRecorder = new MediaRecorder(stream);

          mediaRecorder.ondataavailable = (e) => {{
            if (e.data.size > 0) chunks.push(e.data);
          }};

          mediaRecorder.onstop = async () => {{
            const blob = new Blob(chunks, {{ type: "audio/webm" }});
            const form = new FormData();
            form.append("audio", blob, "voice.webm");

            document.getElementById("status").innerText = "⏫ Uploading...";

            const res = await fetch("{NODEJS_UPLOAD_URL}", {{
              method: "POST",
              body: form
            }});

            const json = await res.json();
            document.getElementById("result").innerText =
              "Transcript: " + (json.transcript || "") + "\\n" +
              "Label: " + (json.label || "") + "\\n" +
              "Audio URL: " + (json.audio_url || "");

            document.getElementById("status").innerText = "✔ Done, waiting for next speech...";
            isRecording = false;
          }};

          processor.onaudioprocess = (e) => {{
            const input = e.inputBuffer.getChannelData(0);
            let sum = 0;
            for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
            
            const rms = Math.sqrt(sum / input.length);

            // === Voice Detection with noise filtering ===
            if (rms > vadThreshold) {{
              vadCount++;
            }} else {{
              vadCount = 0;
            }}

            const voiceDetected = vadCount >= vadRequired;

            if (voiceDetected && !isRecording) {{
              isRecording = true;
              chunks = [];
              mediaRecorder.start();
              document.getElementById("status").innerText = "🎤 Voice detected! Recording...";
            }}

            if (!voiceDetected && isRecording) {{
              mediaRecorder.stop();
              document.getElementById("status").innerText = "⏳ Processing...";
            }}
          }};
        }}
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
