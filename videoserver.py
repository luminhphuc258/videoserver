from flask import Flask, render_template_string

app = Flask(__name__)

# URL NodeJS server của bạn (endpoint nhận audio)
NODEJS_UPLOAD_URL = "https://embeddedprogramming-healtheworldserver.up.railway.app/upload_audio"

@app.route("/")
def index():
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Matthew Voice Control</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        body {{
          background:#111;
          color:#eee;
          font-family:sans-serif;
          text-align:center;
          padding:20px;
        }}
        h2 {{
          color:#0ff;
        }}
        button {{
          margin:10px;
          padding:10px 20px;
          font-size:16px;
          border:none;
          border-radius:6px;
          cursor:pointer;
        }}
        #startBtn {{
          background:#0af;
          color:#000;
        }}
        #stopBtn {{
          background:#f44;
          color:#000;
        }}
        #stopBtn:disabled,
        #startBtn:disabled {{
          opacity:0.5;
          cursor:not-allowed;
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
          min-height:60px;
          text-align:left;
          white-space:pre-wrap;
        }}
      </style>
    </head>
    <body>
      <h2>Matthew Robot — Voice Only</h2>

      <div>
        <button id="startBtn">Speak</button>
        <button id="stopBtn" disabled>Stop</button>
      </div>

      <p id="status">Ready.</p>

      <div id="result"></div>

      <script>
        let mediaRecorder = null;
        let audioChunks = [];

        async function startRecording() {{
          // Kiểm tra API
          if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {{
            alert("Trình duyệt không hỗ trợ getUserMedia. Hãy dùng Chrome / Edge / Safari mới.");
            return;
          }}

          try {{
            const stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
            audioChunks = [];

            mediaRecorder = new MediaRecorder(stream);
            mediaRecorder.ondataavailable = e => {{
              if (e.data && e.data.size > 0) {{
                audioChunks.push(e.data);
              }}
            }};

            mediaRecorder.onstop = async () => {{
              if (!audioChunks.length) {{
                document.getElementById("status").innerText = "Không có dữ liệu audio.";
                return;
              }}

              const blob = new Blob(audioChunks); // để browser tự chọn mime
              const form = new FormData();
              form.append("audio", blob, "voice.webm");

              document.getElementById("status").innerText = "Uploading to server...";
              document.getElementById("result").innerText = "";

              try {{
                const res = await fetch("{NODEJS_UPLOAD_URL}", {{
                  method: "POST",
                  body: form
                }});

                if (!res.ok) {{
                  document.getElementById("status").innerText = "Upload failed: " + res.status;
                  return;
                }}

                const json = await res.json();
                // NodeJS trả về: {{ status, transcript, label, audio_url }}
                const txt = 
                  "Transcript: " + (json.transcript || "") + "\\n" +
                  "Label: " + (json.label || "") + "\\n" +
                  "Audio URL: " + (json.audio_url || "");
                document.getElementById("result").innerText = txt;
                document.getElementById("status").innerText = "Done.";
              }} catch (err) {{
                console.error(err);
                document.getElementById("status").innerText = "Error: " + err;
              }}
            }};

            mediaRecorder.start();
            document.getElementById("status").innerText = "Recording...";
            document.getElementById("startBtn").disabled = true;
            document.getElementById("stopBtn").disabled = false;
          }} catch (err) {{
            console.error(err);
            alert("Không lấy được quyền micro: " + err);
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
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    # Nếu chạy local:
    # app.run(host="0.0.0.0", port=8000, debug=True)
    # Nếu Railway dùng gunicorn thì chỉ cần để như cũ, không sửa
    app.run(host="0.0.0.0", port=8000, threaded=True)
