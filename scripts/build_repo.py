#!/usr/bin/env python3
"""Build a flat APT/Sileo repository and static catalog using only Python's stdlib."""
from pathlib import Path
from datetime import datetime, timezone
from html import escape
import bz2, gzip, hashlib, io, json, re, shutil, subprocess, tarfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'dist'
BASE = 'https://sonicedc.github.io'

def control_from_deb(path):
    data = path.read_bytes()
    if data[:8] != b'!<arch>\n':
        raise ValueError(f'{path.name}: invalid Debian archive')
    pos = 8
    while pos + 60 <= len(data):
        header = data[pos:pos+60]
        size = int(header[48:58])
        name = header[:16].decode().strip().rstrip('/')
        body = data[pos+60:pos+60+size]
        if name.startswith('control.tar'):
            # dpkg on Linux also handles zstd-compressed control archives.
            if name.endswith('.zst'):
                return subprocess.check_output(['dpkg-deb', '-f', str(path)], text=True)
            with tarfile.open(fileobj=io.BytesIO(body), mode='r:*') as archive:
                member = next(m for m in archive.getmembers() if m.name.lstrip('./') == 'control')
                return archive.extractfile(member).read().decode('utf-8')
        pos += 60 + size + size % 2
    raise ValueError(f'{path.name}: missing control archive')

def parse_control(text):
    fields = {}
    key = None
    for line in text.strip().splitlines():
        if line.startswith((' ', '\t')) and key:
            fields[key] += '\n' + line
        else:
            key, sep, value = line.partition(':')
            if not sep:
                raise ValueError('Malformed control field')
            fields[key] = value.strip()
    for name in ('Package', 'Name', 'Version', 'Architecture', 'Description'):
        if not fields.get(name):
            raise ValueError(f'Missing {name}')
    if not re.fullmatch(r'[a-z0-9][a-z0-9+.-]+', fields['Package']):
        raise ValueError('Unsafe package identifier')
    return fields

def digest(data, algorithm):
    return hashlib.new(algorithm, data).hexdigest()

