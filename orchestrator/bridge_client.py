import socket
import json
import uuid
import time
from typing import Any, Dict, Optional

class BridgeError(Exception):
    """Base exception for bridge communication."""
    pass

class BridgeConnectionError(BridgeError):
    """Raised when unable to connect to Blender bridge."""
    pass

class BridgeTimeoutError(BridgeError):
    """Raised when a request times out."""
    pass

class BridgeCommandError(BridgeError):
    """Raised when Blender returns a command error."""
    def __init__(self, code: str, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.details = details or {}

class BridgeProtocolError(BridgeError):
    """Raised when response is malformed or protocol is violated."""
    pass


class BridgeClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 9876, timeout: float = 30.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._buffer = ""

    def connect(self) -> None:
        if self._sock is not None:
            return
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            self._sock = sock
            self._buffer = ""
        except (ConnectionRefusedError, socket.gaierror, TimeoutError, OSError) as e:
            self._sock = None
            raise BridgeConnectionError(
                f"Could not connect to Blender bridge at {self.host}:{self.port}. "
                "Ensure Blender is running and the Rigging Assistant bridge add-on/server is active."
            ) from e

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buffer = ""

    def is_connected(self) -> bool:
        return self._sock is not None

    def send_command(self, command: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        params = params or {}
        req_id = str(uuid.uuid4())
        req_payload = {
            "id": req_id,
            "command": command,
            "params": params
        }
        raw_msg = json.dumps(req_payload) + "\n"

        # Ensure connected
        if self._sock is None:
            self.connect()

        try:
            self._sock.sendall(raw_msg.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, OSError):
            # Try reconnecting once
            self.close()
            self.connect()
            try:
                self._sock.sendall(raw_msg.encode("utf-8"))
            except Exception as e:
                self.close()
                raise BridgeConnectionError(f"Failed to send command to Blender: {e}") from e

        # Wait for reply matching req_id
        start_time = time.time()
        while True:
            if time.time() - start_time > self.timeout:
                raise BridgeTimeoutError(f"Command '{command}' timed out after {self.timeout}s waiting for reply")

            if "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError as e:
                    raise BridgeProtocolError(f"Received malformed JSON from bridge: {line}") from e

                if not isinstance(resp, dict):
                    raise BridgeProtocolError(f"Expected JSON object response, got: {type(resp)}")

                resp_id = resp.get("id")
                if resp_id == req_id:
                    status = resp.get("status")
                    if status == "ok":
                        return resp.get("result", {})
                    elif status == "error":
                        err = resp.get("error", {})
                        code = err.get("code", "UNKNOWN_ERROR")
                        msg = err.get("message", "No message provided")
                        raise BridgeCommandError(code=code, message=msg, details=err)
                    else:
                        raise BridgeProtocolError(f"Unexpected status '{status}' in response: {resp}")
                else:
                    # Could be an out-of-order or unknown response, keep reading
                    continue

            try:
                self._sock.settimeout(max(0.1, self.timeout - (time.time() - start_time)))
                chunk = self._sock.recv(4096)
                if not chunk:
                    self.close()
                    raise BridgeConnectionError("Bridge closed connection unexpectedly")
                self._buffer += chunk.decode("utf-8", errors="replace")
            except socket.timeout:
                raise BridgeTimeoutError(f"Command '{command}' timed out after {self.timeout}s")
            except (ConnectionResetError, OSError) as e:
                self.close()
                raise BridgeConnectionError(f"Connection lost while waiting for reply: {e}") from e

    def ping(self) -> Dict[str, Any]:
        return self.send_command("ping")

    def get_scene_info(self) -> Dict[str, Any]:
        return self.send_command("get_scene_info")

    def clear_scene(self) -> Dict[str, Any]:
        return self.send_command("clear_scene")

    def save_blend(self, path: str) -> Dict[str, Any]:
        return self.send_command("save_blend", {"path": path})

    def render_preview(self, path: str, frame: Optional[int] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"path": path}
        if frame is not None:
            params["frame"] = frame
        return self.send_command("render_preview", params)

    def set_frame_range(self, start: int, end: int) -> Dict[str, Any]:
        return self.send_command("set_frame_range", {"start": start, "end": end})

    def import_generated_mesh(self, path: str, target_height_m: float = 1.75) -> Dict[str, Any]:
        """Import a generated model, scale it to target_height_m, stand it on the ground and check the mesh."""
        return self.send_command("import_generated_mesh", {"path": path, "target_height_m": target_height_m})
