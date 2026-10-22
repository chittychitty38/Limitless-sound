# What listening to the microphone costs, by itself, for different ways of opening it.
import queue
import sys
import time

import sounddevice as sd

SECONDS = 20


def run(label, **kw):
    q = queue.Queue()

    def callback(data, frames, t, status):
        q.put(bytes(data))

    try:
        with sd.RawInputStream(callback=callback, dtype="int16", **kw) as s:
            time.sleep(3)
            got, t0, w0 = 0, time.process_time(), time.time()
            while time.time() < w0 + SECONDS:
                try:
                    got += len(q.get(timeout=0.5))
                except queue.Empty:
                    pass
            cpu = (time.process_time() - t0) / (time.time() - w0) * 100
            print(f"{label:<40} {cpu:5.2f}%   latency {s.latency:.3f} s, {got / SECONDS / 1000:.0f} kB/s", flush=True)
    except Exception as e:
        print(f"{label:<40} failed: {e}", flush=True)


info = sd.query_devices(None, "input")
rate, ch = int(info["default_samplerate"]), max(1, min(2, int(info["max_input_channels"])))
print(f"device: {info['name']}, {rate} Hz, {info['max_input_channels']} channels; PortAudio {sd.get_portaudio_version()[1]}", flush=True)
t0, w0 = time.process_time(), time.time()
time.sleep(10)
print(f"{'nothing open':<40} {(time.process_time() - t0) / (time.time() - w0) * 100:5.2f}%", flush=True)
run("as Zoom 0.1.2 opens it", samplerate=rate, blocksize=rate // 10, channels=ch)
run("mono", samplerate=rate, blocksize=rate // 10, channels=1)
run("blocksize chosen by PortAudio", samplerate=rate, blocksize=0, channels=ch)
run("latency 'low'", samplerate=rate, blocksize=rate // 10, channels=ch, latency="low")
run("latency 0.2 s", samplerate=rate, blocksize=rate // 10, channels=ch, latency=0.2)
run("16 kHz mono", samplerate=16000, blocksize=1600, channels=1)
run("as Zoom 0.1.2 opens it, again", samplerate=rate, blocksize=rate // 10, channels=ch)
