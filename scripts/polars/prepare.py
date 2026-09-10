import hashlib
import json
import pathlib
import subprocess
import tarfile
import urllib.request
import zipfile
import argparse

parser = argparse.ArgumentParser(description="Download and verify a pinned Polars release")
parser.add_argument("version")
args = parser.parse_args()
repo = pathlib.Path(__file__).resolve().parents[2]
root = repo / ".build/polars" / args.version
root.mkdir(parents=True, exist_ok=True)
artifacts = root / "artifacts"
artifacts.mkdir(exist_ok=True)

def download(url, path, expected=None):
    if not path.exists():
        temporary = path.with_suffix(path.suffix + ".part")
        subprocess.run(["curl", "--fail", "--location", "--retry", "3", "--silent", "--show-error", url, "--output", str(temporary)], check=True)
        temporary.replace(path)
    actual = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
    if expected and actual != expected:
        raise RuntimeError(f"Checksum mismatch: {path}")
    print(f"{path.name}: {path.stat().st_size} bytes; sha256={actual}", flush=True)
    return {"url": url, "filename": path.name, "sha256": actual}

recipe_path = repo / "recipes" / f"polars-{args.version}.json"
if recipe_path.exists():
    recipe = json.loads(recipe_path.read_text())
else:
    metadata_path = root / "metadata.json"
    download("https://community.r-multiverse.org/api/packages/polars", metadata_path)
    metadata = json.loads(metadata_path.read_text())
    if metadata["Version"] != args.version:
        raise RuntimeError("Requested version is no longer current; use the archived recipe and artifacts")
    windows = next(item for item in metadata["_binaries"] if item["os"] == "win" and item["r"].startswith("4.5.") and item["arch"] == "x86_64")
    recipe = {"version": args.version,
              "source": {"url": metadata["_fileid"], "filename": metadata["_file"], "sha256": metadata["_sha256"]},
              "windows": {"url": windows["fileid"], "filename": f"polars_{args.version}.zip", "sha256": windows["fileid"].rsplit("/", 1)[1]}}
source = download(recipe["source"]["url"], artifacts / recipe["source"]["filename"], recipe["source"]["sha256"])
windows = download(recipe["windows"]["url"], artifacts / recipe["windows"]["filename"], recipe["windows"]["sha256"])
with tarfile.open(artifacts / source["filename"]) as archive:
    sums = archive.extractfile("polars/tools/lib-sums.tsv").read().decode()
    for name in ["src/rust/Cargo.lock", "src/rust/Cargo.toml", "src/rust/rust-toolchain.toml", "DESCRIPTION", "LICENSE", "LICENSE.md"]:
        member = next((item for item in archive if item.name == "polars/" + name), None)
        if member:
            output = root / (name.replace("/", "_"))
            output.write_bytes(archive.extractfile(member).read())
    print("Source license files:", [m.name for m in archive if any(word in m.name.lower() for word in ["license", "notice", "copying"] )][:30])
url, digest = next(line.split("\t") for line in sums.splitlines() if "x86_64-unknown-linux-gnu.tar.gz" in line)
library = download(url, artifacts / url.rsplit("/", 1)[1], digest)
with zipfile.ZipFile(artifacts / windows["filename"]) as archive:
    print("Windows license files:", [n for n in archive.namelist() if any(word in n.lower() for word in ["license", "notice", "copying"])][:30])
(root / "upstream.json").write_text(json.dumps({"version": args.version, "source": source, "windows": windows, "rust": library}, indent=2) + "\n")
