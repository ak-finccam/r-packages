import concurrent.futures
import hashlib
import json
import pathlib
import re
import subprocess
import tarfile
import tomllib
import urllib.parse
import argparse

parser = argparse.ArgumentParser(description="Collect the locked Polars dependency licenses")
parser.add_argument("version")
args = parser.parse_args()
repository_root = pathlib.Path(__file__).resolve().parents[2]
root = repository_root / ".build/polars" / args.version
cache = root / "license-cache"
cache.mkdir(exist_ok=True)
packages = tomllib.loads((root / "src_rust_Cargo.lock").read_text())["package"]

def download(url, path, expected=None):
    if not path.exists():
        partial = path.with_suffix(path.suffix + ".part")
        subprocess.run(["curl", "-fL", "--retry", "3", "-sS", url, "-o", str(partial)], check=True)
        partial.replace(path)
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if expected and actual != expected:
        raise RuntimeError(f"Checksum mismatch: {path}")
    return path

def license_files(archive, prefix):
    result = []
    for member in archive:
        if not member.isfile() or not member.name.startswith(prefix + "/"):
            continue
        relative = member.name[len(prefix) + 1:]
        if re.match(r"(?i)^(licen[cs]e|copying|notice|copyright)([._-].*)?$", pathlib.PurePosixPath(relative).name):
            data = archive.extractfile(member).read()
            try:
                content = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                content = data.decode("latin-1")
            if "\x00" in content:
                raise RuntimeError(f"Non-text license: {member.name}")
            result.append({"path": relative, "text": content})
    return result

def registry_package(package):
    name, version = package["name"], package["version"]
    url = f"https://static.crates.io/crates/{name}/{name}-{version}.crate"
    path = download(url, cache / f"{name}-{version}.crate", package["checksum"])
    with tarfile.open(path) as archive:
        prefix = f"{name}-{version}"
        manifest = tomllib.loads(archive.extractfile(prefix + "/Cargo.toml").read().decode())
        info = manifest["package"]
        licenses = license_files(archive, prefix)
        license_file = info.get("license-file")
        if license_file and license_file not in [entry["path"] for entry in licenses]:
            licenses.append({"path": license_file, "text": archive.extractfile(prefix + "/" + license_file).read().decode()})
    return {"name": name, "version": version, "license": info.get("license", ""), "repository": info.get("repository", ""), "source": url, "sha256": package["checksum"], "notices": licenses}

registry = [p for p in packages if p.get("source", "").startswith("registry+")]
records = []
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
    for index, record in enumerate(executor.map(registry_package, registry), 1):
        records.append(record)
        if index % 50 == 0:
            print(f"Checked {index}/{len(registry)} registry packages", flush=True)

git_groups = {}
for package in packages:
    if package.get("source", "").startswith("git+"):
        git_groups.setdefault(package["source"], []).append(package)
for source, members in git_groups.items():
    parsed = urllib.parse.urlsplit(source[4:])
    repo = parsed.path.removesuffix(".git").strip("/")
    commit = parsed.fragment
    url = f"https://codeload.github.com/{repo}/tar.gz/{commit}"
    path = download(url, cache / f"{repo.replace('/', '-')}-{commit}.tar.gz")
    with tarfile.open(path) as archive:
        prefix = archive.getmembers()[0].name.rstrip("/")
        notices = license_files(archive, prefix)
        manifests = []
        for item in archive:
            if item.isfile() and pathlib.PurePosixPath(item.name).name == "Cargo.toml":
                manifest = tomllib.loads(archive.extractfile(item).read().decode())
                manifests.append((item.name, manifest))
        workspace = next((value.get("workspace", {}).get("package", {}) for name, value in manifests if name == prefix + "/Cargo.toml"), {})
        for package in members:
            info = next(value["package"] for name, value in manifests if value.get("package", {}).get("name") == package["name"])
            license_name = info.get("license", "")
            if isinstance(license_name, dict):
                license_name = workspace["license"]
            records.append({"name": package["name"], "version": package["version"], "license": license_name, "repository": f"https://github.com/{repo}", "source": source, "notices": notices})
    print(f"Checked Git dependency {repo}: {len(members)} crates", flush=True)

