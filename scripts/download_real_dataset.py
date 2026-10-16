from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path


DATASET_ID = "pf2w725pw3"
VERSION = 1
BASE = f"https://data.mendeley.com/public-files/datasets/{DATASET_ID}/files"
FILES = {
    "Customer_Order.csv": (
        "d08bf859-1fc8-4469-922f-13be7516a30c",
        "e28ae8ac9b368b9496b153fafb5af685bd94ba1530ffcb308dfcd5403601f325",
    ),
    "Picking_Wave.csv": (
        "dff20565-5df8-4b77-ad9d-8b034069bcca",
        "4065a8a94f68c402ef4543245373ac91f6835ecdf34a1e4674cb6981b394b88c",
    ),
    "Product.csv": (
        "0be2b552-260d-43f2-9e36-fb4a3e71f85d",
        "416527e5260c17003177e1389fd48042d9790be9ef9cabe4c6c07e583e01eb2f",
    ),
    "Storage_Location.csv": (
        "05e3b706-3723-4202-b07e-c0609cdd5ea8",
        "2895d9da16b4d63e85a17bfe050cc77b72d5654298072d6fa3b1732b1c1d6cc3",
    ),
    "Support_Points_Navigation.csv": (
        "ffdf3f29-9977-472d-b3cc-f0da6b483a68",
        "848dd2bafd5cce8506555e5fc83369eb985cb446edd84d3fa259f19be449c479",
    ),
    "README.txt": (
        "15cfd855-69df-418b-b767-2b5ae7e58f1f",
        "123b25c62bcfab3e4506ae77ba391915f5ed5f236559e24435b17efb02077df9",
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    target = root / "data" / "external" / "order_picking_mendeley" / "raw"
    target.mkdir(parents=True, exist_ok=True)
    manifest = {
        "dataset": "Order Picking Dataset from a Warehouse of a Footwear Manufacturing Company",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "doi": "10.17632/pf2w725pw3.1",
        "license": "CC BY 4.0",
        "source": "https://data.mendeley.com/datasets/pf2w725pw3/1",
        "files": {},
    }
    for filename, (file_id, expected_hash) in FILES.items():
        destination = target / filename
        if destination.exists() and sha256(destination) == expected_hash:
            print(f"已校验：{filename}")
        else:
            url = f"{BASE}/{file_id}/file_downloaded"
            temporary = destination.with_suffix(destination.suffix + ".part")
            request = urllib.request.Request(url, headers={"User-Agent": "warehouse-agent/1.0"})
            print(f"下载：{filename}")
            with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as output:
                while block := response.read(1024 * 1024):
                    output.write(block)
            actual_hash = sha256(temporary)
            if actual_hash != expected_hash:
                temporary.unlink(missing_ok=True)
                raise RuntimeError(f"checksum mismatch for {filename}: {actual_hash}")
            temporary.replace(destination)
        manifest["files"][filename] = {
            "sha256": expected_hash,
            "bytes": destination.stat().st_size,
        }
    (target.parent / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"完成：{target}")


if __name__ == "__main__":
    main()
