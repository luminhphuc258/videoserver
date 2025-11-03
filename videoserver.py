# app.py
from flask import Flask, request, Response, jsonify, make_response
import cv2, numpy as np, time, ssl, json, threading
from threading import Lock
from paho.mqtt import client as mqtt

app = Flask(__name__)

# ===== MQTT (EMQX Cloud) =====
MQTT_HOST = "rfff7184.ala.us-east-1.emqxsl.com"  # <== Thay bằng Address của bạn
MQTT_PORT = 8883
MQTT_USER = "robot_matthew"                             # <== Username bạn tạo
MQTT_PASS = "29061992abCD!yesokmen"                 # <== Password bạn tạo
MQTT_TOPIC = "robot/sensor/#"                      # nhận mọi thiết bị

# ===== Shared states =====
latest_frame = None
latest_sensor = {"distance_cm": -1.0, "obstacle": False, "led": False, "ts": 0}
latest_ai = {"label": "", "obstacle": False, "ts": 0}

frame_lock = Lock()
sensor_lock = Lock()
ai_lock = Lock()

frames_in = 0
sensors_in = 0

# ---------- Upload JPEG frame từ ESP32-CAM ----------
@app.route("/upload_frame", methods=["POST"])
def upload_frame():
    global latest_frame, frames_in
    data = request.data
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        app.logger.warning("Bad image")
        return "Bad image", 400
    with frame_lock:
        latest_frame = frame
    frames_in += 1
    if frames_in % 20 == 0:
        app.logger.info(f"/upload_frame ok, total={frames_in}")
    return "OK", 200

# ---------- (Demo) Nhận dạng & vẽ khung ----------
def detect_and_draw(frame):
    """
    Demo: coi contour lớn là 'obstacle'.
    Thay bằng model thực tế (YOLO/...) nếu muốn.
    """
    out = frame.copy()
    gray = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 64, 128)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    found = False
    label = ""
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < 8000:
            continue
        found = True
        label = "obstacle"
        cv2.rectangle(out, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(out, label, (x, max(0, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        break

    with ai_lock:
        latest_ai["label"] = label if found else ""
        latest_ai["obstacle"] = bool(found)
        latest_ai["ts"] = time.time()
    return out

# ---------- Stream MJPEG ảnh đã vẽ ----------
@app.route("/video")
def video_feed():
    def gen():
        try:
            while True:
                with frame_lock:
                    f = None if latest_frame is None else latest_frame.copy()
                if f is not None:
                    drawn = detect_and_draw(f)
                    ok, jpeg = cv2.imencode(".jpg", drawn, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if ok:
                        data = jpeg.tobytes()
                        yield (b"--frame\r\n"
                               b"Content-Type: image/jpeg\r\n"
                               b"Content-Length: " + str(len(data)).encode() + b"\r\n\r\n" +
                               data + b"\r\n")
                time.sleep(0.05)  # ~20 fps upper bound
        except GeneratorExit:
            app.logger.info("Client disconnected from /video")
        except Exception as e:
            app.logger.exception("Stream error: %s", e)

    headers = {"Cache-Control":"no-cache","Pragma":"no-cache","Connection":"keep-alive"}
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame", headers=headers)

# ---------- Status tổng hợp ----------
@app.route("/status")
def status():
    with sensor_lock:
        s = dict(latest_sensor)
    with ai_lock:
        a = dict(latest_ai)
    return jsonify({"sensor": s, "ai": a, "frames_in": frames_in})

# ---------- Healthcheck ----------
@app.route("/healthz")
def healthz():
    return "ok", 200

# ---------- UI ----------
INDEX_HTML = """
<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Robot Live • Video + Sensor</title>
<style>
  body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#111;color:#eee;margin:0;padding:16px;text-align:center}
  .wrap{max-width:900px;margin:0 auto}
  .card{background:#0d0d0d;border:1px solid #222;border-radius:12px;padding:12px;margin:10px auto}
  img{width:100%;max-width:860px;border-radius:10px;border:1px solid #222;background:#000}
  .stats{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
  .badge{border:1px solid #2c2c2c;background:#1c1c1c;border-radius:999px;padding:6px 10px}
  .big{font-size:20px;font-weight:700}
</style></head><body>
<div class="wrap">
  <h2>📹 Video đã nhận dạng (đã khoanh đối tượng)</h2>
  <div class="card"><img src="/video" /></div>

  <div class="card">
    <h3>📡 Trạng thái cảm biến & AI</h3>
    <div class="stats">
      <div class="badge">Khoảng cách: <span id="dist" class="big">--</span> cm</div>
      <div class="badge">Obstacle (ultra): <span id="obs">--</span></div>
      <div class="badge">LED: <span id="led">--</span></div>
      <div class="badge">AI obstacle: <span id="ai_obs">--</span></div>
      <div class="badge">AI label: <span id="ai_label">--</span></div>
    </div>
  </div>
</div>
<script>
async function poll(){
  try{
    const r = await fetch('/status', {cache:'no-store'});
    const s = await r.json();
    const se = s.sensor || {};
    const ai = s.ai || {};
    document.getElementById('dist').textContent = (se.distance_cm>=0)?se.distance_cm.toFixed(1):'timeout';
    document.getElementById('obs').textContent  = se.obstacle ? 'YES' : 'NO';
    document.getElementById('led').textContent  = se.led ? 'ON' : 'OFF';
    document.getElementById('ai_obs').textContent  = ai.obstacle ? 'YES' : 'NO';
    document.getElementById('ai_label').textContent= ai.label || '--';
  }catch(e){}
  setTimeout(poll, 300);
}
poll();
</script>
</body></html>
"""
@app.route("/")
def index():
    return make_response(INDEX_HTML)

# ---------- MQTT subscriber (chạy nền) ----------
def on_connect(cli, userdata, flags, rc, properties=None):
    app.logger.info(f"MQTT connected rc={rc}; sub {MQTT_TOPIC}")
    cli.subscribe(MQTT_TOPIC, qos=1)

def on_message(cli, userdata, msg):
    global latest_sensor, sensors_in
    try:
        js = json.loads(msg.payload.decode())
        d  = float(js.get("distance_cm", -1))
        ob = bool(js.get("obstacle", False))
        le = bool(js.get("led", False))
        with sensor_lock:
            latest_sensor = {"distance_cm": d, "obstacle": ob, "led": le, "ts": time.time()}
        sensors_in += 1
        if sensors_in % 10 == 0:
            app.logger.info(f"sensor #{sensors_in} d={d:.1f} ob={ob}")
    except Exception as e:
        app.logger.exception("MQTT parse error: %s", e)

def mqtt_thread():
    cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="server-subscriber")
    cli.username_pw_set(MQTT_USER, MQTT_PASS)
    cli.tls_set(cert_reqs=ssl.CERT_REQUIRED)  # dùng CA hệ thống; có file CA thì truyền ca_certs
    cli.on_connect = on_connect
    cli.on_message = on_message
    cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    cli.loop_forever()

threading.Thread(target=mqtt_thread, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
