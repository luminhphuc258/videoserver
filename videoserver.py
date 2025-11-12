from flask import Flask, Response, render_template_string, jsonify
import cv2, time, ssl, json, threading, numpy as np
from paho.mqtt import client as mqtt
from threading import Lock

app = Flask(__name__)

# ===== MQTT Config =====
MQTT_HOST = "rfff7184.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
MQTT_USER = "robot_matthew"
MQTT_PASS = "29061992abCD!yesokmen"
CAMERA_TOPIC = "robot/camera/#"
SENSOR_TOPIC = "robot/sensor/#"

mqtt_cli = None
latest_frame = None
latest_detected = None
frame_lock = Lock()
detect_lock = Lock()
camera_buffer = {}

# ===== ESP32 Stream URL =====
ESP32_STREAM_URL = "http://192.168.100.134:81/stream"

# ===== Load face detection model =====
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

# ---------- Handle MQTT camera data ----------
def handle_camera_part(topic, payload):
    global latest_frame
    try:
        part_key = topic.split("/")[-1]
        frame_id = "main"
        if frame_id not in camera_buffer:
            camera_buffer[frame_id] = b""
        camera_buffer[frame_id] += payload

        # Decode when long enough or last part
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

# ---------- Handle sensor data ----------
def handle_sensor(payload):
    pass  # (hiện tại không dùng)

def on_connect(cli, userdata, flags, rc, props=None):
    print(f"✅ MQTT connected rc={rc}")
    cli.subscribe(CAMERA_TOPIC, qos=0)
    cli.subscribe(SENSOR_TOPIC, qos=1)

def on_message(cli, userdata, msg):
    if msg.topic.startswith("robot/camera/"):
        handle_camera_part(msg.topic, msg.payload)

def mqtt_thread():
    global mqtt_cli
    mqtt_cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="flask_mqtt_video")
    mqtt_cli.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_cli.tls_set(cert_reqs=ssl.CERT_NONE)
    mqtt_cli.on_connect = on_connect
    mqtt_cli.on_message = on_message
    mqtt_cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_cli.loop_forever()

# ---------- AI Detection Thread ----------
def detect_and_draw(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)
    faces = face_cascade.detectMultiScale(small, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))

    for (x, y, w, h) in faces:
        x, y, w, h = int(x * 2), int(y * 2), int(w * 2), int(h * 2)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.putText(frame, "Face", (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
    return frame

def ai_thread():
    global latest_detected
    while True:
        with frame_lock:
            f = None if latest_frame is None else latest_frame.copy()
        if f is None:
            time.sleep(0.05)
            continue
        result = detect_and_draw(f)
        with detect_lock:
            latest_detected = result
        time.sleep(0.05)  # ~20 FPS

# ---------- MJPEG Stream from ESP32 ----------
def gen_esp32_stream():
    cap = cv2.VideoCapture(ESP32_STREAM_URL)
    if not cap.isOpened():
        print("❌ Cannot open ESP32 stream")
        return
    print("🎥 Connected to ESP32 stream!")

    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if ok:
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
        time.sleep(0.03)

@app.route("/video")
def video_feed():
    return Response(gen_esp32_stream(), mimetype="multipart/x-mixed-replace; boundary=frame")

# ---------- AI Detected Frame ----------
@app.route("/detected")
def detected():
    with detect_lock:
        f = None if latest_detected is None else latest_detected.copy()
    if f is None:
        img = 255 * np.ones((240, 320, 3), np.uint8)
        cv2.putText(img, "Loading...", (80, 130),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2)
        ok, jpeg = cv2.imencode(".jpg", img)
        return Response(jpeg.tobytes(), mimetype="image/jpeg")
    ok, jpeg = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    return Response(jpeg.tobytes(), mimetype="image/jpeg")

# ---------- Web UI ----------
@app.route("/")
def index():
    html = """
    <html>
    <head>
      <title>Matthew Robot — Live & AI View</title>
      <style>
        body {background:#111;color:#eee;text-align:center;font-family:sans-serif;}
        h2 {color:#00ffff;}
        .grid {display:flex;justify-content:center;gap:40px;margin-top:30px;}
        img {border-radius:12px;border:2px solid #333;width:400px;height:300px;object-fit:cover;}
        .label {font-size:20px;margin:10px;color:#0ff;}
      </style>
    </head>
    <body>
      <h2>🤖 Matthew Robot — Live & AI View</h2>
      <div class="grid">
        <div>
          <div class="label">🎥 Live from ESP32-CAM</div>
          <img src="/video" />
        </div>
        <div>
          <div class="label">🧠 AI Detected Frame (from MQTT)</div>
          <img id="det" src="/detected" />
        </div>
      </div>
      <script>
        async function reloadDet(){
          const img = document.getElementById('det');
          img.src = '/detected?t=' + new Date().getTime();
        }
        setInterval(reloadDet, 200); // refresh 5 FPS
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

# ---------- Threads ----------
threading.Thread(target=mqtt_thread, daemon=True).start()
threading.Thread(target=ai_thread, daemon=True).start()

# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
