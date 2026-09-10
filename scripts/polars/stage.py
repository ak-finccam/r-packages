import argparse
import hashlib
import io
import json
import pathlib
import shutil
import tarfile
import zipfile

parser = argparse.ArgumentParser(description="Stage Polars archives in the R repository; does not push")
parser.add_argument("version")
args = parser.parse_args()
repo = pathlib.Path(__file__).resolve().parents[2]
work = repo / ".build/polars" / args.version
artifacts = work / "artifacts"
notices = repo / "licenses/polars" / args.version
recipe_path = repo / "recipes" / f"polars-{args.version}.json"
recipe = json.loads(recipe_path.read_text()) if recipe_path.exists() else json.loads((work / "upstream.json").read_text())
notice_files = sorted(notices.glob("*.txt"))
if len(notice_files) < 2:
    raise RuntimeError("Run collect-licenses.py and review the inventory before packaging")


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def existing(path):
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        return False
    record = next((item for item in recipe.get("published", []) if item["path"] == path.relative_to(repo).as_posix()), None)
    if record is None or sha256(path) != record["sha256"]:
        raise RuntimeError(f"Refusing to overwrite an existing archive: {path}")
    return True


def add_notices(original, destination, prefix):
    with tarfile.open(original) as incoming, tarfile.open(destination, "w:gz", compresslevel=6) as outgoing:
        for member in incoming:
            outgoing.addfile(member, incoming.extractfile(member) if member.isfile() else None)
        for path in notice_files:
            data = path.read_bytes()
            member = tarfile.TarInfo(prefix + path.name)
            member.size, member.mtime, member.mode = len(data), 0, 0o644
            outgoing.addfile(member, io.BytesIO(data))


source = repo / "src/contrib" / f"polars_{args.version}.tar.gz"
windows = repo / "bin/windows/contrib/4.5" / f"polars_{args.version}.zip"
linux = repo / "bin/linux/noble/4.5/src/contrib" / f"polars_{args.version}.tar.gz"
if not existing(source):
    add_notices(artifacts / source.name, source, "polars/inst/licenses/")
if not existing(windows):
    shutil.copyfile(artifacts / windows.name, windows)
    with zipfile.ZipFile(windows, "a", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in notice_files:
            archive.write(path, "polars/licenses/" + path.name)
if not existing(linux):
    shutil.copyfile(artifacts / f"polars_{args.version}_R_x86_64-pc-linux-gnu.tar.gz", linux)

release_dir = work / "release-assets"
release_dir.mkdir(exist_ok=True)
rust = release_dir / recipe["rust"]["filename"]
if not rust.exists():
    add_notices(artifacts / rust.name, rust, "licenses/")
for path in notice_files:
    shutil.copyfile(path, release_dir / path.name)
recipe["published"] = [{"path": path.relative_to(repo).as_posix(), "sha256": sha256(path), "bytes": path.stat().st_size} for path in [source, windows, linux]]
recipe["rustMirror"] = {"url": f"https://github.com/ak-finccam/r-packages/releases/download/polars-{args.version}/{rust.name}", "sha256": sha256(rust), "bytes": rust.stat().st_size, "modifications": "Added license notices; the static library is unchanged."}
recipe_path.parent.mkdir(exist_ok=True)
recipe_path.write_text(json.dumps(recipe, indent=2) + "\n")
shutil.copyfile(recipe_path, release_dir / recipe_path.name)
(release_dir / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sorted(release_dir.iterdir()) if path.is_file() and path.name != "SHA256SUMS"))
for record in recipe["published"]:
    print(record["path"], record["sha256"])
print("Release assets:", release_dir)
