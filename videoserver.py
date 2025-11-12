from flask import Flask, Response, render_template_string
import cv2, time, ssl, json, threading, base64, numpy as np
from threading import Lock
from paho.mqtt import client as mqtt

app = Flask(__name__)
# Tải bộ nhận dạng khuôn mặt Haar Cascade
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
# ===== MQTT config =====
MQTT_HOST = "rfff7184.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
MQTT_USER = "robot_matthew"
MQTT_PASS = "29061992abCD!yesokmen"
CAMERA_TOPIC = "robot/camera/#"

mqtt_cli = None
latest_frame = None
frame_lock = Lock()
camera_buffer = {}

# ===== ESP32 HTTP livestream URL =====
ESP32_STREAM_URL = "http://192.168.100.134:81/stream"  # ⚠️ đổi IP này theo ESP32 của bạn

# ---------- MQTT handlers ----------
def handle_camera_part(topic, payload):
    """Ghép chuỗi Base64 và decode thành ảnh OpenCV."""
    global latest_frame
    try:
        part_key = topic.split("/")[-1]
        frame_id = "main"

        if frame_id not in camera_buffer:
            camera_buffer[frame_id] = b""
        camera_buffer[frame_id] += payload

        # Khi đủ dữ liệu hoặc tới part cuối → decode ảnh
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
        print("❌ handle_camera_part error:", e)


def on_connect(cli, userdata, flags, rc, props=None):
    print(f"✅ MQTT connected rc={rc}")
    cli.subscribe(CAMERA_TOPIC, qos=0)


def on_message(cli, userdata, msg):
    if msg.topic.startswith("robot/camera/"):
        handle_camera_part(msg.topic, msg.payload)

# ---------- Detect & Draw ----------
# ---------- Detect face & draw ----------
def detect_and_draw(frame):
    """Phát hiện khuôn mặt và vẽ khung xanh."""
    # Chuyển BGR -> GRAY để detect nhanh hơn
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Giảm kích thước để tăng tốc (detect nhanh gấp ~3-4 lần)
    small = cv2.resize(gray, (0, 0), fx=0.5, fy=0.5)

    # Phát hiện khuôn mặt
    faces = face_cascade.detectMultiScale(small, scaleFactor=1.2, minNeighbors=5, minSize=(60, 60))

    # Nếu có khuôn mặt, vẽ khung xanh (phóng lại to bằng kích thước thật)
    for (x, y, w, h) in faces:
        x, y, w, h = int(x * 2), int(y * 2), int(w * 2), int(h * 2)
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)
        cv2.putText(frame, "Face", (x, y - 10), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 255, 0), 2)
    return frame


def mqtt_thread():
    """Luồng MQTT subscriber chạy nền."""
    global mqtt_cli
    mqtt_cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="flask_mqtt_video")
    mqtt_cli.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_cli.tls_set(cert_reqs=ssl.CERT_NONE)
    mqtt_cli.on_connect = on_connect
    mqtt_cli.on_message = on_message
    mqtt_cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_cli.loop_forever()


# Chạy MQTT trong luồng riêng
threading.Thread(target=mqtt_thread, daemon=True).start()


# ---------- Endpoint trả ảnh nhận dạng ----------
@app.route("/detected")
def detected():
    start = time.time()
    with frame_lock:
        f = None if latest_frame is None else latest_frame.copy()

    # Nếu chưa có frame nào, trả ảnh “Loading”
    if f is None:
        img = 255 * np.ones((240, 320, 3), np.uint8)
        cv2.putText(img, "Loading...", (90, 130), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 0, 0), 2)
        ok, jpeg = cv2.imencode(".jpg", img)
        return Response(jpeg.tobytes(), mimetype='image/jpeg')

    # Áp dụng phát hiện khuôn mặt
    result = detect_and_draw(f)

    # Giới hạn tốc độ xử lý (tối thiểu 0.3 giây/frame)
    elapsed = time.time() - start
    if elapsed < 0.3:
        time.sleep(0.3 - elapsed)

    # Mã hóa JPEG và gửi trả
    ok, jpeg = cv2.imencode(".jpg", result, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return Response(status=500)
    return Response(jpeg.tobytes(), mimetype='image/jpeg')


# ---------- Giao diện web ----------
@app.route("/")
def index():
    html = '''
    <html>
    <head>
      <title>Matthew Robot Dashboard</title>
      <style>
        body {
          background:#111;color:#eee;text-align:center;
          font-family:sans-serif;margin-top:30px;
        }
        .box {
          display:flex;justify-content:center;gap:50px;
          align-items:flex-start;flex-wrap:wrap;
        }
        img {
          border-radius:10px;border:2px solid #333;
          box-shadow:0 0 8px #000;
        }
        h3 {color:#0ff}
      </style>
    </head>
    <body>
      <h2>🤖 Matthew Robot — Live & AI View</h2>

      <div class="box">
        <div>
          <h3>🎥 Live from ESP32-CAM</h3>
          <iframe src="''' + ESP32_STREAM_URL + '''" width="320" height="240"
                  style="border:none;border-radius:10px;overflow:hidden;">
          </iframe>
        </div>

        <div>
          <h3>🧠 AI Detected Frame (from MQTT)</h3>
          <img id="det" src="/detected" width="320" height="240">
        </div>
      </div>

      <script>
        function refreshDetected() {
          const img = document.getElementById('det');
          img.src = '/detected?t=' + new Date().getTime();
        }
        setInterval(refreshDetected, 500); // update mỗi 0.5 giây
      </script>
    </body>
    </html>
    '''
    return render_template_string(html)


# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
