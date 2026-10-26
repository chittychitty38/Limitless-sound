"""The line between Limitless Keys and every Limitless Undo plugin in every DAW.

Each plugin connects to 127.0.0.1 on the port written in undo-link.json, in the
Limitless Sound folder, and proves it runs as the same person with the token in
that file. Messages are UTF-8 JSON, one object per line.

Plugin -> Keys
  hello   token, instance, host, pid, plugin, track, version
  meta    plugin, track                      the hosted plugin or track name changed
  sync    undo, redo                         its whole history: [{id, label, before, after, age}]
  step    id, label, before, after           a new change
  undone  id / redone id                     it undid or redid a step (its own buttons, or ours)

Keys -> plugin
  welcome
  undo id / redo id                          undo or redo that step; if it isn't the plugin's
                                             next one, the plugin answers with sync
  compare on                                 (unused for now, compare is undo + redo)
"""

import json
import os
import secrets
import socket
import threading

PROTOCOL = 1
MAX_LINE = 1 << 20


class LinkServer:
    def __init__(self, info_path, on_message, on_closed, version=""):
        """on_message(key, msg) and on_closed(key) are called on the connection's thread."""
        self.info_path = info_path
        self.on_message, self.on_closed = on_message, on_closed
        self.version = version
        self.token = secrets.token_hex(16)
        self.port = None
        self._sock = None
        self._conns = {}        # key -> (socket, send lock)
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def start(self, port=0):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", port))
        sock.listen(64)
        self._sock = sock
        self.port = sock.getsockname()[1]
        self._write_info()
        threading.Thread(target=self._accept, daemon=True, name="undo-link").start()
        return self

    def stop(self):
        self._stop.set()
        try:
            self._sock.close()
        except (OSError, AttributeError):
            pass
        with self._lock:
            conns = list(self._conns.values())
        for s, _ in conns:
            try:
                s.close()
            except OSError:
                pass
        try:
            info = json.loads(self.info_path.read_text())
            if info.get("pid") == os.getpid():
                self.info_path.unlink()
        except (OSError, ValueError):
            pass

    def _write_info(self):
        self.info_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.info_path.with_suffix(".tmp")
        data = json.dumps({"protocol": PROTOCOL, "port": self.port, "token": self.token,
                           "pid": os.getpid(), "version": self.version})
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(data)
        tmp.replace(self.info_path)

    def connected(self):
        with self._lock:
            return list(self._conns)

    def send(self, key, msg):
        with self._lock:
            entry = self._conns.get(key)
        if entry is None:
            return False
        sock, lock = entry
        try:
            with lock:
                sock.sendall((json.dumps(msg, separators=(",", ":")) + "\n").encode())
            return True
        except OSError:
            return False

    def _accept(self):
        while not self._stop.is_set():
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn):
        key = None
        try:
            conn.settimeout(5)
            reader = conn.makefile("rb")
            line = reader.readline(MAX_LINE)
            hello = json.loads(line) if line else None
            if not (isinstance(hello, dict) and hello.get("op") == "hello"
                    and secrets.compare_digest(str(hello.get("token", "")), self.token)
                    and hello.get("instance")):
                conn.sendall(b'{"op":"error","message":"bad hello"}\n')
                return
            conn.settimeout(None)
            key = "link:" + str(hello["instance"])
            with self._lock:
                old = self._conns.get(key)
                self._conns[key] = (conn, threading.Lock())
            if old is not None:      # the same plugin reconnected: drop the old line
                try:
                    old[0].close()
                except OSError:
                    pass
            self.on_message(key, hello)
            self.send(key, {"op": "welcome", "protocol": PROTOCOL})
            while not self._stop.is_set():
                line = reader.readline(MAX_LINE)
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if isinstance(msg, dict):
                    self.on_message(key, msg)
        except (OSError, ValueError):
            pass
        finally:
            gone = False
            if key is not None:
                with self._lock:
                    if self._conns.get(key, (None,))[0] is conn:
                        del self._conns[key]
                        gone = True
            try:
                conn.close()
            except OSError:
                pass
            if gone:
                self.on_closed(key)
