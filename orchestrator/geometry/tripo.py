"""Tripo provider: image to 3D model, and optional rigging, through the Tripo web API.

What is confirmed from Tripo's published docs (checked 13 Oct 2026):
  - base URL https://openapi.tripo3d.com/v3, header "Authorization: Bearer <key>"
  - POST /files (multipart field "file") returns {"code": 0, "data": {"file_token": ...}}
  - POST /generation/image-to-model, /animations/rig-check and /animations/rig create tasks
  - GET /tasks/{task_id} returns status queued/running/success/failed/cancelled and output.model_url
  - rig-check returns output.riggable and output.rig_type; rig takes input, rig_type, spec, out_format

NOT confirmed (the docs pages for image-to-model could not be read): the exact body of the
image-to-model request. It is therefore a setting: geometry.tripo.generation_body in config.yaml
(VERIFY against https://developers.tripo3d.com/en/docs). "{file_token}" in any string value is
replaced with the uploaded image's token. If Tripo rejects the body, its own error message is shown.

The API key comes from the environment variable named in config (default TRIPO_API_KEY).
"""

import copy
import os
import time
from typing import Any, Dict, Optional

from .base import GeometryError, GeometryProvider, GeometryRequest, GeometryResult

DEFAULT_BASE_URL = "https://openapi.tripo3d.com/v3"
DEFAULT_BODY = {"input": "{file_token}"}   # VERIFY against Tripo's image-to-model docs


