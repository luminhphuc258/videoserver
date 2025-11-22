from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# ==========================================
# NODEJS ENDPOINTS
# ==========================================
NODEJS_BASE = "https://embeddedprogramming-healtheworldserver.up.railway.app"

NODEJS_UPLOAD_URL = NODEJS_BASE + "/upload_audio"
NODEJS_CAMERA_URL = NODEJS_BASE + "/camera_rotate"

NODEJS_SCAN_30  = NODEJS_BASE + "/trigger_scan30"
NODEJS_SCAN_45  = NODEJS_BASE + "/trigger_scan45"
NODEJS_SCAN_90  = NODEJS_BASE + "/trigger_scan90"
NODEJS_SCAN_180 = NODEJS_BASE + "/trigger_scan180"
NODEJS_SCAN_360 = NODEJS_BASE + "/trigger_scan"


# ==========================================
# HTML TEMPLATE — dùng {{ }} cho Flask render
# ==========================================
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Matthew Robot Control</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>

<body style="background:#111; color:white; text-align:center; font-family:sans-serif; padding:20px;">

<h2 style="color:#0af;">Camera Control</h2>

<button id="btnLeft20"  style="padding:10px 20px; margin:5px;">LEFT 20°</button>
<button id="btnRight20" style="padding:10px 20px; margin:5px;">RIGHT 20°</button>

<p id="cameraStatus" style="margin-top:15px; color:#0f0;"></p>

<script>
/* ==========================================================
   CAMERA ROTATE → GỌI THẲNG NODEJS /camera_rotate
========================================================== */

const NODE_CAMERA = "__NODE_CAMERA__";

// góc hiện tại của camera (giống với góc em set lúc bật nguồn ở ESP, ví dụ 90°)
let currentCamAngle = 90;     
const STEP = 20;              // mỗi lần quay 20°

async function sendCameraRotate(direction) {
    // tính góc mới
    if (direction === "left")  currentCamAngle += STEP;
    if (direction === "right") currentCamAngle -= STEP;

    // giới hạn 0–180
    if (currentCamAngle < 0)   currentCamAngle = 0;
    if (currentCamAngle > 180) currentCamAngle = 180;

    const url = NODE_CAMERA + 
        "?direction=" + encodeURIComponent(direction) + 
        "&angle=" + encodeURIComponent(currentCamAngle);

    try {
        const res = await fetch(url);
        const js  = await res.json();

        document.getElementById("camAngleStatus").innerText =
          `Sent: ${direction.toUpperCase()} → ${currentCamAngle}° (status=${js.status})`;
    } catch (e) {
        document.getElementById("camAngleStatus").innerText =
          "Error sending command: " + e;
    }
}

// gán sự kiện cho 2 nút
document.getElementById("camLeft20").onclick  = () => sendCameraRotate("left");
document.getElementById("camRight20").onclick = () => sendCameraRotate("right");
</script>

</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(
        TEMPLATE,
        node_camera=NODEJS_CAMERA_URL
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
