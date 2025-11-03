from flask import Flask, request, Response, jsonify
import cv2
import numpy as np
import time
from threading import Lock

app = Flask(__name__)

latest_frame = None
latest_sensor = {"distance_cm": -1.0, "obstacle": False, "led": False, "ts": 0}
latest_ai = {"label": "", "obstacle": False, "ts": 0}

frame_lock = Lock()
sensor_lock = Lock()
ai_lock = Lock()

# ---------- Nhận ảnh từ ESP32 ----------
@app.route("/upload_frame", methods=["POST"])
def upload_frame():
    global latest_frame
    data = request.data
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        return "Bad image", 400
    with frame_lock:
        latest_frame = frame
    return "OK", 200

# ---------- Nhận sensor từ ESP32 ----------
@app.route("/sensor", methods=["POST"])
def sensor():
    global latest_sensor
    js = request.get_json(silent=True) or {}
    d  = float(js.get("distance_cm", -1))
    ob = bool(js.get("obstacle", False))
    le = bool(js.get("led", False))
    with sensor_lock:
        latest_sensor = {"distance_cm": d, "obstacle": ob, "led": le, "ts": time.time()}
    return "OK", 200

# ---------- Demo nhận dạng & vẽ khung ----------
def detect_and_draw(frame):
    """
    Thay bằng model thật (YOLO/…):
      - chạy detector → danh sách bbox (x,y,w,h,label,score)
      - vẽ rectangle + label
      - cập nhật latest_ai
    Ở đây: demo contour lớn coi như 'obstacle'.
    """
    out = frame.copy()
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 64, 128)
    cnts, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    found = False
    label = ""
    for c in cnts:
        x,y,w,h = cv2.boundingRect(c)
        if w*h < 8000:    # bỏ nhỏ quá (tùy chỉnh)
            continue
        found = True
        label = "obstacle"
        cv2.rectangle(out, (x,y), (x+w, y+h), (0,255,0), 2)
        cv2.putText(out, label, (x, max(0, y-6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
        # vẽ 1-2 cái là đủ minh họa
        break

    with ai_lock:
        latest_ai["label"] = label if found else ""
        latest_ai["obstacle"] = bool(found)
        latest_ai["ts"] = time.time()

    return out

# ---------- Stream video sau khi đã vẽ bbox ----------
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
                    yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' +
                           jpeg.tobytes() + b'\r\n')
            time.sleep(0.03)  # ~30fps upper bound (thực tế phụ thuộc upload)
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

# ---------- Status tổng hợp ----------
@app.route("/status")
def status():
    with sensor_lock:
        s = dict(latest_sensor)
    with ai_lock:
        a = dict(latest_ai)
    return jsonify({
        "sensor": s,
        "ai": a
    })

# ---------- UI trang web ----------
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
  <div class="card">
    <img src="/video" />
  </div>

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
    const r = await fetch('/status');
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
    return INDEX_HTML

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
