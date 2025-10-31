from flask import Flask, request, Response
import cv2
import numpy as np

app = Flask(__name__)
latest_frame = None

@app.route("/upload_frame", methods=["POST"])
def upload_frame():
    global latest_frame
    data = request.data
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    latest_frame = frame
    return "OK", 200

@app.route("/video")
def video_feed():
    def gen():
        global latest_frame
        while True:
            if latest_frame is not None:
                _, jpeg = cv2.imencode('.jpg', latest_frame)
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
    return Response(gen(), mimetype='multipart/x-mixed-replace; boundary=frame')

app.run(host="0.0.0.0", port=8000)