class TripoProvider(GeometryProvider):
    name = "tripo"
    can_generate = True
    can_rig = True

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, session=None, sleep=time.sleep):
        super().__init__(cfg)
        self.base_url = (self.cfg.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.poll_seconds = float(self.cfg.get("poll_seconds", 5))
        self.timeout_seconds = float(self.cfg.get("timeout_seconds", 600))
        self._session = session
        self._sleep = sleep
        self._credits = 0.0
        self._credits_seen = False

    # ----- plumbing -------------------------------------------------------------------------
    def _api_key(self) -> str:
        env_var = self.cfg.get("api_key_env_var", "TRIPO_API_KEY")
        key = os.environ.get(env_var)
        if not key:
            raise GeometryError(
                f"No Tripo API key found. Create one at https://developers.tripo3d.com/en/keys "
                f"and set it in the environment variable {env_var}."
            )
        return key

    def _http(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
        return self._session

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key()}"}

    @staticmethod
    def _unwrap(resp) -> Dict[str, Any]:
        """Return the 'data' part of a Tripo response, or raise with Tripo's own message."""
        try:
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise GeometryError(f"Tripo returned a response that is not JSON (HTTP {resp.status_code}).") from exc
        if resp.status_code >= 400 or payload.get("code", 0) not in (0, None):
            message = payload.get("message") or payload.get("error") or payload
            raise GeometryError(f"Tripo rejected the request (HTTP {resp.status_code}): {message}")
        return payload.get("data", payload)

    def _post_json(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._http().post(self.base_url + path, json=body, headers=self._headers(), timeout=60)
        return self._unwrap(resp)

    # ----- the steps ------------------------------------------------------------------------
    def upload_image(self, path: str) -> str:
        if not os.path.isfile(path):
            raise GeometryError(f"Image not found: '{path}'")
        with open(path, "rb") as f:
            resp = self._http().post(self.base_url + "/files", files={"file": (os.path.basename(path), f)},
                                     headers=self._headers(), timeout=120)
        data = self._unwrap(resp)
        token = data.get("file_token")
        if not token:
            raise GeometryError(f"Tripo accepted the upload but returned no file_token: {data}")
        return token

    def _fill(self, value: Any, file_token: str) -> Any:
        if isinstance(value, str):
            return value.replace("{file_token}", file_token)
        if isinstance(value, dict):
            return {k: self._fill(v, file_token) for k, v in value.items()}
        if isinstance(value, list):
            return [self._fill(v, file_token) for v in value]
        return value

    def create_task(self, path: str, body: Dict[str, Any]) -> str:
        data = self._post_json(path, body)
        task_id = data.get("task_id")
        if not task_id:
            raise GeometryError(f"Tripo created no task (response: {data}).")
        return task_id

    def wait_for_task(self, task_id: str) -> Dict[str, Any]:
        """Poll until the task succeeds. Returns the task's data (with 'output')."""
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            resp = self._http().get(f"{self.base_url}/tasks/{task_id}", headers=self._headers(), timeout=60)
            data = self._unwrap(resp)
            status = data.get("status")
            if status == "success":
                used = data.get("credits_consumed")
                if used is not None:
                    self._credits += float(used)
                    self._credits_seen = True
                return data
            if status in ("failed", "cancelled"):
                raise GeometryError(
                    f"Tripo task {task_id} {status}: {data.get('error_code', '')} {data.get('error_message', '')}".strip()
                )
            if time.monotonic() > deadline:
                raise GeometryError(f"Tripo task {task_id} did not finish within {self.timeout_seconds:.0f} s (last status: {status}).")
            self._sleep(self.poll_seconds)

    def download(self, url: str, dest: str) -> str:
        resp = self._http().get(url, timeout=300)
        if resp.status_code >= 400:
            raise GeometryError(f"Could not download the model (HTTP {resp.status_code}).")
        os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(resp.content)
        return dest

    # ----- the public call ------------------------------------------------------------------
    def generate(self, request: GeometryRequest) -> GeometryResult:
        if not request.image_paths:
            raise GeometryError("No reference image was given.")
        os.makedirs(request.output_dir, exist_ok=True)
        notes = ["Model generated by Tripo from the first reference image; its proportions are an estimate, not a measurement."]
        if len(request.image_paths) > 1:
            notes.append("Only the first image was sent. Multi-view input is not enabled yet.")

        token = self.upload_image(request.image_paths[0])
        body = self._fill(copy.deepcopy(self.cfg.get("generation_body") or DEFAULT_BODY), token)
        gen_path = self.cfg.get("generation_endpoint", "/generation/image-to-model")
        gen_id = self.create_task(gen_path, body)
        gen = self.wait_for_task(gen_id)
        model_url = (gen.get("output") or {}).get("model_url")
        if not model_url:
            raise GeometryError(f"Tripo task {gen_id} finished without a model_url.")
        mesh_path = self.download(model_url, os.path.join(request.output_dir, "generated.glb"))
        result = GeometryResult(provider=self.name, mesh_path=mesh_path, task_ids={"generate": gen_id}, notes=notes)

        if request.rig:
            self._rig(request, gen_id, result)
        result.credits_used = self._credits if self._credits_seen else None
        return result

    def _rig(self, request: GeometryRequest, gen_id: str, result: GeometryResult) -> None:
        rig_cfg = self.cfg.get("rig", {}) or {}
        check_id = self.create_task("/animations/rig-check", {"input": gen_id})
        check = self.wait_for_task(check_id).get("output") or {}
        result.task_ids["rig_check"] = check_id
        if not check.get("riggable", False):
            result.notes.append("Tripo reports this model cannot be rigged automatically; it was left unrigged.")
            return
        rig_type = rig_cfg.get("rig_type", "auto")
        if rig_type == "auto":
            rig_type = check.get("rig_type", "biped")
        out_format = rig_cfg.get("out_format", "glb")
        body = {"input": gen_id, "rig_type": rig_type, "spec": rig_cfg.get("spec", "mixamo"), "out_format": out_format}
        if rig_cfg.get("model"):
            body["model"] = rig_cfg["model"]
        rig_id = self.create_task("/animations/rig", body)
        rig = self.wait_for_task(rig_id)
        url = (rig.get("output") or {}).get("model_url")
        if not url:
            raise GeometryError(f"Tripo rig task {rig_id} finished without a model_url.")
        result.rigged_path = self.download(url, os.path.join(request.output_dir, f"rigged.{out_format}"))
        result.task_ids["rig"] = rig_id
        result.notes.append(f"Rigged by Tripo as '{rig_type}' with {body['spec']} bone names (not a Rigify rig).")
