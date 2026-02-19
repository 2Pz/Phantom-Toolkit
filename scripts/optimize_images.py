import io
import os
import time
import zipfile
from pathlib import Path

from PIL import Image


def optimize_zip(zip_path: Path):
    """
    Optimizes a zip file by converting images to WebP.
    """
    print(f"Processing {zip_path}...")
    original_size = zip_path.stat().st_size
    temp_zip_path = zip_path.with_suffix(".temp.zip")

    start_time = time.time()
    count = 0
    skipped = 0
    errors = 0

    try:
        with (
            zipfile.ZipFile(zip_path, "r") as zin,
            zipfile.ZipFile(temp_zip_path, "w", compression=zipfile.ZIP_STORED) as zout,
        ):
            # Use ZIP_STORED (no compression) for the container because WebP is already compressed.
            # This allows for faster random access seeking.

            for item in zin.infolist():
                data = zin.read(item.filename)

                # Check if it's an image we want to convert
                is_dds = item.filename.lower().endswith(".dds")
                is_png = item.filename.lower().endswith(".png")

                if is_dds or is_png:
                    try:
                        # Open image
                        img = Image.open(io.BytesIO(data))

                        # Convert to WebP
                        # Quality 90 is usually indistinguishable from source for UI assets
                        # Method 6 is slowest compression but best size/quality ratio
                        out_buffer = io.BytesIO()
                        img.save(out_buffer, format="WEBP", quality=90, method=6)
                        webp_data = out_buffer.getvalue()

                        # New filename
                        new_filename = (
                            Path(item.filename).with_suffix(".webp").as_posix()
                        )

                        # Create new ZipInfo
                        new_info = zipfile.ZipInfo(new_filename)
                        new_info.date_time = time.localtime(time.time())[:6]

                        # Write WebP data
                        zout.writestr(new_info, webp_data)
                        count += 1

                        if count % 100 == 0:
                            print(f"  Converted {count} items...", end="\r")

                    except Exception as e:
                        print(f"  Error converting {item.filename}: {e}")
                        # Fallback: write original
                        zout.writestr(item, data)
                        errors += 1
                else:
                    # Copy other files as-is
                    zout.writestr(item, data)
                    skipped += 1

        print(f"\nFinished processing {zip_path}.")
        print(f"Converted: {count}, Copied: {skipped}, Errors: {errors}")

        new_size = temp_zip_path.stat().st_size
        ratio = original_size / new_size if new_size > 0 else 0
        reduction = (original_size - new_size) / 1024 / 1024

        print(f"Original Size: {original_size / 1024 / 1024:.2f} MB")
        print(f"New Size:      {new_size / 1024 / 1024:.2f} MB")
        print(f"Reduction:     {reduction:.2f} MB ({ratio:.2f}x smaller)")
        print(f"Time taken:    {time.time() - start_time:.2f}s")

        # Replace original
        backup_path = zip_path.with_suffix(".bak.zip")
        if backup_path.exists():
            os.remove(backup_path)

        os.rename(zip_path, backup_path)
        os.rename(temp_zip_path, zip_path)
        print(f"Replaced original file. Backup saved to {backup_path.name}")

    except Exception as e:
        print(f"Fatal error processing {zip_path}: {e}")
        if temp_zip_path.exists():
            os.remove(temp_zip_path)
        raise


def main():
    root = Path(__file__).resolve().parents[1]
    items_dir = root / "items"

    # Locate all images.zip files
    targets = []

    # Check specific game paths
    for game in ["ds3", "eldenring"]:
        game_dir = items_dir / game
        if not game_dir.exists():
            continue

        # Check for various casings
        candidates = list(game_dir.glob("*mages.zip"))  # Images.zip, images.zip
        for c in candidates:
            # Avoid re-processing backups
            if ".bak" not in c.name and ".temp" not in c.name:
                targets.append(c)

    if not targets:
        print("No images.zip files found to optimize.")
        return

    print(f"Found {len(targets)} zip files to optimize.")
    for t in targets:
        optimize_zip(t)


if __name__ == "__main__":
    main()
