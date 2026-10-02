# SonicEDC · Sileo repository

A static APT repository and responsive package catalog, hosted at **https://sonicedc.github.io/**.

Add to Sileo: `sileo://source/https://sonicedc.github.io/`.

## Included package

**CarCanvas 0.12.7** (`local.carcanvas`) — customizable CarPlay dashboard, cards, dock, appearance, and status bar. Requires a rootless jailbreak on **iOS 16.2**, ElleKit, and PreferenceLoader. The original `.deb` is preserved byte-for-byte. Its source matches `sonicedc/CarCanvas` at `f72f649a92ab79c52bd3e1c90d50dc4160a5922b` (apart from `.gitignore`). This is an in-development package.

## Publish a package or update

1. Copy a built `.deb` into `packages/`. To replace an old release, remove the older `.deb`. Keep its Package identifier stable and increase its Version so Sileo offers the update. Rootless packages normally use `iphoneos-arm64`.
2. Commit and push to `main`, or use GitHub’s **Add file → Upload files** in the `packages/` folder.
3. The **Build and publish Sileo repository** workflow reads each archive’s control metadata, generates the catalog and depictions, verifies checksums, and deploys GitHub Pages. Refresh Sources in Sileo after deployment completes.

No manual editing of `Packages` or `Release` is needed. GitHub Pages hosts files; management happens through this GitHub repository. The website does not upload packages or build tweak source code.

## Local build

```sh
python3 scripts/build_repo.py
python3 scripts/verify_repo.py
python3 -m http.server 8000 --directory dist
```

Python 3.9+ is required. Gzip, bzip2, and xz package control archives work without dependencies. Zstd control archives require `dpkg-deb` (available in the Ubuntu Actions runner).

Generated output lives in ignored `dist/`: `Release`, `Packages`, compressed indexes, package binaries, native Sileo JSON depictions, web depictions, and the catalog. Package and index hashes are generated from the actual bytes. Release metadata is unsigned; no signing key is included. Dependencies are referenced, not redistributed.

## GitHub Pages setup

The public repository must be named `sonicedc.github.io`. In **Settings → Pages → Build and deployment**, select **GitHub Actions**. The workflow publishes only `dist/`, keeping scripts and source templates out of the public deployment.

## Customize

- `site/index.html`: homepage structure and copy.
- `site/assets/style.css`: colors, layout, and responsive styles.
- `site/detail.html`: package detail template.
- `scripts/build_repo.py`: Sileo metadata and catalog generation.
- `packages/`: installable `.deb` packages.
