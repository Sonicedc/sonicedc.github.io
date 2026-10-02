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
        assert depiction['class'] == 'DepictionTabView' and depiction['tabs']
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
