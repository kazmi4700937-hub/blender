import typer
import yaml
import os
import sys
from typing import List, Optional
from .bridge_client import BridgeClient, BridgeError
from .settings import load_config

app = typer.Typer(help="2D-to-3D Character Rigging Assistant CLI")


def get_bridge_client() -> BridgeClient:
    cfg = load_config()
    b_cfg = cfg.get("bridge", {})
    host = b_cfg.get("host", "127.0.0.1")
    port = int(b_cfg.get("port", 9876))
    timeout = float(b_cfg.get("timeout_seconds", 30.0))
    return BridgeClient(host=host, port=port, timeout=timeout)

@app.command()
def ping():
    """Ping the Blender bridge and print versions."""
    client = get_bridge_client()
    try:
        client.connect()
        res = client.ping()
        typer.echo(f"Bridge connected successfully!")
        typer.echo(f"Blender Version: {res.get('blender_version')}")
        typer.echo(f"Addon Version:   {res.get('addon_version')}")
    except BridgeError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    finally:
        client.close()

@app.command()
def scene_info():
    """Get current Blender scene information."""
    client = get_bridge_client()
    try:
        client.connect()
        res = client.get_scene_info()
        typer.echo(f"Frame range: {res.get('frame_start')} - {res.get('frame_end')} (current: {res.get('frame_current')}, fps: {res.get('fps')})")
        typer.echo(f"Armatures: {res.get('armatures')}")
        typer.echo(f"Total objects: {len(res.get('objects', []))}")
        for obj in res.get("objects", []):
            typer.echo(f"  - {obj['name']} ({obj['type']}) at {obj['location']}")
    except BridgeError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    finally:
        client.close()

@app.command()
def clear_scene():
    """Clear all objects from Blender scene."""
    client = get_bridge_client()
    try:
        client.connect()
        res = client.clear_scene()
        typer.echo(f"Scene cleared: {res}")
    except BridgeError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    finally:
        client.close()

@app.command()
def validate_images(
    front: str = typer.Option("assets/test_images/front.png", help="Path to front view image"),
    side: str = typer.Option("assets/test_images/side.png", help="Path to side view image"),
    allow_busy_background: bool = typer.Option(
        False, "--allow-busy-background",
        help="Accept gradient or busy backgrounds; the character is then cut out with rembg."),
):
    """Validate front and side reference images."""
    from .vision.validate import validate_input_images, ImageValidationError
    try:
        res = validate_input_images(front, side, allow_busy_background=allow_busy_background)
        for warning in res.get("warnings", []):
            typer.secho(f"Warning: {warning}", fg=typer.colors.YELLOW)
        typer.secho("Images validated successfully!", fg=typer.colors.GREEN)
        typer.echo(f"Front: {res['front']['size']} (bg: {res['front']['background']['type']})")
        typer.echo(f"Side:  {res['side']['size']} (bg: {res['side']['background']['type']})")
    except ImageValidationError as e:
        typer.secho(f"Validation failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def extract_silhouettes(
    front: str = typer.Option("assets/test_images/front.png", help="Path to front view image"),
    side: str = typer.Option("assets/test_images/side.png", help="Path to side view image"),
    output_dir: str = typer.Option("output", help="Output directory for masks")
):
    """Extract binary silhouette masks from reference images."""
    from .vision.silhouette import extract_silhouette_mask
    os.makedirs(output_dir, exist_ok=True)
    mask_front_path = os.path.join(output_dir, "front_mask.png")
    mask_side_path = os.path.join(output_dir, "side_mask.png")
    
    f_res = extract_silhouette_mask(front, mask_front_path)
    s_res = extract_silhouette_mask(side, mask_side_path)
    
    typer.secho("Silhouettes extracted successfully!", fg=typer.colors.GREEN)
    typer.echo(f"Front mask: height {f_res['height_px']}px, ground y={f_res['ground_y']} -> {mask_front_path}")
    typer.echo(f"Side mask:  height {s_res['height_px']}px, ground y={s_res['ground_y']} -> {mask_side_path}")

