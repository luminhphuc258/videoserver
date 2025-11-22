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
const NODE_CAMERA = "{{ node_camera }}";

document.getElementById("btnLeft20").onclick = async () => {
    try {
        const r = await fetch(NODE_CAMERA + "?direction=left&angle=20");
        const js = await r.json();
        document.getElementById("cameraStatus").innerText =
            "Sent LEFT → " + js.status;
    } catch(err) {
        document.getElementById("cameraStatus").innerText =
            "Error: " + err;
    }
};

document.getElementById("btnRight20").onclick = async () => {
    try {
        const r = await fetch(NODE_CAMERA + "?direction=right&angle=20");
        const js = await r.json();
        document.getElementById("cameraStatus").innerText =
            "Sent RIGHT → " + js.status;
    } catch(err) {
        document.getElementById("cameraStatus").innerText =
            "Error: " + err;
    }
};
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
