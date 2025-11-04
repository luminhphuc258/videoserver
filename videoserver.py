# app.py
from flask import Flask, request, Response, jsonify, make_response, send_file
import cv2, numpy as np, time, ssl, json, threading, io
from threading import Lock
from paho.mqtt import client as mqtt

app = Flask(__name__)

# ===== MQTT (EMQX Cloud) =====
MQTT_HOST = "rfff7184.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
MQTT_USER = "robot_matthew"
MQTT_PASS = "29061992abCD!yesokmen"
SENSOR_SUB_TOPIC = "robot/sensor/#"
CMD_PUB_TOPIC    = "robot/cmd"

# ===== Shared states =====
latest_frame = None
latest_sensor = {"distance_cm": -1.0, "obstacle": False, "led": False, "ts": 0}
latest_ai = {"label": "", "obstacle": False, "ts": 0}

frame_lock = Lock()
sensor_lock = Lock()
ai_lock = Lock()

frames_in = 0
sensors_in = 0

mqtt_cli = None

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

# ---------- Nhận dạng & vẽ khung (demo) ----------
def detect_and_draw(frame):
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

# ---------- MJPEG (giữ nguyên nếu bạn cần xem full) ----------
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
                time.sleep(0.05)
        except GeneratorExit:
            app.logger.info("Client disconnected from /video")
        except Exception as e:
            app.logger.exception("Stream error: %s", e)

    headers = {"Cache-Control":"no-cache","Pragma":"no-cache","Connection":"keep-alive"}
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame", headers=headers)

# ---------- NEW: /snapshot trả 1 frame JPEG mới nhất ----------
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
    # tránh cache để luôn lấy khung mới
    resp.headers['Cache-Control'] = 'no-store'
    return resp

# ---------- Status tổng hợp ----------
@app.route("/status")
def status():
    with sensor_lock:
        s = dict(latest_sensor)
    with ai_lock:
        a = dict(latest_ai)
    return jsonify({"sensor": s, "ai": a, "frames_in": frames_in})

# ---------- Điều khiển ----------
@app.route("/move", methods=["POST"])
def move():
    global mqtt_cli
    direction = (request.args.get("dir", "") or "").lower()
    mapping = {"up":"tien","down":"lui","left":"trai","right":"phai"}
    cmd = mapping.get(direction)
    if not cmd:
        return jsonify({"ok": False, "error": "invalid dir"}), 400
    payload = json.dumps({"cmd": cmd, "ts": time.time()})
    try:
        if mqtt_cli is not None:
            mqtt_cli.publish(CMD_PUB_TOPIC, payload, qos=1, retain=False)
        app.logger.info(f"[CMD] {payload}")
        return jsonify({"ok": True, "sent": payload})
    except Exception as e:
        app.logger.exception("publish cmd error: %s", e)
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- Healthcheck ----------
@app.route("/healthz")
def healthz():
    return "ok", 200

