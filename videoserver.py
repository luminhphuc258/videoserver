from flask import Flask, Response, jsonify, render_template_string
import cv2, time, ssl, json, threading
from paho.mqtt import client as mqtt

app = Flask(__name__)

# ===== MQTT (EMQX Cloud) =====
MQTT_HOST = "rfff7184.ala.us-east-1.emqxsl.com"
MQTT_PORT = 8883
MQTT_USER = "robot_matthew"
MQTT_PASS = "29061992abCD!yesokmen"
SENSOR_SUB_TOPIC = "robot/sensor/#"
CMD_PUB_TOPIC    = "robot/cmd"

mqtt_cli = None
latest_sensor = {"distance_cm": -1.0, "obstacle": False, "led": False, "ts": 0}

# ===== ESP32 STREAM URL (HTTP) =====
# 👉 Thay IP này bằng IP in trong Serial của bạn
ESP32_STREAM_URL = "http://192.168.100.134:81/stream"

# ---------- MQTT callbacks ----------
def on_connect(cli, userdata, flags, rc, props=None):
    print(f"✅ MQTT connected rc={rc}")
    cli.subscribe(SENSOR_SUB_TOPIC, qos=1)

def on_message(cli, userdata, msg):
    global latest_sensor
    try:
        js = json.loads(msg.payload.decode())
        latest_sensor = js
    except Exception as e:
        print("❌ MQTT parse error:", e)

def mqtt_thread():
    global mqtt_cli
    mqtt_cli = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="server-video")
    mqtt_cli.username_pw_set(MQTT_USER, MQTT_PASS)
    mqtt_cli.tls_set(cert_reqs=ssl.CERT_NONE)
    mqtt_cli.on_connect = on_connect
    mqtt_cli.on_message = on_message
    mqtt_cli.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    mqtt_cli.loop_forever()

threading.Thread(target=mqtt_thread, daemon=True).start()

# ---------- Live video from ESP32 ----------
def gen_frames():
    cap = cv2.VideoCapture(ESP32_STREAM_URL)
    if not cap.isOpened():
        print("❌ Cannot open stream. Check IP or /stream path.")
        return
    print("🎥 Connected to ESP32 stream!")
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        if not ok:
            continue
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n")
        time.sleep(0.03)  # ~30 FPS

@app.route("/video")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

# ---------- Sensor status ----------
@app.route("/status")
def status():
    return jsonify(latest_sensor)

# ---------- Control (optional) ----------
@app.route("/move/<cmd>", methods=["POST"])
def move_robot(cmd):
    valid = {"up":"tien", "down":"lui", "left":"trai", "right":"phai", "stop":"yen"}
    if cmd not in valid:
        return jsonify({"ok": False, "error": "Invalid command"}), 400
    payload = json.dumps({"cmd": valid[cmd], "ts": time.time()})
    try:
        mqtt_cli.publish(CMD_PUB_TOPIC, payload, qos=1)
        print("📡 Sent command:", payload)
        return jsonify({"ok": True, "cmd": cmd})
    except Exception as e:
        print("❌ Publish error:", e)
        return jsonify({"ok": False, "error": str(e)}), 500

# ---------- UI ----------
@app.route("/")
def index():
    html = """
    <html><head><title>Matthew Robot Stream</title></head>
    <body style="background:#111;color:#eee;text-align:center;">
    <h2>🤖 Live Stream from ESP32-CAM</h2>
    <img src="/video" width="640" height="480" style="border-radius:8px;border:2px solid #333;">
    <p>Controls:
      <button onclick="move('up')">⬆️</button>
      <button onclick="move('left')">⬅️</button>
      <button onclick="move('stop')">⏹️</button>
      <button onclick="move('right')">➡️</button>
      <button onclick="move('down')">⬇️</button>
    </p>
    <script>
      async function move(dir){
        try{
          const r = await fetch('/move/'+dir, {method:'POST'});
          console.log(await r.text());
        }catch(e){console.log(e);}
      }
    </script>
    </body></html>
    """
    return render_template_string(html)

# ---------- Main ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, threaded=True)
