#!/usr/bin/env python3
import zmq
import json
import time

ctx = zmq.Context()
sock = ctx.socket(zmq.PUB)
sock.connect("tcp://127.0.0.1:6010")
time.sleep(1)  # Let subscription propagate
msg = {"text": "Direct ZMQ test hello"}
sock.send_multipart([b"cmd.tts.speak", json.dumps(msg).encode()])
print("Sent TTS via ZMQ")
sock.close()
