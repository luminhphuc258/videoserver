from flask import Flask, render_template_string

app = Flask(__name__)

# NodeJS endpoint nhận audio
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
        <h2>Matthew Robot — Active Listening</h2>

        <button id="speakBtn">Speak</button>

        <p id="status">Ready.</p>
        <div id="result"></div>

        <script>
        let mediaRecorder = null;
        let chunks = [];
        let isRecording = false;

        let speakingStart = 0;
        let lastVoiceTime = 0;

        // === VAD config ===
        let vadThreshold = 0.04;      // chống tiếng quạt nền
        let VAD_START_TIME = 4000;    // 4 giây nói liên tục thì bắt đầu ghi
        let VAD_STOP_GAP = 600;       // 0.6 giây im lặng thì stop

        async function startListening() {{
            document.getElementById("speakBtn").disabled = true;

            const stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
            const audioCtx = new AudioContext();
            const source = audioCtx.createMediaStreamSource(stream);

            // Processor
            const processor = audioCtx.createScriptProcessor(2048, 1, 1);
            source.connect(processor);
            processor.connect(audioCtx.destination);

            // MediaRecorder
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

            // === ACTIVE VAD ===
            processor.onaudioprocess = (e) => {{
                const input = e.inputBuffer.getChannelData(0);

                let sum = 0;
                for (let i = 0; i < input.length; i++)
                    sum += input[i] * input[i];

                const rms = Math.sqrt(sum / input.length);
                const now = performance.now();

                if (rms > vadThreshold) {{
                    // đang nói
                    lastVoiceTime = now;
                    if (speakingStart === 0) speakingStart = now;

                    // BẮT ĐẦU GHI ÂM (nếu nói >= 4s)
                    if (!isRecording && (now - speakingStart >= VAD_START_TIME)) {{
                        isRecording = true;
                        mediaRecorder.start();
                        document.getElementById("status").innerText = "🎤 Recording...";
                    }}
                }} else {{
                    // im lặng
                    speakingStart = 0;

                    if (isRecording && (now - lastVoiceTime > VAD_STOP_GAP)) {{
                        isRecording = false;
                        mediaRecorder.stop();
                        document.getElementById("status").innerText = "⏳ Processing...";
                    }}
                }}
            }};

            document.getElementById("status").innerText = "Listening...";
        }}

        document.getElementById("speakBtn").onclick = startListening;
        </script>
    </body>
    </html>
    """
    return render_template_string(html)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
