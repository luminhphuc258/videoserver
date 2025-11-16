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
<title>Matthew Robot — Wake Word</title>
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
    background:#0af;
    padding:12px 26px;
    font-size:18px;
    border:none;
    border-radius:8px;
    cursor:pointer;
}}
#status {{
    margin-top:12px;
    font-weight:bold;
}}
#result {{
    margin-top:20px;
    background:#222;
    padding:15px;
    border-radius:8px;
    min-height:80px;
    text-align:left;
    white-space:pre-wrap;
}}
</style>
</head>

<body>

<h2>Matthew Robot — Wake Word: "robot"</h2>

<button id="startBtn">Speak</button>

<p id="status">Ready.</p>
<div id="result"></div>


<script>
// =====================================================================
// CONSTANTS
// =====================================================================
const STOP_GAP = 700;   // 0.7s im lặng là stop
const WAKEWORD = "robot";

// =====================================================================
// GLOBALS
// =====================================================================
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let lastVoiceTime = 0;

let recognizer = null;
let stream = null;


// =====================================================================
// START RECORDING RAW AUDIO (upload to server)
// =====================================================================
async function startRecording() {
    if (isRecording) return;

    console.log("🎤 START recording...");
    document.getElementById("status").innerText = "Recording after wake word...";

    if (!stream) {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    }

    audioChunks = [];
    mediaRecorder = new MediaRecorder(stream);

    mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.onstop = async () => {
        console.log("🛑 STOP recording");

        if (!audioChunks.length) {
            console.log("⚠ No audio chunks");
            return;
        }

        const blob = new Blob(audioChunks, { type: "audio/webm" });
        audioChunks = [];

        const form = new FormData();
        form.append("audio", blob, "voice.webm");

        document.getElementById("status").innerText = "Uploading...";

        const res = await fetch("{NODEJS_UPLOAD_URL}", {
            method: "POST",
            body: form,
        });

        const json = await res.json();
        document.getElementById("result").innerText =
            "Transcript: " + (json.transcript || "") + "\\n" +
            "Label: " + (json.label || "") + "\\n" +
            "Audio URL: " + (json.audio_url || "");

        document.getElementById("status").innerText = "Ready.";
    };

    mediaRecorder.start();
    isRecording = true;
}

// =====================================================================
// STOP RECORDING
// =====================================================================
function stopRecording() {
    if (isRecording && mediaRecorder.state !== "inactive") {
        console.log("⏹ Force stop recording");
        isRecording = false;
        mediaRecorder.stop();
    }
}

// =====================================================================
// SPEECH RECOGNITION SETUP
// =====================================================================
function startWakeWordListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        alert("Browser does not support SpeechRecognition (Chrome recommended).");
        return;
    }

    recognizer = new SpeechRecognition();
    recognizer.lang = "en-US";
    recognizer.continuous = true;
    recognizer.interimResults = true;

    recognizer.onresult = (event) => {
        const txt = event.results[event.results.length - 1][0].transcript.toLowerCase();
        console.log("ASR:", txt);

        lastVoiceTime = performance.now();

        // CHECK WAKE WORD
        if (txt.includes(WAKEWORD)) {
            console.log("🔥 WAKE-WORD DETECTED:", WAKEWORD);
            startRecording();
        }
    };

    recognizer.onerror = (e) => console.error("ASR error:", e);
    recognizer.onend = () => {
        console.log("ASR ended → restarting...");
        recognizer.start();
    };

    recognizer.start();
    console.log("🎧 Wake-word listener started");
}


// =====================================================================
// CHECK FOR SILENCE (STOP RECORDING)
// =====================================================================
setInterval(() => {
    if (isRecording) {
        const now = performance.now();
        if (now - lastVoiceTime > STOP_GAP) {
            stopRecording();
        }
    }
}, 200);


// =====================================================================
// BUTTON HANDLER
// =====================================================================
document.getElementById("startBtn").onclick = async () => {
    document.getElementById("startBtn").disabled = true;
    document.getElementById("status").innerText = "Listening for wake-word: robot…";

    // Ask mic permission ONCE
    await navigator.mediaDevices.getUserMedia({ audio: true });

    // Start SpeechRecognition
    startWakeWordListening();
};
</script>

</body>
</html>
    """
    return render_template_string(html)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
