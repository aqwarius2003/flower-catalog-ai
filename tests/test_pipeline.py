import io
from pathlib import Path

from PIL import Image

from src.image_processor import process_and_export_image
from src.models import ProcessingOptions


def test_process_and_export_image(tmp_path: Path):
    # Create a 300x300 image
    img = Image.new("RGB", (300, 300), color="red")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    img_bytes = buf.getvalue()

    # Process options
    options = ProcessingOptions(remove_bg=True, shadow=True, center=True)

    folder_name = "test_folder"
    filename = "test_img"

    export_dir = process_and_export_image(
        img_bytes, folder_name, filename, options=options, output_base_dir=tmp_path
    )

    output_dir = Path(export_dir)
    assert output_dir.exists(), "Output directory should be created"
    assert (output_dir / f"{filename}.jpg").exists(), "JPEG image should be exported"
    assert (output_dir / f"{filename}.webp").exists(), "WEBP image should be exported"
