from flask import Flask, render_template_string

app = Flask(__name__)

# URL NodeJS server (để upload audio)
NODEJS_UPLOAD_URL = "https://embeddedprogramming-healtheworldserver.up.railway.app/upload_audio"

@app.route("/")
def index():
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Matthew Robot — Voice Control</title>
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
        #activeBtn {{ background:#0f0; color:#000; }}

        #stopBtn:disabled,
        #startBtn:disabled,
        #activeBtn:disabled {{
          opacity:0.5;
          cursor:not-allowed;
        }}

        #thresholdBox {{
          margin-top:10px;
          padding:8px;
          width:160px;
          border-radius:6px;
          border:none;
          font-size:15px;
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
      </style>
    </head>

    <body>
      <h2>Matthew Robot — Voice Only</h2>

      <!-- Nút Speak/Stop -->
      <div>
        <button id="startBtn">Speak</button>
        <button id="stopBtn" disabled>Stop</button>
      </div>

      <!-- Active Listening -->
      <h3 style="color:#0f0; margin-top:30px;">Active Listening Mode</h3>
      <button id="activeBtn">Activate Listening</button>  

      <br>
      <input id="thresholdBox" type="number" min="50" max="3000"
             placeholder="Threshold (vd: 300)" />

      <p id="status">Ready.</p>
      <div id="result"></div>

      <script>
        let mediaRecorder = null;
        let audioChunks = [];
        let listening = false;
        let audioStream = null;

        // =============================
        //  GHI THỦ CÔNG: START / STOP
        // =============================
        async function startRecording() {{
          if (!navigator.mediaDevices) {{
            alert("Browser không hỗ trợ mic.");
            return;
          }}

          try {{
            const stream = await navigator.mediaDevices.getUserMedia({{ audio:true }});
            audioChunks = [];
            mediaRecorder = new MediaRecorder(stream);

            mediaRecorder.ondataavailable = e => {{
              if (e.data.size > 0) audioChunks.push(e.data);
            }};

            mediaRecorder.onstop = () => uploadAudio();

            mediaRecorder.start();
            document.getElementById("status").innerText = "Recording...";
            document.getElementById("startBtn").disabled = true;
            document.getElementById("stopBtn").disabled = false;
          }} catch(e) {{
            alert("Không truy cập được mic: " + e);
          }}
        }}

        function stopRecording() {{
          if (mediaRecorder && mediaRecorder.state !== "inactive") {{
            mediaRecorder.stop();
            document.getElementById("status").innerText = "Processing...";
            document.getElementById("startBtn").disabled = false;
            document.getElementById("stopBtn").disabled = true;
          }}
        }}

        // =============================
        //   ACTIVE LISTENING MODE
        // =============================
        document.getElementById("activeBtn").onclick = async function() {{
          if (listening) return; // tránh double click
          listening = true;

          const threshold = parseInt(document.getElementById("thresholdBox").value || "300");

          document.getElementById("status").innerText = 
              "Active Listening ON (threshold = " + threshold + ")";

          // Lấy microphone
          audioStream = await navigator.mediaDevices.getUserMedia({{
            audio: {{
              echoCancellation:false,
              noiseSuppression:false,
              sampleRate: 44100
            }}
          }});

          const audioCtx = new AudioContext();
          const source = audioCtx.createMediaStreamSource(audioStream);
          const analyser = audioCtx.createAnalyser();
          analyser.fftSize = 2048;

          source.connect(analyser);

          let dataArray = new Uint8Array(analyser.fftSize);
          let triggered = false;
          let recordStartTime = 0;

          function loopDetect() {{
            if (!listening) return;

            analyser.getByteTimeDomainData(dataArray);

            let maxAmp = 0;
            for (let i=0; i<dataArray.length; i++) {{
              let amp = Math.abs(dataArray[i] - 128);
              if (amp > maxAmp) maxAmp = amp;
            }}

            if (!triggered && maxAmp >= threshold) {{
              triggered = true;
              document.getElementById("status").innerText = "Sound detected → start recording (max 5s)";
              startActiveRecorder();
            }}

            if (triggered && (Date.now() - recordStartTime) >= 5000) {{
              stopActiveRecorder();
              return;
            }}

            requestAnimationFrame(loopDetect);
          }}

          function startActiveRecorder() {{
            audioChunks = [];
            mediaRecorder = new MediaRecorder(audioStream);

            mediaRecorder.ondataavailable = e => {{
              if (e.data.size > 0) audioChunks.push(e.data);
            }};

            mediaRecorder.onstop = uploadAudio;

            mediaRecorder.start();
            recordStartTime = Date.now();
          }}

          function stopActiveRecorder() {{
            listening = false;
            mediaRecorder.stop();
            audioStream.getTracks().forEach(t => t.stop());
          }}

          loopDetect();
        }}

        // ====================================
        //           UPLOAD AUDIO
        // ====================================
        async function uploadAudio() {{
          const blob = new Blob(audioChunks);
          const form = new FormData();
          form.append("audio", blob, "voice.webm");

          document.getElementById("status").innerText = "Uploading...";
          document.getElementById("result").innerText = "";

          try {{
            const res = await fetch("{NODEJS_UPLOAD_URL}", {{
              method:"POST",
              body:form
            }});

            const json = await res.json();

            const txt = 
              "Transcript: " + (json.transcript || "") + "\\n" +
              "Label: "       + (json.label || "") + "\\n" +
              "Audio URL: "   + (json.audio_url || "");

            document.getElementById("result").innerText = txt;
            document.getElementById("status").innerText = "Done";

          }} catch (e) {{
            console.log(e);
            document.getElementById("status").innerText = "Upload error: " + e;
          }}
        }}

        // Gán nút
        document.getElementById("startBtn").onclick = startRecording;
        document.getElementById("stopBtn").onclick = stopRecording;

      </script>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
