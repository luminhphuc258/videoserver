from flask import Flask, request, Response, jsonify, make_response, send_file
import cv2, numpy as np, time, ssl, json, threading, io, base64
from threading import Lock
from paho.mqtt import client as mqtt

app = Flask(__name__)

# ===== MQTT (EMQX Cloud) =====
MQTT_HOST = "rfff7184.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
MQTT_USER = "robot_matthew"
MQTT_PASS = "29061992abCD!yesokmen"
SENSOR_SUB_TOPIC = "robot/sensor/#"
CAMERA_SUB_TOPIC = "robot/camera/#"
CMD_PUB_TOPIC    = "robot/cmd"

# ===== Shared states =====
latest_frame = None
latest_sensor = {"distance_cm": -1.0, "obstacle": False, "led": False, "ts": 0}
latest_ai = {"label": "", "obstacle": False, "ts": 0}
frames_in = 0
sensors_in = 0

# ===== Locks =====
frame_lock = Lock()
sensor_lock = Lock()
ai_lock = Lock()

mqtt_cli = None
camera_buffer = {}   # temporary storage for multi-part frames

# ---------- Nhận ảnh từ MQTT (Base64) ----------
def handle_camera_part(topic, payload):
    global latest_frame, frames_in
    try:
        # Lấy số part
        part_key = topic.split("/")[-1]   # part0, part1,...
        frame_id = "current"              # (có thể mở rộng nếu có nhiều cam)

        if frame_id not in camera_buffer:
            camera_buffer[frame_id] = ""

        # Ghép chuỗi base64
        camera_buffer[frame_id] += payload.decode()

        # Nếu part số 9 là cuối cùng, hoặc dài >100k → decode
        if len(camera_buffer[frame_id]) > 80000 or part_key.endswith("part9"):
            b64_data = camera_buffer[frame_id]
            del camera_buffer[frame_id]
            img_data = base64.b64decode(b64_data)
            nparr = np.frombuffer(img_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if frame is not None:
                with frame_lock:
                    latest_frame = frame
                frames_in += 1
                if frames_in % 5 == 0:
                    app.logger.info(f"📸 MQTT frame #{frames_in} ok ({len(img_data)} bytes)")
    except Exception as e:
        app.logger.exception("❌ handle_camera_part error: %s", e)

# ---------- Nhận sensor ----------
def handle_sensor_message(js):
    global latest_sensor, sensors_in
    try:
        d = float(js.get("distance_cm", -1))
        ob = bool(js.get("obstacle", False))
        le = bool(js.get("led", False))
        with sensor_lock:
            latest_sensor = {"distance_cm": d, "obstacle": ob, "led": le, "ts": time.time()}
        sensors_in += 1
        if sensors_in % 10 == 0:
            app.logger.info(f"📡 Sensor #{sensors_in} d={d:.1f} ob={ob}")
    except Exception as e:
        app.logger.exception("❌ handle_sensor_message error: %s", e)

# ---------- MQTT events ----------
def on_connect(cli, userdata, flags, rc, properties=None):
    app.logger.info(f"✅ MQTT connected rc={rc}; sub {SENSOR_SUB_TOPIC}, {CAMERA_SUB_TOPIC}")
    cli.subscribe(SENSOR_SUB_TOPIC, qos=1)
    cli.subscribe(CAMERA_SUB_TOPIC, qos=0)

def on_message(cli, userdata, msg):
    try:
        topic = msg.topic
        if topic.startswith("robot/sensor/"):
            js = json.loads(msg.payload.decode())
            handle_sensor_message(js)
        elif topic.startswith("robot/camera/"):
            handle_camera_part(topic, msg.payload)
    except Exception as e:
        app.logger.exception("❌ MQTT on_message error: %s", e)

def mqtt_thread():
    global mqtt_cli
    mqtt_cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="server-subscriber")
    mqtt_cli.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_cli.tls_set(cert_reqs=ssl.CERT_NONE)
    mqtt_cli.on_connect = on_connect
    mqtt_cli.on_message = on_message
    mqtt_cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_cli.loop_forever()

# ---------- Detect & Draw ----------
def detect_and_draw(frame):
    out = frame.copy()
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 64, 128)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = False
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < 8000: continue
        found = True
        cv2.rectangle(out, (x, y), (x+w, y+h), (0,255,0), 2)
        break
    with ai_lock:
        latest_ai["label"] = "obstacle" if found else ""
        latest_ai["obstacle"] = found
        latest_ai["ts"] = time.time()
    return out

# ---------- Snapshot & Video ----------
@app.route("/snapshot")
def snapshot():
    with frame_lock:
        f = None if latest_frame is None else latest_frame.copy()
    if f is None:
        return "no frame", 404
    drawn = detect_and_draw(f)
    ok, jpeg = cv2.imencode(".jpg", drawn, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok:
        return "encode fail", 500
    bio = io.BytesIO(jpeg.tobytes())
    resp = send_file(bio, mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'no-store'
    return resp

@app.route("/video")
def video_feed():
    def gen():
        while True:
            with frame_lock:
                f = None if latest_frame is None else latest_frame.copy()
            if f is not None:
                drawn = detect_and_draw(f)
                ok, jpeg = cv2.imencode(".jpg", drawn, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                if ok:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" +
                           jpeg.tobytes() + b"\r\n")
            time.sleep(0.05)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

# ---------- Health ----------
@app.route("/healthz")
def healthz():
    return "ok", 200

@app.route("/status")
def status():
    with sensor_lock: s = dict(latest_sensor)
    with ai_lock: a = dict(latest_ai)
    return jsonify({"sensor": s, "ai": a, "frames_in": frames_in})

# ---------- UI ----------
@app.route("/")
def index():
    return "<h2>✅ MQTT Video Server running — visit /video or /snapshot</h2>"

# ---------- Start MQTT Thread ----------
threading.Thread(target=mqtt_thread, daemon=True).start()

# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
