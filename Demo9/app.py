from pathlib import Path

from src.pipeline import discover_input_images, process_image


def main() -> int:
    base_dir = Path(__file__).resolve().parent
    image_paths = discover_input_images(base_dir)

    if not image_paths:
        print("No input images found.")
        return 0

    for image_path in image_paths:
        result = process_image(image_path, base_dir / "outputs")
        print(
            f"{image_path.name}: elements={result.element_count} "
            f"contours={result.contour_count} connectors={result.connector_count} "
            f"verification={result.verification_status}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
