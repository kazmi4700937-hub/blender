import socket
import threading
import queue
import json
import traceback
import bpy

from .commands import scene, fit, rig, environment, motion

# Global server state
_server_sock = None
_server_thread = None
_running = False
_request_queue = queue.Queue()
_timer_registered = False
_allow_exec = False

COMMAND_HANDLERS = {
    "ping": scene.cmd_ping,
    "get_scene_info": scene.cmd_get_scene_info,
    "clear_scene": scene.cmd_clear_scene,
    "save_blend": scene.cmd_save_blend,
    "render_preview": scene.cmd_render_preview,
    "set_frame_range": scene.cmd_set_frame_range,
    "create_cube": scene.cmd_create_cube,
    "import_base_character": fit.cmd_import_base_character,
    "fit_template": fit.cmd_fit_template,
    "generate_rig": rig.cmd_generate_rig,
    "bind_mesh": rig.cmd_bind_mesh,
    "list_bones": rig.cmd_list_bones,
    "build_environment": environment.cmd_build_environment,
    "apply_motion": motion.cmd_apply_motion,
}

def register_command(name, handler):
    COMMAND_HANDLERS[name] = handler

def _execute_request_on_main_thread(req):
    req_id = req.get("id", "unknown")
    command = req.get("command")
    params = req.get("params", {})
    
    if not command:
        return {
            "id": req_id,
            "status": "error",
            "error": {"code": "BAD_REQUEST", "message": "Missing 'command' field"}
        }
        
    if command == "execute_python":
        if not _allow_exec:
            return {
                "id": req_id,
                "status": "error",
                "error": {"code": "FORBIDDEN", "message": "execute_python is disabled by config"}
            }
        code = params.get("code", "")
        locs = {}
        try:
            exec(code, globals(), locs)
            return {"id": req_id, "status": "ok", "result": locs.get("result", {})}
        except Exception as e:
            return {
                "id": req_id,
                "status": "error",
                "error": {"code": "EXEC_ERROR", "message": str(e), "traceback": traceback.format_exc()}
            }
            
    handler = COMMAND_HANDLERS.get(command)
    if not handler:
        return {
            "id": req_id,
            "status": "error",
            "error": {"code": "UNKNOWN_COMMAND", "message": f"Command '{command}' is not recognized"}
        }
        
    try:
        res = handler(params)
        return {
            "id": req_id,
            "status": "ok",
            "result": res if res is not None else {}
        }
    except Exception as e:
        return {
            "id": req_id,
            "status": "error",
            "error": {"code": "COMMAND_ERROR", "message": str(e), "traceback": traceback.format_exc()}
        }

def _process_queue_timer():
    global _running
    if not _running:
        return None  # Unregister timer
        
    # Process up to 50 requests per tick to prevent latency buildup
    processed = 0
    while not _request_queue.empty() and processed < 50:
        try:
            item = _request_queue.get_nowait()
        except queue.Empty:
            break
            
        req, client_sock = item
        response_dict = _execute_request_on_main_thread(req)
        
        try:
            resp_bytes = (json.dumps(response_dict) + "\n").encode("utf-8")
            client_sock.sendall(resp_bytes)
        except Exception as e:
            print(f"[Bridge Server] Failed to send response: {e}")
        finally:
            _request_queue.task_done()
        processed += 1
        
    return 0.005  # Run every 5ms for low latency

def _handle_client_connection(client_sock, client_addr):
    buffer = ""
    client_sock.settimeout(1.0)
    
    while _running:
        try:
            data = client_sock.recv(4096)
            if not data:
                break
            buffer += data.decode("utf-8", errors="replace")
            
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    req = json.loads(line)
                    if not isinstance(req, dict):
                        raise ValueError("Request must be a JSON object")
                    _request_queue.put((req, client_sock))
                except Exception as e:
                    err_resp = {
                        "id": "unknown",
                        "status": "error",
                        "error": {"code": "MALFORMED_JSON", "message": str(e)}
                    }
                    try:
                        client_sock.sendall((json.dumps(err_resp) + "\n").encode("utf-8"))
                    except Exception:
                        pass
        except socket.timeout:
            continue
        except Exception as e:
            break
            
    try:
        client_sock.close()
    except Exception:
        pass

def _server_listener(host, port):
    global _running, _server_sock
    while _running:
        try:
            client_sock, client_addr = _server_sock.accept()
            t = threading.Thread(
                target=_handle_client_connection,
                args=(client_sock, client_addr),
                daemon=True
            )
            t.start()
        except socket.timeout:
            continue
        except Exception as e:
            if not _running:
                break
            print(f"[Bridge Server] Accept error: {e}")

def start_server(host="127.0.0.1", port=9876, allow_exec=False):
    global _server_sock, _server_thread, _running, _timer_registered, _allow_exec
    if _running:
        print("[Bridge Server] Server is already running.")
        return True
        
    _allow_exec = allow_exec
    _running = True
    
    _server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    _server_sock.bind((host, port))
    _server_sock.listen(5)
    _server_sock.settimeout(0.5)
    
    _server_thread = threading.Thread(
        target=_server_listener,
        args=(host, port),
        daemon=True
    )
    _server_thread.start()
    
    if not _timer_registered:
        bpy.app.timers.register(_process_queue_timer, persistent=True)
        _timer_registered = True
        
    print(f"[Bridge Server] Started listening on {host}:{port}")
    return True

def stop_server():
    global _server_sock, _server_thread, _running, _timer_registered
    if not _running:
        return
        
    print("[Bridge Server] Stopping server...")
    _running = False
    
    if _server_sock:
        try:
            _server_sock.close()
        except Exception:
            pass
        _server_sock = None
        
    if _server_thread:
        _server_thread.join(timeout=1.0)
        _server_thread = None
        
    if _timer_registered:
        if bpy.app.timers.is_registered(_process_queue_timer):
            bpy.app.timers.unregister(_process_queue_timer)
        _timer_registered = False
        
    # Drain any leftover requests
    while not _request_queue.empty():
        try:
            _request_queue.get_nowait()
            _request_queue.task_done()
        except Exception:
            break
            
    print("[Bridge Server] Server stopped.")

def run_server_loop(duration=None):
    """Run server processing loop on the main thread (ideal for headless blender -b)."""
    import time
    start = time.time()
    try:
        while _running:
            _process_queue_timer()
            time.sleep(0.005)
            if duration is not None and (time.time() - start) >= duration:
                break
    except KeyboardInterrupt:
        pass
    finally:
        stop_server()

