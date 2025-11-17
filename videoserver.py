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
        #updateBtn {{ background:#0f0; color:#000; }}

        #thresholdBox {{
          margin-top:10px;
          padding:8px;
          width:220px;
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

      <!-- Nút Speak/Stop thủ công -->
      <div>
        <button id="startBtn">Speak</button>
        <button id="stopBtn" disabled>Stop</button>
      </div>

      <!-- Active Listening -->
      <h3 style="color:#0f0; margin-top:30px;">Active Listening Mode</h3>

      <input id="thresholdBox" type="number" min="5" max="120"
             placeholder="Threshold biên độ (gợi ý: 20–40)" />

      <br>
      <button id="updateBtn">Update Threshold & Start Listening</button>

      <p id="status">Ready.</p>
      <div id="result"></div>

      <script>
        let mediaRecorder = null;
        let audioChunks = [];
        let manualStream = null;

        // ========== GHI THỦ CÔNG: SPEAK / STOP ==========
        async function startRecordingManual() {{
          if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
            alert("Trình duyệt không hỗ trợ micro.");
            return;
          }}
          try {{
            manualStream = await navigator.mediaDevices.getUserMedia({{ audio:true }});
            audioChunks = [];
            mediaRecorder = new MediaRecorder(manualStream);

            mediaRecorder.ondataavailable = e => {{
              if (e.data.size > 0) audioChunks.push(e.data);
            }};
            mediaRecorder.onstop = () => {{
              if (manualStream) {{
                manualStream.getTracks().forEach(t => t.stop());
                manualStream = null;
              }}
              uploadAudio();
            }};

            mediaRecorder.start();
            document.getElementById("status").innerText = "Recording (manual)...";
            document.getElementById("startBtn").disabled = true;
            document.getElementById("stopBtn").disabled = false;
          }} catch(e) {{
            console.error(e);
            alert("Không truy cập được mic: " + e);
          }}
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

        // ========== ACTIVE LISTENING ==========
        let listening = false;
        let listenStream = null;
        let thresholdAmp = 30;   // raw amp 0–128
        let activeRecorder = null;

        document.getElementById("updateBtn").onclick = async function() {{
          const val = parseInt(document.getElementById("thresholdBox").value);
          if (isNaN(val) || val < 5 || val > 120) {{
            alert("Nhập threshold từ 5–120 (gợi ý 20–40).");
            return;
          }}
          thresholdAmp = val;

          // Nếu đang nghe cũ thì stop
          if (listenStream) {{
            listenStream.getTracks().forEach(t => t.stop());
            listenStream = null;
          }}
          listening = false;

          document.getElementById("status").innerText =
            "Threshold = " + thresholdAmp + ". Đang bật Active Listening...";

          await startActiveListening();
        }};

        async function startActiveListening() {{
          if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
            alert("Trình duyệt không hỗ trợ micro.");
            return;
          }}

          try {{
            listenStream = await navigator.mediaDevices.getUserMedia({{ audio:true }});
          }} catch(e) {{
            console.error(e);
            document.getElementById("status").innerText =
              "Không lấy được quyền micro (Active Listening).";
            return;
          }}

          const AudioCtx = window.AudioContext || window.webkitAudioContext;
          const audioCtx = new AudioCtx();
          const source = audioCtx.createMediaStreamSource(listenStream);
          const analyser = audioCtx.createAnalyser();
          analyser.fftSize = 1024;

          source.connect(analyser);

          const data = new Uint8Array(analyser.fftSize);
          listening = true;
          let triggered = false;
          let recordStart = 0;

          function startAutoRecord() {{
            if (triggered) return;
            triggered = true;

            audioChunks = [];
            activeRecorder = new MediaRecorder(listenStream);

            activeRecorder.ondataavailable = e => {{
              if (e.data.size > 0) audioChunks.push(e.data);
            }};
            activeRecorder.onstop = () => {{
              // dừng stream
              if (listenStream) {{
                listenStream.getTracks().forEach(t => t.stop());
                listenStream = null;
              }}
              uploadAudio();
            }};

            activeRecorder.start();
            recordStart = Date.now();
            document.getElementById("status").innerText =
              "Sound detected! Đang ghi (tối đa 5s)...";
          }}

          function stopAutoRecord() {{
            listening = false;
            if (activeRecorder && activeRecorder.state !== "inactive") {{
              activeRecorder.stop();
            }} else {{
              // không ghi được gì → dừng stream thôi
              if (listenStream) {{
                listenStream.getTracks().forEach(t => t.stop());
                listenStream = null;
              }}
            }}
          }}

          async function loop() {{
            if (!listening) return;

            analyser.getByteTimeDomainData(data);
            let maxAmp = 0;
            for (let i = 0; i < data.length; i++) {{
              const v = Math.abs(data[i] - 128);
              if (v > maxAmp) maxAmp = v;
            }}

            // hiển thị biên độ hiện tại để bạn thấy nó có đo
            document.getElementById("status").innerText =
              "Active Listening - Level: " + maxAmp + " / 128 | Threshold: " + thresholdAmp;

            if (!triggered && maxAmp >= thresholdAmp) {{
              startAutoRecord();
            }}

            if (triggered && (Date.now() - recordStart) >= 5000) {{
              stopAutoRecord();
              return;
            }}

            requestAnimationFrame(loop);
          }}

          loop();
        }}

        // ========== UPLOAD AUDIO ==========
        async function uploadAudio() {{
          if (!audioChunks.length) {{
            document.getElementById("status").innerText =
              "Không có dữ liệu audio để upload.";
            return;
          }}

          const blob = new Blob(audioChunks);
          const form = new FormData();
          form.append("audio", blob, "voice.webm");

          document.getElementById("status").innerText = "Uploading...";
          document.getElementById("result").innerText = "";

          try {{
            const res = await fetch("{NODEJS_UPLOAD_URL}", {{
              method: "POST",
              body: form
            }});
            if (!res.ok) {{
              document.getElementById("status").innerText =
                "Upload failed: " + res.status;
              return;
            }}
            const json = await res.json();

            const txt =
              "Transcript: " + (json.transcript || "") + "\\n" +
              "Label: " + (json.label || "") + "\\n" +
              "Audio URL: " + (json.audio_url || "");

            document.getElementById("result").innerText = txt;
            document.getElementById("status").innerText = "Done.";
          }} catch(e) {{
            console.error(e);
            document.getElementById("status").innerText = "Upload error: " + e;
          }}
        }}
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