for record in records:
    if record["notices"]:
        continue
    if record["name"].startswith("winapi-"):
        parent = next(item for item in records if item["name"] == "winapi")
        record["notices"] = parent["notices"]
        record["notice_source"] = parent["source"]
        continue
    path = cache / f'{record["name"]}-{record["version"]}.crate'
    with tarfile.open(path) as archive:
        vcs_member = next(item for item in archive if item.name.endswith(".cargo_vcs_info.json"))
        vcs = json.loads(archive.extractfile(vcs_member).read())
    repo = "/".join(urllib.parse.urlsplit(record["repository"]).path.strip("/").split("/")[:2])
    commit = vcs["git"]["sha1"]
    url = f"https://codeload.github.com/{repo}/tar.gz/{commit}"
    path = download(url, cache / f"{repo.replace('/', '-')}-{commit}.tar.gz")
    with tarfile.open(path) as archive:
        prefix = archive.getmembers()[0].name.rstrip("/")
        record["notices"] = license_files(archive, prefix)
    if not record["notices"]:
        with tarfile.open(path) as archive:
            record["notices"] = [{"path": item.name, "text": archive.extractfile(item).read().decode()} for item in archive if item.isfile() and (item.name.endswith("/README.md") or item.name.endswith("/AUTHORS"))]
    record["notice_source"] = url
    print(f"Retrieved source notices: {record['name']}", flush=True)

assert all(record["notices"] for record in records)
nightly = tomllib.loads((root / "src_rust_rust-toolchain.toml").read_text())["toolchain"]["channel"]
nightly_date = nightly.removeprefix("nightly-")
manifest = root / "license-cache" / f"rust-{nightly}.toml"
if not manifest.exists():
    subprocess.run(["curl", "-fLsS", f"https://static.rust-lang.org/dist/{nightly_date}/channel-rust-nightly.toml", "-o", str(manifest)], check=True)
metadata = tomllib.loads(manifest.read_text())
source = metadata["pkg"]["rust-src"]["target"]["*"]
path = root / "license-cache" / f"rust-src-{nightly}.tar.xz"
if not path.exists():
    subprocess.run(["curl", "-fLsS", "--retry", "3", source["xz_url"], "-o", str(path)], check=True)
with path.open("rb") as stream:
    assert hashlib.file_digest(stream, "sha256").hexdigest() == source["xz_hash"]
with tarfile.open(path) as archive:
    notices = [{"path": member.name, "text": archive.extractfile(member).read().decode()} for member in archive if member.isfile() and re.match(r"(?i)^(license|copying|notice|copyright)([._-].*)?$", pathlib.PurePosixPath(member.name).name)]
records.append({"name": "Rust standard library", "version": metadata["pkg"]["rust"]["version"], "license": "MIT OR Apache-2.0; see component notices", "source": source["xz_url"], "notices": notices})
(root / "license-records.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
output = repository_root / "licenses/polars" / args.version
output.mkdir(parents=True, exist_ok=True)
subprocess.run(["curl", "-fLsS", f"https://raw.githubusercontent.com/pola-rs/r-polars/v{args.version}/LICENSE.md", "-o", str(output / "LICENSE-MIT.txt")], check=True)
parts = [f"Polars {args.version}: third-party licenses and notices\n\nThis inventory conservatively includes all dependencies in the release Cargo.lock, including build-time and other-platform dependencies. Their inclusion does not mean every component is present in each binary. Where MIT or Apache-2.0 is offered as an alternative to LGPL, distribution uses the permissive alternative.\n"]
seen = {}
for record in records:
    parts.append("\n" + "=" * 78 + "\n" + record["name"] + " " + record["version"] + "\nDeclared license: " + record["license"] + "\nSource: " + record["source"] + "\n")
    for notice in record["notices"]:
        content = notice["text"]
        digest = hashlib.sha256(content.encode()).hexdigest()
        if digest in seen:
            parts.append("\n" + notice["path"] + ": same notice as " + seen[digest] + "\n")
        else:
            seen[digest] = record["name"] + " " + record["version"] + ": " + notice["path"]
            parts.append("\n--- " + notice["path"] + " ---\n" + content + "\n")
(output / "THIRD-PARTY-NOTICES.txt").write_text("".join(parts), encoding="utf-8")
print("License bundle:", len(records), "packages;", len(seen), "distinct notice texts;", (output / "THIRD-PARTY-NOTICES.txt").stat().st_size, "bytes", flush=True)


(output / "inventory.json").write_text(json.dumps([{k: v for k, v in item.items() if k != "notices"} for item in records], indent=2) + "\n", encoding="utf-8")
