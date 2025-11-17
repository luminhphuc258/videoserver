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
          width:200px;
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

      <!-- Nút Speak/Stop cũ -->
      <div>
        <button id="startBtn">Speak</button>
        <button id="stopBtn" disabled>Stop</button>
      </div>

      <!-- Active Listening -->
      <h3 style="color:#0f0; margin-top:30px;">Active Listening Mode</h3>

      <input id="thresholdBox" type="number" min="1" max="100"
             placeholder="Threshold (gợi ý: 20–30)" />

      <br>
      <button id="updateBtn">Update Threshold & Start</button>

      <p id="status">Ready.</p>
      <div id="result"></div>

      <script>
        let mediaRecorder = null;
        let audioChunks = [];
        let listening = false;
        let audioStream = null;
        let thresholdValue = 25;  // mặc định % (0–100)
        let detectTimer = null;

        // =============================
        //  GHI THỦ CÔNG: START / STOP
        // =============================
        async function startRecording() {{
          if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
            alert("Trình duyệt không hỗ trợ micro.");
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
            console.error(e);
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

        document.getElementById("startBtn").onclick = startRecording;
        document.getElementById("stopBtn").onclick = stopRecording;

        // ======================================
        //   UPDATE THRESHOLD & START LISTENING
        // ======================================
        document.getElementById("updateBtn").onclick = async function() {{
          const val = parseInt(document.getElementById("thresholdBox").value);
          if (isNaN(val) || val < 1 || val > 100) {{
            alert("Nhập threshold từ 1–100 (gợi ý 20–30).");
            return;
          }}
          thresholdValue = val;
          document.getElementById("status").innerText =
            "Threshold = " + thresholdValue + "%. Đang bật Active Listening...";

          // nếu đang nghe cũ thì stop lại
          listening = false;
          if (detectTimer) {{
            clearInterval(detectTimer);
            detectTimer = null;
          }}
          if (audioStream) {{
            audioStream.getTracks().forEach(t => t.stop());
            audioStream = null;
          }}

          // bắt đầu session mới
          await startActiveListening();
        }};

        // =============================
        //      ACTIVE LISTENING LOOP
        // =============================
        async function startActiveListening() {{
          if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
            alert("Trình duyệt không hỗ trợ micro.");
            return;
          }}

          try {{
            audioStream = await navigator.mediaDevices.getUserMedia({{
              audio: {{
                echoCancellation:false,
                noiseSuppression:false
              }}
            }});
          }} catch(e) {{
            console.error(e);
            document.getElementById("status").innerText =
              "Không lấy được quyền micro (Active Listening).";
            return;
          }}

          const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
          const source = audioCtx.createMediaStreamSource(audioStream);
          const analyser = audioCtx.createAnalyser();
          analyser.fftSize = 1024;

          source.connect(analyser);

          let data = new Uint8Array(analyser.fftSize);
          listening = true;
          let triggered = false;
          let recordStartTime = 0;

          // Hàm bắt đầu ghi tối đa 5s
          function startAutoRecord() {{
            if (triggered) return;
            triggered = true;
            audioChunks = [];

            mediaRecorder = new MediaRecorder(audioStream);
            mediaRecorder.ondataavailable = e => {{
              if (e.data.size > 0) audioChunks.push(e.data);
            }};
            mediaRecorder.onstop = () => {{
              uploadAudio();
            }};

            mediaRecorder.start();
            recordStartTime = Date.now();
            document.getElementById("status").innerText =
              "Sound detected! Đang ghi (tối đa 5s)...";
          }}

          // Hàm dừng ghi + tắt listening
          function stopAutoRecord() {{
            listening = false;
            if (detectTimer) {{
              clearInterval(detectTimer);
              detectTimer = null;
            }}
            if (mediaRecorder && mediaRecorder.state !== "inactive") {{
              mediaRecorder.stop();
            }}
            if (audioStream) {{
              audioStream.getTracks().forEach(t => t.stop());
              audioStream = null;
            }}
          }}

          // Loop kiểm tra biên độ
          detectTimer = setInterval(() => {{
            if (!listening) return;

            analyser.getByteTimeDomainData(data);
            let maxAmp = 0;
            for (let i = 0; i < data.length; i++) {{
              const v = Math.abs(data[i] - 128);
              if (v > maxAmp) maxAmp = v;
            }}

            // maxAmp ~ 0–128 -> convert sang %
            const levelPercent = (maxAmp / 128) * 100;

            // log ra console nếu muốn debug
            // console.log("Level:", levelPercent.toFixed(1), "%");

            if (!triggered && levelPercent >= thresholdValue) {{
              startAutoRecord();
            }}

            if (triggered && (Date.now() - recordStartTime) >= 5000) {{
              stopAutoRecord();
            }}
          }}, 80);  // check ~12.5 lần/giây
        }}

        // ====================================
        //            UPLOAD AUDIO
        // ====================================
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
