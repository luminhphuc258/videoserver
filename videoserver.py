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

# ESP32-CAM livestream URL (thay IP theo Serial ESP32 của bạn)
ESP32_STREAM_URL = "http://192.168.100.134:81/stream"

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

# ---------- Endpoint trả ảnh nhận dạng ----------
@app.route("/detected")
def detected():
    with frame_lock:
        f = None if latest_frame is None else latest_frame.copy()
    if f is None:
        return Response(status=404)
    ok, jpeg = cv2.imencode(".jpg", f, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return Response(status=500)
    return Response(jpeg.tobytes(), mimetype='image/jpeg')

# ---------- UI ----------
@app.route("/")
def index():
    html = f"""
    <html>
    <head>
      <title>Matthew Robot Dashboard</title>
      <style>
        body {{
          background:#111;color:#eee;text-align:center;
          font-family:sans-serif;margin-top:30px;
        }}
        .box {{
          display:flex;justify-content:center;gap:50px;
          align-items:flex-start;flex-wrap:wrap;
        }}
        img {{
          border-radius:10px;border:2px solid #333;
          box-shadow:0 0 8px #000;
        }}
        h3 {{color:#0ff}}
      </style>
    </head>
    <body>
      <h2>🤖 Matthew Robot — Live & AI View</h2>

      <div class="box">
        <div>
          <h3>🎥 Live from ESP32-CAM</h3>
          <iframe src="{ESP32_STREAM_URL}" width="320" height="240"
                  style="border:none;border-radius:10px;overflow:hidden;">
          </iframe>
        </div>

        <div>
          <h3>🧠 AI Detected Frame (from MQTT)</h3>
          <img id="det" src="/detected" width="320" height="240">
        </div>
      </div>

      <p id="status"></p>

      <script>
        async function updateStatus(){{
          const r = await fetch('/status');
          const d = await r.json();
          document.getElementById('status').innerText =
            `📏 Distance: ${'{:.1f}'.format(latest_sensor['distance_cm']) if 'distance_cm' in latest_sensor else 'N/A'} cm | Obstacle: ${'{latest_sensor['obstacle'] if 'obstacle' in latest_sensor else 'N/A'}`}
        }}

        function refreshDetected(){{
          const img = document.getElementById('det');
          img.src = '/detected?t=' + new Date().getTime();
        }}

        setInterval(updateStatus, 1000);
        setInterval(refreshDetected, 500);  // cập nhật khung nhận dạng 2 FPS
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