@app.command()
def geometry_generate(
    images: List[str] = typer.Option(..., "--image", help="Reference image (repeat for more than one; front first)"),
    provider: Optional[str] = typer.Option(None, help="manual or tripo. Default: geometry.provider in config.yaml"),
    model: Optional[str] = typer.Option(None, help="manual provider only: path to a finished model file (.glb, .gltf, .fbx, .obj)"),
    rig: bool = typer.Option(False, "--rig", help="Also ask the provider to rig the model, if it can"),
    output_dir: str = typer.Option("output/geometry", help="Folder for the model files"),
):
    """Get a 3D model for the reference images from the chosen provider."""
    from .geometry import GeometryError, GeometryRequest, get_provider
    try:
        prov = get_provider(provider)
        options = {"model_path": model} if model else {}
        result = prov.generate(GeometryRequest(image_paths=images, output_dir=output_dir, rig=rig, options=options))
    except GeometryError as e:
        typer.secho(f"Geometry failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.secho(f"Model ready (provider: {result.provider})", fg=typer.colors.GREEN)
    typer.echo(f"Mesh:   {result.mesh_path}")
    if result.rigged_path:
        typer.echo(f"Rigged: {result.rigged_path}")
    if result.credits_used is not None:
        typer.echo(f"Credits used: {result.credits_used:g}")
    for note in result.notes:
        typer.secho(f"Note: {note}", fg=typer.colors.YELLOW)

@app.command()
def import_generated_mesh(
    path: str = typer.Argument(..., help="Model file (.glb, .gltf, .fbx, .obj), for example output/geometry/generated.glb"),
    height_m: float = typer.Option(1.75, help="Real height of the character in metres"),
    save: Optional[str] = typer.Option(None, help="Save the scene as this .blend file afterwards"),
):
    """Import a generated model into Blender, scale it, stand it on the ground and check the mesh."""
    client = get_bridge_client()
    try:
        client.connect()
        res = client.import_generated_mesh(os.path.abspath(path), height_m)
        typer.secho("Model imported and normalized.", fg=typer.colors.GREEN)
        typer.echo(f"Height {res['height_m']} m, width {res['width_m']} m, depth {res['depth_m']} m (scale factor {res['scale_factor']})")
        typer.echo(f"Vertices {res['vertices']} (before merging seams: {res['vertices_before_weld']}), triangles {res['triangles']}, "
                   f"pieces {res['pieces']}, open edges {res['non_manifold_edges']}, UV map: {res['has_uv']}")
        for warning in res["warnings"]:
            typer.secho(f"Warning: {warning}", fg=typer.colors.YELLOW)
        if save:
            client.save_blend(os.path.abspath(save))
            typer.echo(f"Saved {save}")
    except BridgeError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    finally:
        client.close()

@app.command()
def propose_landmarks(
    front: str = typer.Option("assets/test_images/front.png", help="Path to front view image"),
    side: str = typer.Option("assets/test_images/side.png", help="Path to side view image"),
    output_dir: str = typer.Option("output", help="Output directory")
):
    """Propose landmarks via VLM or fallback, and generate visual overlays."""
    import json
    from .vision.landmarks import propose_landmarks_vlm
    from .vision.overlay import draw_landmarks_overlay
    os.makedirs(output_dir, exist_ok=True)
    out_json = os.path.join(output_dir, "landmarks.json")
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        typer.echo("Querying Vision-Language Model for landmarks...")
        data = propose_landmarks_vlm(front, side)
    else:
        # Fallback to ground truth or template projection if available
        gt_file = "assets/test_images/ground_truth_landmarks.json"
        if os.path.exists(gt_file):
            typer.secho("ANTHROPIC_API_KEY not found. Using reference ground truth as proposal.", fg=typer.colors.YELLOW)
            with open(gt_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["confirmed"] = False
            data["source"] = "reference_proposal"
        else:
            typer.secho("ANTHROPIC_API_KEY must be set to propose landmarks with VLM.", fg=typer.colors.RED, err=True)
            raise typer.Exit(code=1)
            
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    front_overlay_path = os.path.join(output_dir, "landmarks_front_overlay.png")
    side_overlay_path = os.path.join(output_dir, "landmarks_side_overlay.png")
    draw_landmarks_overlay(front, data["front"], view="front", output_path=front_overlay_path)
    draw_landmarks_overlay(side, data["side"], view="side", output_path=side_overlay_path)
    
    typer.secho(f"Landmarks proposed and saved to: {out_json}", fg=typer.colors.GREEN)
    typer.echo(f"Review overlays:")
    typer.echo(f"  Front: {front_overlay_path}")
    typer.echo(f"  Side:  {side_overlay_path}")
    typer.echo("Please review the overlays. If corrections are needed, edit output/landmarks.json.")
    typer.echo("Once verified, run: python -m orchestrator.cli confirm-landmarks")

@app.command()
def confirm_landmarks(
    landmarks_path: str = typer.Option("output/landmarks.json", help="Path to landmarks.json")
):
    """Mark landmarks as confirmed by the user."""
    import json
    if not os.path.exists(landmarks_path):
        typer.secho(f"File not found: {landmarks_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
        
    with open(landmarks_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    data["confirmed"] = True
    data["source"] = "user_confirmed"
    
    with open(landmarks_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        
    typer.secho(f"Landmarks marked confirmed in: {landmarks_path}", fg=typer.colors.GREEN)

@app.command()
def measure(
    landmarks_path: str = typer.Option("output/landmarks.json", help="Path to landmarks.json"),
    front_mask_path: str = typer.Option("output/front_mask.png", help="Path to front mask"),
    side_mask_path: str = typer.Option("output/side_mask.png", help="Path to side mask"),
    output_path: str = typer.Option("output/character_spec.json", help="Path to character_spec.json"),
    height_m: float = typer.Option(1.75, help="Target character height in meters")
):
    """Compute 3D joint positions and body dimensions from confirmed landmarks."""
    import json
    import cv2
    from .measure.measure import compute_measurements, UnconfirmedLandmarksError, LandmarkOrderError
    
    if not os.path.exists(landmarks_path):
        typer.secho(f"Landmarks file not found: {landmarks_path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
        
    with open(landmarks_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    f_mask = cv2.imread(front_mask_path, cv2.IMREAD_GRAYSCALE) if os.path.exists(front_mask_path) else None
    s_mask = cv2.imread(side_mask_path, cv2.IMREAD_GRAYSCALE) if os.path.exists(side_mask_path) else None
    
    try:
        spec = compute_measurements(data, front_mask=f_mask, side_mask=s_mask, height_m=height_m)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=2)
            
        typer.secho(f"Character specification written to: {output_path}", fg=typer.colors.GREEN)
        typer.echo(f"Height: {spec['height_m']}m, Joints: {len(spec['joints'])}, Widths: {spec['widths']}")
        if spec["warnings"]:
            typer.secho(f"Warnings ({len(spec['warnings'])}):", fg=typer.colors.YELLOW)
            for w in spec["warnings"]:
                typer.echo(f"  - {w}")
    except (UnconfirmedLandmarksError, LandmarkOrderError, ValueError) as e:
        typer.secho(f"Measurement error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

@app.command()
def agent(
    prompt: str = typer.Argument(..., help="Natural language command (e.g. 'Make the character jump from a 3 meter high ground')"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate and plan without sending commands to Blender"),
    preview: bool = typer.Option(True, "--preview/--no-preview", help="Render preview after applying motion"),
    preview_path: str = typer.Option("output/previews/agent_preview.png", help="Path to save preview render")
):
    """Natural-language agent interface for character motions and environments."""
    from .agent.run import run_agent_command

    client = None
    if not dry_run:
        client = get_bridge_client()
        try:
            client.connect()
        except BridgeError as be:
            typer.secho(f"Notice: Could not connect to Blender bridge ({be}). Running in dry-run mode.", fg=typer.colors.YELLOW)
            client = None

    try:
        res = run_agent_command(
            prompt,
            bridge_client=client,
            render_preview=preview,
            preview_output_path=preview_path
        )

        if not res.success:
            typer.secho(f"Command failed: {res.message}", fg=typer.colors.RED, err=True)
            if res.errors:
                for err in res.errors:
                    typer.echo(f"  - {err}")
            raise typer.Exit(code=1)

        typer.secho(f"Agent response:", fg=typer.colors.GREEN)
        typer.echo(f"{res.message}")

        if res.tool_calls:
            typer.echo("\nPlanned tool calls:")
            for t_name, t_args in res.tool_calls:
                typer.echo(f"  - {t_name}({t_args})")

        if res.bridge_commands:
            typer.echo(f"\nBridge commands ({len(res.bridge_commands)}):")
            for cmd in res.bridge_commands:
                typer.echo(f"  - {cmd['command']}: {cmd.get('params')}")

        if res.applied_defaults:
            typer.echo(f"\nApplied defaults:")
            for d in res.applied_defaults:
                typer.echo(f"  - {d['tool']}: {d['defaults']}")

        if res.preview_path:
            typer.secho(f"\nPreview rendered to: {res.preview_path}", fg=typer.colors.CYAN)

    finally:
        if client:
            client.close()


if __name__ == "__main__":
    app()
