import gc
import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter
from rembg import new_session, remove  # type: ignore

from .models import ProcessingOptions
from .trace import tracer

_rembg_sessions: dict[str, Any] = {}


def get_rembg_session(model_name: str, force_cpu: bool = False):
    key = f"{model_name}_cpu" if force_cpu else model_name
    if key not in _rembg_sessions:
        providers = (
            ["CPUExecutionProvider"]
            if force_cpu
            else ["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
        _rembg_sessions[key] = new_session(model_name, providers=providers)
    return _rembg_sessions[key]


def handle_cuda_oom(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_str = str(e).lower()
            if "memory" in error_str or "oom" in error_str or "allocate" in error_str:
                with tracer.span("cuda_oom_recovery"):
                    gc.collect()
                    # Try to force CPU on kwargs if possible, or just retry with CPU session
                    kwargs["force_cpu"] = True
                    return func(*args, **kwargs)
            raise

    return wrapper


@handle_cuda_oom
def _remove_bg_with_retry(
    img: Image.Image, model_name: str, force_cpu: bool = False
) -> Image.Image:
    session = get_rembg_session(model_name, force_cpu=force_cpu)
    return remove(img, session=session)


def add_shadow(img: Image.Image) -> Image.Image:
    # A simple shadow effect for a transparent image
    if img.mode != "RGBA":
        return img

    # Create shadow layer
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))

    # Extract alpha channel and use it as black mask with some offset
    alpha = img.split()[3]
    shadow_mask = Image.new("L", img.size, 0)
    shadow_mask.paste(alpha, (0, 10))  # offset shadow down

    # Blur the mask
    shadow_mask = shadow_mask.filter(ImageFilter.GaussianBlur(10))

    # Apply shadow to the layer
    shadow.paste((0, 0, 0, 100), (0, 0), mask=shadow_mask)

    # Composite
    result = Image.alpha_composite(shadow, img)
    return result


def process_and_export_image(
    image_bytes: bytes,
    folder_name: str,
    filename_base: str,
    options: ProcessingOptions | None = None,
    output_base_dir: Path | str | None = None,
):
    """Process image and export to output directory."""
    if options is None:
        options = ProcessingOptions()

    with tracer.span(
        "process_and_export_image", folder=folder_name, filename=filename_base, op_type="MUTATING"
    ) as span:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

        if options.remove_bg:
            model_name = "isnet-general-use"
            with tracer.span("remove_bg", model=model_name):
                img = _remove_bg_with_retry(img, model_name=model_name)

        if options.shadow:
            with tracer.span("shadow"):
                img = add_shadow(img)

        # Center and crop logic could go here, omitting for brevity unless required
        if options.center:
            # simple centering on canvas
            canvas = Image.new("RGBA", options.canvas, options.bg_color)
            # Resize image to fit canvas based on crop_ratio
            target_w = int(options.canvas[0] * options.crop_ratio)
            target_h = int(options.canvas[1] * options.crop_ratio)
            img.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)

            x = (options.canvas[0] - img.width) // 2
            y = (options.canvas[1] - img.height) // 2
            canvas.paste(img, (x, y), img)
            img = canvas
        else:
            # Just add background color
            bg = Image.new("RGBA", img.size, options.bg_color)
            img = Image.alpha_composite(bg, img)

        img = img.convert("RGB")  # Ready for JPEG

        # Export to output/
        base_dir = (
            Path(output_base_dir)
            if output_base_dir is not None
            else Path(__file__).resolve().parent.parent / "output"
        )
        output_dir = base_dir / folder_name
        output_dir.mkdir(parents=True, exist_ok=True)

        jpg_path = output_dir / f"{filename_base}.jpg"
        img.save(jpg_path, "JPEG", quality=options.export_jpeg_q)
        span.metadata["exported_jpg"] = str(jpg_path)

        if options.export_webp:
            webp_path = output_dir / f"{filename_base}.webp"
            img.save(webp_path, "WEBP", quality=options.export_jpeg_q)
            span.metadata["exported_webp"] = str(webp_path)

        return str(output_dir)
