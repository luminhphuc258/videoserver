from flask import Flask, Response, jsonify, render_template_string
import cv2, time, ssl, json, threading, base64, numpy as np
from threading import Lock
from paho.mqtt import client as mqtt

app = Flask(__name__)

# ===== MQTT config =====
MQTT_HOST = "rfff7184.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
MQTT_USER = "robot_matthew"
MQTT_PASS = "29061992abCD!yesokmen"
CAMERA_TOPIC = "robot/camera/#"
SENSOR_TOPIC = "robot/sensor/#"

mqtt_cli = None
latest_sensor = {"distance_cm": -1.0, "obstacle": False, "led": False, "ts": 0}
latest_frame = None
frame_lock = Lock()
camera_buffer = {}  # tạm ghép chuỗi Base64 nhiều phần

# ---------- MQTT callbacks ----------
def handle_camera_part(topic, payload):
    global latest_frame
    try:
        part_key = topic.split("/")[-1]
        frame_id = "main"
        if frame_id not in camera_buffer:
            camera_buffer[frame_id] = b""

        camera_buffer[frame_id] += payload
        # Nếu chuỗi dài > 60KB hoặc tới part9 thì decode
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

def handle_sensor(payload):
    global latest_sensor
    try:
        js = json.loads(payload.decode())
        latest_sensor = js
    except Exception as e:
        print("Sensor parse error:", e)

def on_connect(cli, userdata, flags, rc, props=None):
    print(f"✅ MQTT connected rc={rc}")
    cli.subscribe(CAMERA_TOPIC, qos=0)
    cli.subscribe(SENSOR_TOPIC, qos=1)

def on_message(cli, userdata, msg):
    if msg.topic.startswith("robot/camera/"):
        handle_camera_part(msg.topic, msg.payload)
    elif msg.topic.startswith("robot/sensor/"):
        handle_sensor(msg.payload)

def mqtt_thread():
    global mqtt_cli
    mqtt_cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="flask_mqtt_video")
    mqtt_cli.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_cli.tls_set(cert_reqs=ssl.CERT_NONE)
    mqtt_cli.on_connect = on_connect
    mqtt_cli.on_message = on_message
    mqtt_cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_cli.loop_forever()

threading.Thread(target=mqtt_thread, daemon=True).start()

# ---------- MJPEG stream from MQTT frames ----------
def gen_frames():
    print("🎥 Streaming frames from MQTT...")
    while True:
        with frame_lock:
            frame = None if latest_frame is None else latest_frame.copy()
        if frame is not None:
            # Giảm kích thước cho mượt hơn
            frame_small = cv2.resize(frame, (150, 150))
            ok, jpeg = cv2.imencode(".jpg", frame_small, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            if ok:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" +
                       jpeg.tobytes() + b"\r\n")
        time.sleep(0.05)  # ~20 FPS

@app.route("/video")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

# ---------- UI ----------
@app.route("/")
def index():
    html = """
    <html>
    <head>
      <title>Matthew Robot Mini Stream</title>
      <style>
        body {background:#111;color:#eee;text-align:center;font-family:sans-serif;}
        img {border-radius:8px;border:2px solid #444;}
      </style>
    </head>
    <body>
      <h3>🤖 Camera live from MQTT</h3>
      <img src="/video" width="150" height="150">
      <p id="status"></p>
      <script>
        async function updateStatus(){
          const res = await fetch('/status');
          const data = await res.json();
          document.getElementById('status').innerText =
            `Distance: ${data.distance_cm} cm | Obstacle: ${data.obstacle}`;
        }
        setInterval(updateStatus, 1000);
      </script>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/status")
def status():
    return jsonify(latest_sensor)

# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
