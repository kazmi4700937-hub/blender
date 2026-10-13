"""Provider that uses a model file you already have.

Make the model anywhere (a web tool, another program, an artist) and pass it here with
options={"model_path": "..."}. Nothing is sent over the network. This is the way to test the
rest of the pipeline without any account or API key.
"""

import os
import shutil

from .base import GeometryError, GeometryProvider, GeometryRequest, GeometryResult

MODEL_EXTENSIONS = (".glb", ".gltf", ".fbx", ".obj")


class ManualProvider(GeometryProvider):
    name = "manual"
    can_generate = False   # it does not generate anything, it only imports

    def generate(self, request: GeometryRequest) -> GeometryResult:
        model_path = request.options.get("model_path")
        if not model_path:
            raise GeometryError(
                "The 'manual' provider needs a finished model file. Pass --model path\\to\\model.glb, "
                "or choose a provider that generates one (for example --provider tripo)."
            )
        if not os.path.isfile(model_path):
            raise GeometryError(f"Model file not found: '{model_path}'")
        ext = os.path.splitext(model_path)[1].lower()
        if ext not in MODEL_EXTENSIONS:
            raise GeometryError(f"Unsupported model type '{ext}'. Use one of: {', '.join(MODEL_EXTENSIONS)}")

        os.makedirs(request.output_dir, exist_ok=True)
        dest = os.path.join(request.output_dir, "generated" + ext)
        if os.path.abspath(model_path) != os.path.abspath(dest):
            shutil.copyfile(model_path, dest)
        notes = ["Model supplied by the user; the app did not generate it."]
        if request.rig:
            notes.append("The manual provider cannot rig; the model will be rigged later by the app's own rig step.")
        return GeometryResult(provider=self.name, mesh_path=dest, notes=notes)
