#!/usr/bin/env python

import base64
import face_recognition
import datetime
import imutils
import pickle
import time
import cv2
from imutils.video import VideoStream
from flask import Response
from flask import Flask
from flask import render_template
from mailjet_rest import Client
from threading import Thread, Lock


# Initialize 'currentname' to trigger only when a new person is identified.
currentname = "unknown"
# Determine faces from encodings.pickle file model created from train_model.py
encodingsP = "facial_recognition/encodings.pickle"
# use this xml file
cascade = "facial_recognition/haarcascade_frontalface_default.xml"

# initialize the output frame and a lock used to ensure thread-safe
# exchanges of the output frames (useful when multiple browsers/tabs
# are viewing the stream)
outputFrame = None
lock = Lock()

# initialize a flask object
app = Flask(__name__)


@app.route("/")
def index():
    # return the rendered template
    return render_template("index.html")


def send_message(name):
    # Send an email using the Mailjet API, account registration required
    api_key = os.environ['MJ_APIKEY_PUBLIC'] # Your API key
    api_secret = os.environ['MJ_APIKEY_PRIVATE'] # Your API secret
    mailjet = Client(auth=(api_key, api_secret), version='v3.1')
    img = cv2.imread('facial_recognition/image.jpg')
    jpg_img = cv2.imencode('.jpg', img)
    imgBase64 = base64.b64encode(jpg_img[1]).decode('utf-8')
    data = {
        'Messages': [
            {
                "From": {
                    "Email": "Your email",
                    "Name": "Your name"
                },
                "To": [
                    {
                        "Email": "Recipient email",
                        "Name": "Recipient name"
                    }
                ],
                "Subject": "Hello from Trilobot!",
                "HTMLPart": "<h3>Greetings.</h3> Trilobot has detected that " + name + " is in the room.",
                "Attachments": [
                    {
                        "ContentType": "image/jpeg",
                        "Filename": "image.jpg",
                        "Base64Content": imgBase64
                    }
                ]
            }
        ]
    }
    return mailjet.send.create(data=data)


def facial_recognition():
    global currentname
    global encodingsP
    global cascade
    global outputFrame
    global lock
    global encodingsP

    # load the known faces and embeddings along with OpenCV's Haar
    # cascade for face detection
    print("[INFO] loading encodings + face detector...")
    data = pickle.loads(open(encodingsP, "rb").read())
    detector = cv2.CascadeClassifier(cascade)

    # initialize the video stream and allow the camera sensor to warm up
    print("[INFO] starting video stream...")
    vs = VideoStream(usePiCamera=True).start()
    time.sleep(2.0)

    # loop over frames from the video file stream
    while True:
        # get frame and resize to speed up processing
        frame = vs.read()
        frame = imutils.resize(frame, width=500)

        # convert the input frame from (1) BGR to grayscale (for face
        # detection) and (2) from BGR to RGB (for face recognition)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # get the current timestamp and draw it on the frame
        timestamp = datetime.datetime.now()
        cv2.putText(frame, timestamp.strftime(
            "%A %d %B %Y %I:%M:%S%p"), (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 0, 255), 1)

        # detect faces in the grayscale frame
        rects = detector.detectMultiScale(gray, scaleFactor=1.1,
                                          minNeighbors=5, minSize=(30, 30),
                                          flags=cv2.CASCADE_SCALE_IMAGE)

        # OpenCV returns bounding box coordinates in (x, y, w, h) order
        # but we need them in (top, right, bottom, left) order, so we
        # need to do a bit of reordering
        boxes = [(y, x + w, y + h, x) for (x, y, w, h) in rects]

        # compute the facial embeddings for each face bounding box
        encodings = face_recognition.face_encodings(rgb, boxes)
        names = []

        # loop over the facial embeddings
        for encoding in encodings:
            # attempt to match each face in the input image to encodings
            matches = face_recognition.compare_faces(data["encodings"],
                                                     encoding)
            name = "Unknown"

            if True in matches:
                # find the indexes of all matched faces then initialize a
                # dictionary to count the total number of times each face
                # was matched
                matchedIdxs = [i for (i, b) in enumerate(matches) if b]
                counts = {}

                # loop over the matched indexes and maintain a count for
                # each recognized face
                for i in matchedIdxs:
                    name = data["names"][i]
                    counts[name] = counts.get(name, 0) + 1

                # determine the recognized face with the largest number
                # of votes (note: in the event of an unlikely tie Python
                # will select first entry in the dictionary)
                name = max(counts, key=counts.get)

                # If someone in your dataset is identified, print their name on the screen
                if currentname != name:
                    currentname = name
                    print(currentname)

                    # Take a picture to send in the email
                    img_name = "facial_recognition/image.jpg"
                    cv2.imwrite(img_name, frame)
                    print('Taking a picture.')

                    # Notify user by sending an email
                    request = send_message(name)
                    print(
                        'Status Code: ' + format(request.status_code))  # 200 status code means email sent successfully

            # update the list of names
            names.append(name)

        # loop over the recognized faces
        for ((top, right, bottom, left), name) in zip(boxes, names):
            # draw the predicted face name on the image - color is in BGR
            cv2.rectangle(frame, (left, top), (right, bottom),
                          (0, 255, 225), 2)
            y = top - 15 if top - 15 > 15 else top + 15
            cv2.putText(frame, name, (left, y), cv2.FONT_HERSHEY_SIMPLEX,
                        .8, (0, 255, 255), 2)

        with lock:
            outputFrame = frame.copy()


def generate():
    # grab global references to the output frame and lock variables
    global outputFrame, lock
    # loop over frames from the output stream
    while True:
        # wait until the lock is acquired
        with lock:
            # check if the output frame is available, otherwise skip
            # the iteration of the loop
            if outputFrame is None:
                continue
            # encode the frame in JPEG format
            (flag, encodedImage) = cv2.imencode(".jpg", outputFrame)
            # ensure the frame was successfully encoded
            if not flag:
                continue

        # yield the output frame in the byte format
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')


@app.route("/video_feed")
def video_feed():
    # return the response generated along with the specific media
    # type (mime type)
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


def main():
    # start a thread that will perform facial recognition
    t = Thread(target=facial_recognition, daemon=None)
    t.start()
    print("[INFO] Starting facial recognition thread.")

    # start the flask app on port 8100
    app.run(host="0.0.0.0", port=8100, debug=True, threaded=True, use_reloader=False)


# check to see if this is the main thread of execution
if __name__ == '__main__':
    main()


