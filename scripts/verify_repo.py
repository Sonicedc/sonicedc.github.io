#!/usr/bin/env python3
"""Verify the deployed APT metadata, archives, catalog, and local web links."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlsplit, unquote
import bz2, gzip, hashlib, json, re
from build_repo import OUT, ROOT, BASE, control_from_deb, parse_control

class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in ('href', 'src') and value:
                self.links.append(value)


REQUIRED = {
    'DepictionTabView': ('minVersion', 'tabs'),
    'DepictionStackView': ('tabname', 'views'),
    'DepictionHeaderView': ('title',),
    'DepictionSubheaderView': ('title',),
    'DepictionMarkdownView': ('markdown',),
    'DepictionImageView': ('URL', 'width', 'height', 'cornerRadius'),
    'DepictionTableTextView': ('title', 'text'),
    'DepictionTableButtonView': ('title', 'action'),
    'DepictionButtonView': ('action',),
    'DepictionSeparatorView': (),
    'DepictionLabelView': ('text',),
    'DepictionSpacerView': ('spacing',),
    'DepictionScreenshotsView': ('screenshots', 'itemSize', 'itemCornerRadius'),
}

def verify_native(view):
    assert view['class'] in REQUIRED, f"Unknown depiction class: {view['class']}"
    for field in REQUIRED[view['class']]:
        assert field in view, f"Missing {field} in {view['class']}"
    assert 'link' not in view, 'Sileo buttons require action, not link'
    assert view['class'] != 'DepictionLabelView', 'Fixed-height single-line labels truncate mobile copy; use Markdown'
    if view['class'] == 'DepictionMarkdownView':
        assert view.get('useMargins') is True and view.get('useSpacing') is True
    for field in ('URL', 'action', 'headerImage'):
        url = view.get(field, '')
        if url.startswith(BASE + '/'):
            assert (OUT / url.removeprefix(BASE + '/')).exists(), f'Broken depiction asset: {url}'
    if view['class'] == 'DepictionScreenshotsView':
        assert len(view['screenshots']) == 3
        for shot in view['screenshots']:
            assert shot['accessibilityText']
            assert (OUT / shot['url'].removeprefix(BASE + '/')).exists()
        for device in ('iphone', 'ipad'):
            if device in view:
                verify_native(view[device])
    for key in ('tabs', 'views'):
        for child in view.get(key, []):
            verify_native(child)

def main():
    index = (OUT / 'Packages').read_bytes()
    assert gzip.decompress((OUT / 'Packages.gz').read_bytes()) == index
    assert bz2.decompress((OUT / 'Packages.bz2').read_bytes()) == index
    records = [parse_control(s) for s in index.decode().strip().split('\n\n')]
    catalog = json.loads((OUT / 'catalog.json').read_text())
    assert len(records) == len(catalog) > 0
    for fields in records:
        target = OUT / fields['Filename']
        payload = target.read_bytes()
        original = ROOT / 'packages' / target.name
        assert payload == original.read_bytes(), 'Package bytes changed'
        original_fields = parse_control(control_from_deb(original))
        for key, value in original_fields.items():
            if key not in ('Depiction', 'SileoDepiction', 'Icon', 'Filename', 'Size', 'MD5sum', 'SHA1', 'SHA256', 'SHA512'):
                assert fields[key] == value, f'Changed package metadata: {key}'
        assert int(fields['Size']) == len(payload)
        for field, algorithm in [('MD5sum','md5'),('SHA1','sha1'),('SHA256','sha256'),('SHA512','sha512')]:
            assert fields[field] == hashlib.new(algorithm, payload).hexdigest()
        for field in ['Depiction', 'SileoDepiction']:
            path = OUT / fields[field].removeprefix(BASE + '/')
            assert path.exists()
        depiction = json.loads((OUT / fields['SileoDepiction'].removeprefix(BASE + '/')).read_text())
        assert depiction['class'] == 'DepictionTabView' and depiction['minVersion'] == '0.4'
        assert depiction['headerImage'].endswith('/assets/sileo-header.png')
        assert depiction['tintColor'] == '#BFA3F0'
        assert depiction['backgroundColor'] == '#17131F'
        verify_native(depiction)
    icon = (OUT / 'CydiaIcon.png').read_bytes()
    assert icon[:8] == b'\x89PNG\r\n\x1a\n'
    import struct
    assert struct.unpack('>II', icon[16:24]) == (256, 256)
    assert icon != (OUT / 'assets/carcanvas.png').read_bytes(), 'Repo icon must be independent'
    featured = json.loads((OUT / 'sileo-featured.json').read_text())
    assert featured['class'] == 'FeaturedBannersView'
    assert featured['itemSize'] == '{263, 148}' and featured['itemCornerRadius'] == 10
    package_ids = {record['Package'] for record in records}
    assert featured['banners'], 'Featured catalog must contain a banner'
    for banner in featured['banners']:
        assert banner['title'] and banner['package'] in package_ids
        assert isinstance(banner['hideShadow'], bool)
        assert banner['url'].startswith(BASE + '/')
        image_path = OUT / banner['url'].removeprefix(BASE + '/')
        image = image_path.read_bytes()
        assert image[:8] == b'\x89PNG\r\n\x1a\n'
        width, height = struct.unpack('>II', image[16:24])
        assert (width, height) == (1920, 1080), 'Featured banner must be 1920x1080'
    algorithm = None
    for line in (OUT / 'Release').read_text().splitlines():
        if line in ('MD5Sum:', 'SHA1:', 'SHA256:', 'SHA512:'):
            algorithm = {'MD5Sum:':'md5','SHA1:':'sha1','SHA256:':'sha256','SHA512:':'sha512'}[line]
        elif line.startswith(' '):
            checksum, size, name = line.split()
            payload = (OUT / name).read_bytes()
            assert len(payload) == int(size)
            assert hashlib.new(algorithm, payload).hexdigest() == checksum
    for page in OUT.rglob('*.html'):
        text = page.read_text()
        assert not re.search(r'\{\{\w+\}\}', text), f'Unfilled template: {page}'
        parser = Links()
        parser.feed(text)
        for link in parser.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (OUT / unquote(parsed.path).lstrip('/')) if parsed.path.startswith('/') else page.parent / unquote(parsed.path)
            assert target.exists(), f'Broken local link in {page}: {link}'
    print(f'PASS: {len(records)} package(s); archive metadata, all hashes, compressed indexes, depictions, catalog, and local HTML links verified.')

if __name__ == '__main__':
    main()
