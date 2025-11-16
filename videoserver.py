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
        <title>Matthew Robot — Wake Word Mode</title>
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
            #speakBtn {{
                background:#0af;
                padding:12px 26px;
                border:none;
                border-radius:8px;
                font-size:18px;
                color:#000;
                cursor:pointer;
            }}
            #speakBtn:disabled {{
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
        <h2>Matthew Robot — Wake Word: "robot"</h2>

        <button id="speakBtn">Speak</button>

        <p id="status">Ready.</p>
        <div id="result"></div>

        <script>
        let mediaRecorder = null;
        let chunks = [];
        let isRecording = false;
        let lastVoiceTime = 0;

        let STOP_GAP = 600; // 0.6s im lặng thì stop ghi âm

        // ===== Speech Recognition =====
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        let recognizer = null;

        function startSpeechRecognition() {{
            recognizer = new SpeechRecognition();
            recognizer.lang = "en-US";
            recognizer.continuous = true;
            recognizer.interimResults = true;

            recognizer.onresult = (event) => {{
                const txt = event.results[event.results.length - 1][0].transcript.toLowerCase();

                console.log("ASR:", txt);

                // nếu chứa wake-word "robot"
                if (txt.includes("robot")) {{
                    console.log("Wake-word detected: robot");

                    if (!isRecording) {{
                        startRecording();
                        document.getElementById("status").innerText = "🎤 Recording (wake-word)…";
                    }}
                }}

                lastVoiceTime = performance.now();
            }};

            recognizer.onend = () => recognizer.start();
            recognizer.start();
        }}

        // ===== MediaRecorder (real audio upload) =====
        let stream = null;

        async function startRecording() {{
            if (isRecording) return;

            if (!stream) {{
                stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
            }}

            chunks = [];
            mediaRecorder = new MediaRecorder(stream);

            mediaRecorder.ondataavailable = e => {{
                if (e.data.size > 0) chunks.push(e.data);
            }};

            mediaRecorder.onstop = async () => {{
                if (!chunks.length) return;

                const blob = new Blob(chunks, {{ type: "audio/webm" }});
                chunks = [];

                const form = new FormData();
                form.append("audio", blob, "voice.webm");

                document.getElementById("status").innerText = "Uploading...";

                const res = await fetch("{NODEJS_UPLOAD_URL}", {{
                    method: "POST",
                    body: form
                }});

                const json = await res.json();

                document.getElementById("result").innerText =
                    "Transcript: " + (json.transcript || "") + "\\n" +
                    "Label: " + (json.label || "") + "\\n" +
                    "Audio URL: " + (json.audio_url || "");

                document.getElementById("status").innerText = "Ready.";
            }};

            mediaRecorder.start();
            isRecording = true;
        }}

        function stopRecording() {{
            if (isRecording) {{
                isRecording = false;
                mediaRecorder.stop();
            }}
        }}

        // ===== LOOP kiểm tra tiếng dừng =====
        setInterval(() => {{
            if (isRecording) {{
                const now = performance.now();

                if (now - lastVoiceTime > STOP_GAP) {{
                    stopRecording();
                }}
            }}
        }}, 200);

        // ===== Start Listening =====
        document.getElementById("speakBtn").onclick = async () => {{
            document.getElementById("speakBtn").disabled = true;
            document.getElementById("status").innerText = "Listening for wake-word: robot…";

            await navigator.mediaDevices.getUserMedia({{ audio: true }});
            startSpeechRecognition();
        }};
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
