#! /usr/bin/python3

# Streaming and snapshot server 
# Originally based on Source code from the official PiCamera package
# http://picamera.readthedocs.io/en/latest/recipes2.html#web-streaming

from ast import For
import io
import picamera
import logging
import socketserver
from threading import Condition
from http import server

class StreamingOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()
        self.condition = Condition()

    def write(self, buf):
        if buf.startswith(b'\xff\xd8'):
            # New frame, copy the existing buffer's content and notify all
            # clients it's available
            self.buffer.truncate()
            with self.condition:
                self.frame = self.buffer.getvalue()
                self.condition.notify_all()
            self.buffer.seek(0)
        return self.buffer.write(buf)

class SnapshotOutput(object):
    def __init__(self):
        self.frame = None
        self.buffer = io.BytesIO()

    def write(self, buf):
        bufLen = self.buffer.write(buf)
        self.buffer.truncate()
        self.frame = self.buffer.getvalue()
        self.buffer.seek(0)
        return bufLen

class StreamingHandler(server.BaseHTTPRequestHandler):
    
    def change_framerate(self,value):
        num = int(value)
        if(num >= 1 and num <= 60):
            camera.stop_recording()
            camera.framerate = num
            camera.start_recording(output, format='mjpeg')
            self.send_response(202)
            return f"set framerate to {value}"
        return f"Couldn't set framerate to {value}"

    def change_resolution(self,value):
        h,v = map(int,value.split('x'))
        #ensure sensible
        if(h >= 640 and h <= 2592 and v >= 480 and v <= 1944):
            camera.stop_recording()
            camera.resolution = value
            camera.start_recording(output, format='mjpeg')
            self.send_response(202)
            return f"set res to {value}"
        return f"Couldn't set res to {value}"

    def handle_setter(self):
        # get params
        trim = self.path.split('?')[1]
        params = trim.split('&')
        output = "";
        for param in params:
            var, value = param.split('=')
            if(var == "fr"):
                output += self.change_framerate(value)
            if(var == "res"):
                output += self.change_resolution(value)
            return output


    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/stream')
            self.end_headers()
        elif self.path.startswith('/set'):
            content = self.handle_setter()
            
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content.encode(encoding='utf-8'))
        elif self.path == '/snap':
            camera.stop_recording()
            tmp = camera.resolution
            camera.resolution = '2592x1944'
            camera.capture(snap,format='jpeg')
            camera.resolution = tmp
            camera.start_recording(output, format='mjpeg')
            self.send_response(200)
            self.send_header('Content-Type', 'image/jpeg')
            self.send_header('Content-Length', len(snap.frame))
            self.end_headers()
            self.wfile.write(snap.frame)
        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(frame))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


with picamera.PiCamera(resolution='1280x720', framerate=48) as camera:
    output = StreamingOutput()
    snap = SnapshotOutput()
    camera.rotation = 180
    camera.start_recording(output, format='mjpeg')
    try:
        address = ('', 8000)
        server = StreamingServer(address, StreamingHandler)
        server.serve_forever()
    finally:
        camera.stop_recording()
