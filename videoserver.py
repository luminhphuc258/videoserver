from flask import Flask, Response, render_template_string
import cv2, time, ssl, json, threading, base64, numpy as np
from threading import Lock
from paho.mqtt import client as mqtt

app = Flask(__name__)

# ===== Bộ nhận dạng khuôn mặt =====
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
)

# ===== Cấu hình MQTT =====
MQTT_HOST = "rfff7184.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
MQTT_USER = "robot_matthew"
MQTT_PASS = "29061992abCD!yesokmen"
CAMERA_TOPIC = "robot/camera/#"

mqtt_cli = None
latest_frame = None
frame_lock = Lock()
camera_buffer = {}

# ===== Địa chỉ livestream HTTP của ESP32 =====
ESP32_STREAM_URL = "http://192.168.100.134:81/stream"  # ⚠️ thay IP thật của ESP32

# ---------- Ghép và decode ảnh từ MQTT ----------
def handle_camera_part(topic, payload):
    global latest_frame
    try:
        part_key = topic.split("/")[-1]
        frame_id = "main"
        if frame_id not in camera_buffer:
            camera_buffer[frame_id] = b""
        camera_buffer[frame_id] += payload

        # Khi nhận đủ dữ liệu hoặc tới part cuối thì decode
        if len(camera_buffer[frame_id]) > 60000 or part_key.endswith("part9"):
            b64 = camera_buffer[frame_id].decode()
            del camera_buffer[frame_id]
            img_bytes = base64.b64decode(b64)
            npimg = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
            if frame is not None:
                with frame_lock:
                    latest_frame = frame
    except Exception as e:
        print("❌ handle_camera_part:", e)

# ---------- MQTT event ----------
def on_connect(cli, userdata, flags, rc, props=None):
    print(f"✅ MQTT connected rc={rc}")
    cli.subscribe(CAMERA_TOPIC, qos=0)

def on_message(cli, userdata, msg):
    if msg.topic.startswith("robot/camera/"):
        handle_camera_part(msg.topic, msg.payload)

def mqtt_thread():
    global mqtt_cli
    mqtt_cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="flask_mqtt_face")
    mqtt_cli.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_cli.tls_set(cert_reqs=ssl.CERT_NONE)
    mqtt_cli.on_connect = on_connect
    mqtt_cli.on_message = on_message
    mqtt_cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_cli.loop_forever()

threading.Thread(target=mqtt_thread, daemon=True).start()

# ---------- Phát hiện khuôn mặt ----------
def detect_and_draw(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)

    faces = face_cascade.detectMultiScale(
        small, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60)
    )

    # Vẽ khung xanh quanh khuôn mặt
    for (x, y, w, h) in faces:
        x, y, w, h = int(x * 2), int(y * 2), int(w * 2), int(h * 2)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.putText(frame, "Face", (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    return frame

# ---------- API trả ảnh nhận dạng ----------
@app.route("/detected")
def detected():
    with frame_lock:
        f = None if latest_frame is None else latest_frame.copy()
    if f is None:
        img = 255 * np.ones((240, 320, 3), np.uint8)
        cv2.putText(img, "Loading...", (90, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        ok, jpeg = cv2.imencode(".jpg", img)
        return Response(jpeg.tobytes(), mimetype="image/jpeg")

    result = detect_and_draw(f)
    ok, jpeg = cv2.imencode(".jpg", result, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return Response(jpeg.tobytes(), mimetype="image/jpeg")

# ---------- Giao diện chính ----------
@app.route("/")
def index():
    html = f"""
    <html>
    <head>
      <title>Matthew Robot — Face + Voice</title>
      <style>
        body {{
          background:#111; color:#eee; text-align:center; font-family:sans-serif;
        }}
        h2 {{ color:#0ff; }}
        .grid {{
          display:flex; justify-content:center; gap:50px; flex-wrap:wrap; margin-top:30px;
        }}
        iframe, img {{
          border-radius:10px; border:2px solid #333; box-shadow:0 0 8px #000;
        }}
        button {{
          margin:10px; padding:10px 20px; font-size:16px; border:none;
          border-radius:6px; cursor:pointer; background:#0ff; color:#000;
        }}
        button:disabled {{ opacity:0.5; cursor:not-allowed; }}
        audio {{ margin-top:20px; }}
      </style>
    </head>
    <body>
      <h2>🤖 Matthew Robot — Face + Voice Interaction</h2>
      <div class="grid">
        <div>
          <h3>🎥 Live from ESP32-CAM</h3>
          <iframe src="{ESP32_STREAM_URL}" width="320" height="240" style="border:none;"></iframe>
        </div>
        <div>
          <h3>🧠 Detected Faces (from MQTT)</h3>
          <img id="det" src="/detected" width="320" height="240">
        </div>
      </div>

      <div style="margin-top:40px;">
        <h3>🎙️ Voice Interaction</h3>
        <button id="startBtn" onclick="startRecording()">🎤 Start Recording</button>
        <button id="stopBtn" onclick="stopRecording()" disabled>⏹️ Stop</button>
        <p id="status"></p>
        <audio id="audioPlayer" controls></audio>
      </div>

      <script>
        let mediaRecorder;
        let audioChunks = [];

        async function startRecording() {{
          try {{
            const stream = await navigator.mediaDevices.getUserMedia({{ audio: true }});
            mediaRecorder = new MediaRecorder(stream);
            audioChunks = [];

            mediaRecorder.ondataavailable = e => {{
              if (e.data.size > 0) audioChunks.push(e.data);
            }};

            mediaRecorder.onstop = async () => {{
              const audioBlob = new Blob(audioChunks, {{ type: 'audio/webm' }});
              const formData = new FormData();
              formData.append('audio', audioBlob, 'voice.webm');

              document.getElementById('status').innerText = "⏳ Uploading audio...";
              const res = await fetch('https://embeddedprogramming-healtheworldserver.up.railway.app/upload_audio', {{
                method: 'POST',
                body: formData
              }});

              if (!res.ok) {{
                document.getElementById('status').innerText = "❌ Upload failed.";
                return;
              }}

              const blob = await res.blob();
              const audioURL = URL.createObjectURL(blob);
              const player = document.getElementById('audioPlayer');
              player.src = audioURL;
              player.play();
              document.getElementById('status').innerText = "✅ Response audio received!";
            }};

            mediaRecorder.start();
            document.getElementById('status').innerText = "🎙️ Recording...";
            document.getElementById('startBtn').disabled = true;
            document.getElementById('stopBtn').disabled = false;
          }} catch (err) {{
            console.error(err);
            alert('Microphone access denied or error occurred.');
          }}
        }}

        function stopRecording() {{
          if (mediaRecorder && mediaRecorder.state !== "inactive") {{
            mediaRecorder.stop();
            document.getElementById('status').innerText = "Processing audio...";
            document.getElementById('startBtn').disabled = false;
            document.getElementById('stopBtn').disabled = true;
          }}
        }}

        function reloadDet() {{
          const img = document.getElementById('det');
          img.src = '/detected?t=' + new Date().getTime();
        }}
        setInterval(reloadDet, 300);
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
