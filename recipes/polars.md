# Polars binary recipe

Polars **1.15.0** is retained here for **Windows x86-64 / R 4.5** and **Ubuntu Noble x86-64 / R 4.5.2**.

| Artifact | Location |
|---|---|
| Windows binary | `bin/windows/contrib/4.5/polars_1.15.0.zip` |
| Linux binary | `bin/linux/noble/4.5/src/contrib/polars_1.15.0.tar.gz` |
| Source package | `src/contrib/polars_1.15.0.tar.gz` |
| Prebuilt Rust library | [GitHub release polars-1.15.0](https://github.com/ak-finccam/r-packages/releases/tag/polars-1.15.0) |
| Inputs, build image and SHA-256 checksums | [polars-1.15.0.json](polars-1.15.0.json) |

The Windows binary and source package came from R-multiverse. They were repackaged only to include license notices. The Linux package was built with `R CMD INSTALL --build` in the exact finccam CI base image recorded in the JSON, linking upstream's `libr_polars` **1.15.0-rc.1**. The build had networking disabled and no Rust compiler. The Rust release archive adds notices without changing the static library.

Both finished binaries passed a fresh-library test covering Parquet write/read, nulls, dates, projection and filtering. The Linux test ran offline in a fresh instance of the pinned base image.

## Reproduce or update

Use Python 3.11+, curl, R 4.5 and Docker; the Linux build requires access to finccam's ACR. Run from this repository's root. The shell commands below use Bash (WSL works).

1. Select a version and verify the upstream inputs. For a new version, `prepare.py` requires that version still to be current on R-multiverse; it never silently substitutes another version.

   ```sh
   version=1.15.0
   python3 scripts/polars/prepare.py "$version"
   python3 scripts/polars/collect-licenses.py "$version"
   ```

2. Review `licenses/polars/$version/inventory.json` and the generated notices. The collector covers the entire locked Rust dependency set, including other-platform/build dependencies, and the pinned Rust standard library. It collects notices, but does not automatically approve new licenses. Retain MIT/Apache/BSD and applicable third-party notices in every archive.

3. Build against the deployment image, using the image digest and dependency versions in the JSON recipe. For this release:

   ```sh
   image=finccam.azurecr.io/r-linux-base@sha256:144da7aa87808b799cf1a40becf5b56d70adf467af55cde5c9e39568a8a7b2ac
   work=".build/polars/$version"
   az acr login --name finccam
   mkdir -p "$work/library"
   docker run --rm -v "$PWD:/repo" -w /repo --entrypoint Rscript "$image" -e "install.packages(c('rlang', 'S7'), lib='$work/library', repos='https://packagemanager.posit.co/cran/__linux__/noble/latest')"
   docker run --rm --network none -v "$PWD:/repo" -w /repo --entrypoint bash "$image" \
     scripts/polars/build-linux.sh "$work/artifacts/polars_$version.tar.gz" \
     "$work/artifacts/libr_polars-1.15.0-rc.1-x86_64-unknown-linux-gnu.tar.gz" \
     "licenses/polars/$version" "$work/library" "$work/artifacts"
   ```

   `build-linux.sh` verifies R **4.5.2**, rlang **1.3.0**, S7 **0.2.2**, Noble and x86-64 before building. When updating, choose and pin the new build/dependency versions deliberately, update these assertions, the Rust filename, and the JSON's `linuxBuild` record. An R, distro or architecture upgrade needs its own verified binary/repository path.

4. Stage the files and regenerate indexes:

   ```sh
   python3 scripts/polars/stage.py "$version"
   Rscript -e 'source("scripts/polars/update-indexes.R")'
   ```

   Staging refuses to overwrite an existing archive unless it matches the recorded checksum. Keep previous versions and use a new version for changed package code. For a new release, copy the generated input/build metadata into `recipes/polars-$version.json` and record the tested image/dependencies. The index script retains all versions and excludes legacy Linux binary archives from the source index.

5. Install the staged Windows/Linux binaries into fresh libraries and run `Rscript -e 'source("scripts/polars/smoke-test.R")'` with the verification library first in `.libPaths()`. Update its expected version when upgrading. Also verify an empty-cache `renv::restore()` from the hosted repository, so a warm cache cannot hide broken hosting.

6. Commit and push the repository files. Publish `.build/polars/$version/release-assets/*` as assets of a GitHub release named `polars-$version`, with the license texts and checksums. The large Rust archive belongs in Releases, not Git. Wait for GitHub Pages and verify the published checksums before updating the engine's lockfile. Do not replace assets in a published release.

## Restoring after upstream files disappear

The repository retains the source and both finished R binaries. The release retains the prebuilt Rust library. Use the `published` and `rustMirror` URLs/checksums in the JSON to download these preserved copies; the `source`/`windows`/`rust` fields document the original upstream archives and their hashes. The mirrored source and Rust library can be passed directly to `build-linux.sh`; their only additions are notices. No upstream binary service is needed to install the retained R binaries.

## Repository URLs

Windows: `https://ak-finccam.github.io/r-packages`.

Linux: `https://ak-finccam.github.io/r-packages/bin/linux/noble/4.5`.

The Linux `src/contrib` directory deliberately serves **installed binary packages**, following the Linux repository convention; the archives contain a `Built` field and R installs them without compilation. Do not use this Linux URL on another distro/architecture/R minor version. Keep the root repository configured separately for source-only fork packages such as Rblpapi.
