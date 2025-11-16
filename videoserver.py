from flask import Flask, Response

app = Flask(__name__)

NODEJS_UPLOAD_URL = "https://embeddedprogramming-healtheworldserver.up.railway.app/upload_audio"


@app.route("/")
def index():
    return Response("""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Matthew Robot — Active Listening</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body {
      background:#111;
      color:#eee;
      font-family:sans-serif;
      text-align:center;
      padding:20px;
    }
    h2 {
      color:#0ff;
    }
    #speakBtn {
      margin:10px;
      padding:12px 28px;
      font-size:18px;
      font-weight:bold;
      border:none;
      border-radius:8px;
      cursor:pointer;
      background:#0af;
      color:#000;
    }
    #speakBtn.active {
      background:#0f0;
      color:#000;
    }
    #status {
      margin-top:15px;
      font-weight:bold;
      color:#0f0;
    }
    #result {
      margin-top:20px;
      padding:15px;
      border-radius:8px;
      background:#222;
      min-height:60px;
      text-align:left;
      white-space:pre-wrap;
    }
  </style>
</head>

<body>
  <h2>Matthew Robot — Active Listening Mode</h2>

  <button id="speakBtn">🎤 Start Listening</button>
  <p id="status">Idle.</p>

  <div id="result"></div>

<script>
let mediaRecorder = null;
let audioChunks = [];
let vadActive = false;
let listening = false;
let checkInterval = null;

// độ nhạy VAD
let vadThreshold = 0.015;

// ================= VAD DETECTOR ==================
async function createVAD(stream) {
    const audioCtx = new AudioContext();
    const src = audioCtx.createMediaStreamSource(stream);
    const processor = audioCtx.createScriptProcessor(2048, 1, 1);

    processor.onaudioprocess = (e) => {
        const data = e.inputBuffer.getChannelData(0);
        let sum = 0;
        for (let i = 0; i < data.length; i++) sum += data[i] * data[i];
        const rms = Math.sqrt(sum / data.length);

        vadActive = rms > vadThreshold;

        if (vadActive)
          document.getElementById("status").innerText = "🎤 Voice detected...";
    };

    src.connect(processor);
    processor.connect(audioCtx.destination);
}

// ================= START LISTENING ==================
async function startListening() {
    if (listening) return;

    listening = true;
    document.getElementById("speakBtn").classList.add("active");
    document.getElementById("speakBtn").innerText = "🟢 Listening…";
    document.getElementById("status").innerText = "Listening...";

    const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
            noiseSuppression: true,
            echoCancellation: true,
            autoGainControl: true
        }
    });

    await createVAD(stream);

    mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
        if (!audioChunks.length) return;

        const blob = new Blob(audioChunks, { type: "audio/webm" });
        audioChunks = [];

        const form = new FormData();
        form.append("audio", blob, "voice.webm");

        document.getElementById("status").innerText = "Uploading...";

        try {
            const res = await fetch("%s", {
                method: "POST",
                body: form
            });

            const json = await res.json();

            const txt =
                "Transcript: " + (json.transcript || "") + "\\n" +
                "Label: " + (json.label || "") + "\\n" +
                "Audio URL: " + (json.audio_url || "");

            document.getElementById("result").innerText = txt;
            document.getElementById("status").innerText = "Listening...";

        } catch (err) {
            console.error(err);
            document.getElementById("status").innerText = "Upload error.";
        }
    };

    // check every 200ms
    checkInterval = setInterval(() => {
        if (vadActive && mediaRecorder.state === "inactive") {
            audioChunks = [];
            mediaRecorder.start();
        }

        if (!vadActive && mediaRecorder.state === "recording") {
            mediaRecorder.stop();
        }
    }, 200);
}

document.getElementById("speakBtn").onclick = startListening;

</script>

</body>
</html>
""" % NODEJS_UPLOAD_URL, mimetype="text/html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
