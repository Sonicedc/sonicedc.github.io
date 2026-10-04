# sonicedc · Sileo repository

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

## Repository identity and Sileo project pages

The independent lavender ribbon mark is deployed as `CydiaIcon.png`, `CydiaIcon@2x.png`, and `CydiaIcon@3x.png` at the repository root, plus website favicon and touch-icon sizes. It is separate from CarCanvas’s package icon. The original generated asset is in `site/assets/repo-icon.png`.

Native package depictions follow [Sileo’s native depiction documentation](https://developer.getsileo.app/native-depictions), use version `0.4`, and contain About and Information tabs. Buttons use the documented `action` field. Feature sections come from `metadata/<package>_<version>.json`; the website and Sileo share the same package data. The deployment validates component requirements and local asset URLs.

The native depiction palette uses `tintColor: #BFA3F0` and `backgroundColor: #17131F`, with a wide abstract `headerImage` at `assets/sileo-header.png`. Body labels use explicit text colors and 16-point horizontal margins; headings and subheaders separate features, compatibility, and package metadata. No screenshots or promotional taglines are fabricated. Native rendering should be checked on-device; the automated checks validate JSON structure, asset URLs, and package integrity.