# ---------- UI ----------
INDEX_HTML = """
<!doctype html>
<html lang="vi"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Matthew Robot Control Board</title>
<style>
  :root {
    --bg:#111; --card:#0d0d0d; --border:#222; --txt:#eee; --muted:#aaa;
    --btnW: 100px; --btnH: 60px;
  }
  *{box-sizing:border-box}
  body{
    font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
    background:var(--bg);color:var(--txt);margin:0;padding:16px;
  }
  .wrap{max-width:900px;margin:0 auto;display:flex;flex-direction:column;gap:12px}
  .card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px}
  .row{display:flex;justify-content:center;align-items:center}
  /* Top: camera 350x280 + nút reload */
  .camRow{display:flex;justify-content:center;align-items:center;gap:10px;flex-wrap:wrap}
  .cam{width:350px;height:280px;border-radius:10px;border:1px solid var(--border);background:#000;object-fit:contain}
  .btn{
    background:#1c1c1c;border:1px solid #333;border-radius:12px;
    padding:10px 14px;cursor:pointer;color:#eee;font-weight:600;
    transition:transform .05s ease;
  }
  .btn:active{transform:scale(0.98)}
  .btn:hover{border-color:#3d3d3d}
  .muted{color:var(--muted);font-size:12px;margin-top:6px;text-align:center}
  /* Middle: sensor badges */
  .stats{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
  .badge{border:1px solid #2c2c2c;background:#1c1c1c;border-radius:999px;padding:8px 12px}
  .big{font-size:20px;font-weight:700}
  /* Bottom: control pad (FLEX) */
  .padFlex{display:flex;flex-direction:column;gap:10px;align-items:center;justify-content:center}
  .padRow{display:flex;gap:10px;justify-content:center;align-items:center;flex-wrap:wrap}
  .btn.ctrl{
    width:var(--btnW); height:var(--btnH);
    display:flex; align-items:center; justify-content:center;
    padding:0; user-select:none;
  }
  .btn.stop{
    background:#2a1c1c; border-color:#533; 
  }
  .btn.stop:hover{border-color:#755}
  @media (max-width:420px){
    :root{ --btnW: 88px; --btnH: 56px; }
    .cam{width:300px;height:220px}
  }
</style></head><body>
<div class="wrap">

  <!-- ROW 1: CAM + Reload -->
  <div class="card">
    <div class="camRow">
      <img id="cam" class="cam" alt="cam">
      <div>
        <button class="btn" onclick="reloadCam()">🔄 Reload cam</button>
        <div id="camState" class="muted">Loading…</div>
      </div>
    </div>
  </div>

  <!-- ROW 2: SENSOR -->
  <div class="card">
    <h3>📡 Trạng thái cảm biến &amp; AI</h3>
    <div class="stats">
      <div class="badge">Khoảng cách: <span id="dist" class="big">--</span> cm</div>
      <div class="badge">Obstacle (ultra): <span id="obs">--</span></div>
      <div class="badge">LED: <span id="led">--</span></div>
      <div class="badge">AI obstacle: <span id="ai_obs">--</span></div>
      <div class="badge">AI label: <span id="ai_label">--</span></div>
    </div>
  </div>

  <!-- ROW 3: CONTROL -->
  <div class="card">
    <h3>Điều khiển</h3>
    <div class="padFlex">
      <div class="padRow">
        <button class="btn ctrl" id="btn-up"    onclick="sendRobot('up')">⬆️ Lên</button>
      </div>
      <div class="padRow">
        <button class="btn ctrl" id="btn-left"  onclick="sendRobot('left')">⬅️ Trái</button>
        <button class="btn ctrl stop" id="btn-stop"  onclick="sendRobot('stop')">⏹️ Dừng</button>
        <button class="btn ctrl" id="btn-right" onclick="sendRobot('right')">➡️ Phải</button>
      </div>
      <div class="padRow">
        <button class="btn ctrl" id="btn-down"  onclick="sendRobot('down')">⬇️ Xuống</button>
      </div>
    </div>
    <div id="msg" class="muted"></div>
  </div>

</div>

<script>
(() => {
  // ====== CONFIG: Python action server ======
  const PYTHON_SERVER = "https://mylocalpythonserver-mypythonserver.up.railway.app";
  const CMD_MAP = { up: "tien", down: "lui", left: "trai", right: "phai", stop: "yen" };

  // ====== SENSOR POLLING ======
  async function poll(){
    try{
      const r = await fetch('/status', {cache:'no-store'});
      const s = await r.json();
      const se = s.sensor || {};
      const ai = s.ai || {};
      document.getElementById('dist').textContent = (se.distance_cm>=0) ? se.distance_cm.toFixed(1) : 'timeout';
      document.getElementById('obs').textContent  = se.obstacle ? 'YES' : 'NO';
      document.getElementById('led').textContent  = se.led ? 'ON' : 'OFF';
      document.getElementById('ai_obs').textContent  = ai.obstacle ? 'YES' : 'NO';
      document.getElementById('ai_label').textContent= ai.label || '--';
    }catch(e){
      // silent
    }
    setTimeout(poll, 300);
  }
  poll();

  // ====== CONTROL (call Python server endpoints) ======
  async function sendRobot(dir){
    const el = document.getElementById('msg');
    const endpoint = CMD_MAP[dir];
    if(!endpoint){
      el.textContent = "Lỗi: lệnh không hợp lệ";
      return;
    }
    try{
      const r = await fetch(PYTHON_SERVER + "/" + endpoint, {
        method: "POST",
        mode: "cors",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({ source: "video_ui", ts: Date.now() })
      });
      if(!r.ok){
        const txt = await r.text().catch(()=> "");
        el.textContent = "Lỗi gửi lệnh (" + r.status + "): " + (txt || "unknown");
        return;
      }
      el.textContent = "✅ Đã gửi: " + dir.toUpperCase() + " → /" + endpoint;
    }catch(e){
      el.textContent = "Lỗi mạng khi gửi lệnh: " + (e && e.message ? e.message : e);
    }
  }
  // export
  window.sendRobot = sendRobot;

  // ====== CAMERA BUFFERED PLAYBACK ======
  let TARGET_BUFFER = 3;    // có thể auto điều chỉnh
  let PLAY_INTERVAL = 70;   // ms/frame
  let buf = [];             // list blob URLs
  let playing = false;
  let stopFlag = false;

  const camImg   = document.getElementById('cam');
  const camState = document.getElementById('camState');

  function revokeAll(){
    for(const u of buf){ URL.revokeObjectURL(u); }
    buf = [];
  }

  async function fetchOne(){
    const res = await fetch('/snapshot?ts=' + Date.now(), {cache:'no-store'});
    if(!res.ok) throw new Error('no frame');
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    buf.push(url);
  }

  async function fillBuffer(){
    camState.textContent = 'Loading…';
    let miss = 0;
    while(!stopFlag && buf.length < TARGET_BUFFER){
      try {
        await fetchOne();
        miss = 0;
      } catch(e){
        miss++;
        if (miss >= 3 && TARGET_BUFFER < 6) TARGET_BUFFER++;
        await new Promise(r => setTimeout(r, 120));
      }
    }
    // mạng ổn định → hạ buffer để giảm trễ
    if (miss === 0 && TARGET_BUFFER > 2) TARGET_BUFFER--;
  }

  async function playBuffer(){
    playing = true;
    camState.textContent = 'Playing';
    while(!stopFlag && buf.length){
      const url = buf.shift();
      camImg.src = url;
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      await new Promise(r => setTimeout(r, PLAY_INTERVAL));
    }
    playing = false;
  }

  async function loopCam(){
    stopFlag = false;
    revokeAll();
    while(!stopFlag){
      await fillBuffer();
      if(stopFlag) break;
      await playBuffer();
    }
    camState.textContent = 'Stopped';
  }

  function reloadCam(){
    stopFlag = true;
    revokeAll();
    camImg.removeAttribute('src');
    camState.textContent = 'Loading…';
    setTimeout(loopCam, 50);
  }
  // export cho nút Reload
  window.reloadCam = reloadCam;

  // tự khởi động vòng gom/phát khi mở trang
  reloadCam();
})();
</script>

</body></html>
"""


#==================end html==========
@app.route("/")
def index():
    return make_response(INDEX_HTML)

# ---------- MQTT subscriber ----------
def on_connect(cli, userdata, flags, rc, properties=None):
    app.logger.info(f"MQTT connected rc={rc}; sub {SENSOR_SUB_TOPIC}")
    cli.subscribe(SENSOR_SUB_TOPIC, qos=1)

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
    global mqtt_cli
    mqtt_cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="server-subscriber")
    mqtt_cli.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_cli.tls_set(cert_reqs=ssl.CERT_REQUIRED)
    mqtt_cli.on_connect = on_connect
    mqtt_cli.on_message = on_message
    mqtt_cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_cli.loop_forever()

threading.Thread(target=mqtt_thread, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