def depiction_html(text):
    def inline(value):
        rendered = escape(value)
        rendered = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', rendered)
        return re.sub(r'`([^`]+)`', r'<code>\1</code>', rendered)
    parts = []
    for block in text.split('\n\n'):
        lines = block.splitlines()
        if not lines:
            continue
        if lines[0].startswith('**') and lines[0].endswith('**'):
            parts.append('<h3>' + escape(lines.pop(0)[2:-2]) + '</h3>')
        if lines and all(line.startswith('- ') for line in lines):
            parts.append('<ul>' + ''.join('<li>' + inline(line[2:]) + '</li>' for line in lines) + '</ul>')
        elif lines:
            parts.append('<p>' + '<br>'.join(inline(line) for line in lines) + '</p>')
    return ''.join(parts)

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(ROOT / 'site', OUT)
    (OUT / 'debs').mkdir()
    (OUT / 'depictions').mkdir()
    records, stanzas, seen = [], [], set()
    for deb in sorted((ROOT / 'packages').glob('*.deb')):
        fields = parse_control(control_from_deb(deb))
        identity = tuple(fields[k] for k in ('Package', 'Version', 'Architecture'))
        if identity in seen:
            raise ValueError(f'Duplicate package/version/architecture: {identity}')
        seen.add(identity)
        package = fields['Package']
        is_carcanvas = package in ('local.carcanvas', 'com.sonicedc.carcanvas')
        if not re.fullmatch(r'[A-Za-z0-9_.+-]+\.deb', deb.name):
            raise ValueError(f'Unsafe package filename: {deb.name}')
        payload = deb.read_bytes()
        shutil.copy2(deb, OUT / 'debs' / deb.name)
        fields.update(Filename=f'debs/{deb.name}', Size=str(len(payload)),
                      MD5sum=digest(payload, 'md5'), SHA1=digest(payload, 'sha1'),
                      SHA256=digest(payload, 'sha256'), SHA512=digest(payload, 'sha512'))
        # Use a version-specific depiction so every indexed release has accurate metadata.
        slug = hashlib.sha256('|'.join(identity).encode()).hexdigest()[:16]
        depiction = OUT / 'depictions' / slug
        depiction.mkdir()
        fields['Depiction'] = f'{BASE}/depictions/{slug}/'
        fields['SileoDepiction'] = f'{BASE}/depictions/{slug}/sileo.json'
        if is_carcanvas:
            fields['Icon'] = f'{BASE}/assets/carcanvas.png'
        stanzas.append('\n'.join(f'{key}: {value}' for key, value in fields.items()))
        record = {key: fields[key] for key in ('Package', 'Name', 'Version', 'Architecture', 'Description', 'Depends', 'Filename', 'Size', 'SHA256', 'Depiction') if key in fields}
        record['path'] = f'depictions/{slug}/'
        record['icon'] = 'assets/carcanvas.png' if is_carcanvas else 'assets/favicon.svg'
        record['compatibility'] = (('iOS 15+ · Rootless' if package == 'com.sonicedc.carcanvas' else 'iOS 16.2 · Rootless') if is_carcanvas else fields['Architecture'])
        records.append(record)
        info = [('Version', fields['Version']), ('Architecture', fields['Architecture']), ('Dependencies', fields.get('Depends', 'None specified'))]
        text = '' if is_carcanvas else fields['Description'].split('\n')[0]
        if is_carcanvas:
            text += '\n\nCustomize your CarPlay dashboard, cards, dock, appearance, and status bar from Settings.'
        metadata_path = ROOT / 'metadata' / (package + '_' + fields['Version'] + '.json')
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
            text += '\n\n' + metadata['details']
        depiction_json = {'class': 'DepictionTabView', 'minVersion': '0.1', 'tintColor': '#9B72CF', 'tabs': [
            {'class': 'DepictionStackView', 'tabname': 'Details', 'views': [
                {'class': 'DepictionHeaderView', 'title': fields['Name']},
                {'class': 'DepictionMarkdownView', 'markdown': text, 'useSpacing': True},
                *[{'class': 'DepictionTableTextView', 'title': label, 'text': value} for label, value in info],
                {'class': 'DepictionButtonView', 'text': 'Source code', 'link': 'https://github.com/sonicedc/CarCanvas' if is_carcanvas else 'https://github.com/sonicedc/sonicedc.github.io'}]}]}
        (depiction / 'sileo.json').write_text(json.dumps(depiction_json, indent=2) + '\n')
        details = ''.join(f'<div><dt>{escape(k)}</dt><dd>{escape(v)}</dd></div>' for k,v in info)
        content = f'''<a class="back" href="/">← All packages</a><div class="detail-heading"><img src="/{record['icon']}" alt="" width="96" height="96"><div><p class="eyebrow">{escape(fields['Section'] if 'Section' in fields else 'Package')}</p><h1>{escape(fields['Name'])}</h1><p class="muted">{escape(record['compatibility'])}</p></div></div><div class="detail-body">{depiction_html(text)}<dl>{details}</dl><a class="button primary" href="sileo://source/{BASE}/">Add repository to Sileo <span>↗</span></a><p class="checksum">SHA-256<br><code>{fields['SHA256']}</code></p></div>'''
        template = (ROOT / 'site' / 'detail.html').read_text()
        (depiction / 'index.html').write_text(template.replace('{{TITLE}}', escape(fields['Name'])).replace('{{CONTENT}}', content))
    if not records:
        raise ValueError('Add at least one .deb to packages/ before building')
    packages = ('\n\n'.join(stanzas) + '\n\n').encode()
    (OUT / 'Packages').write_bytes(packages)
    (OUT / 'Packages.gz').write_bytes(gzip.compress(packages, mtime=0))
    (OUT / 'Packages.bz2').write_bytes(bz2.compress(packages))
    stamp = datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')
    architectures = ' '.join(sorted({record['Architecture'] for record in records}))
    release = f'Origin: sonicedc\nLabel: sonicedc\nSuite: stable\nVersion: 1.0\nCodename: sonicedc\nArchitectures: {architectures}\nComponents: main\nDescription: sonicedc packages for Sileo\nDate: {stamp}\n'
    for label, algorithm in [('MD5Sum', 'md5'), ('SHA1', 'sha1'), ('SHA256', 'sha256'), ('SHA512', 'sha512')]:
        release += f'{label}:\n'
        for name in ['Packages', 'Packages.gz', 'Packages.bz2']:
            payload = (OUT / name).read_bytes()
            release += f' {digest(payload, algorithm)} {len(payload)} {name}\n'
    (OUT / 'Release').write_text(release)
    (OUT / 'catalog.json').write_text(json.dumps(records, indent=2) + '\n')
    cards = ''
    for record in records:
        cards += f'''<a class="package-card" href="{record['path']}"><div class="package-top"><img src="{record['icon']}" alt="" width="76" height="76"><span class="version">v{escape(record['Version'])}</span></div><div class="package-title"><h3>{escape(record['Name'])}</h3><span aria-hidden="true">↗</span></div><p>{escape(record['Description'].split(chr(10))[0])}</p><div class="package-bottom"><span>{escape(record['compatibility'])}</span><span>View package →</span></div></a>'''
    index = (OUT / 'index.html').read_text().replace('{{CARDS}}', cards).replace('{{COUNT}}', str(len(records))).replace('{{UPDATED}}', datetime.now(timezone.utc).strftime('%b %d, %Y'))
    (OUT / 'index.html').write_text(index)
    (OUT / 'detail.html').unlink()
    (OUT / '.nojekyll').touch()
    print(f'Built {len(records)} package(s) into {OUT}')

if __name__ == '__main__':
    main()
