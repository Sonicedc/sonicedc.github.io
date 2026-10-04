#!/usr/bin/env python3
"""Build a flat APT/Sileo repository and static catalog using only Python's stdlib."""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
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
        is_importone = package == 'com.sonicedc.importone'
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
        if is_importone:
            fields['Icon'] = f'{BASE}/assets/importone.png'
        stanzas.append('\n'.join(f'{key}: {value}' for key, value in fields.items()))
        record = {key: fields[key] for key in ('Package', 'Name', 'Version', 'Architecture', 'Description', 'Depends', 'Filename', 'Size', 'SHA256', 'Depiction') if key in fields}
        record['path'] = f'depictions/{slug}/'
        record['icon'] = 'assets/carcanvas.png' if is_carcanvas else ('assets/importone.png' if is_importone else 'assets/repo-icon.png')
        record['compatibility'] = (('iOS 15+ · Rootless' if package == 'com.sonicedc.carcanvas' else 'iOS 16.2 · Rootless') if is_carcanvas else ('iOS 15+ · Rootless' if is_importone else fields['Architecture']))
        records.append(record)
        source_url = 'https://github.com/sonicedc/CarCanvas' if is_carcanvas else ('https://github.com/sonicedc/Importone' if is_importone else 'https://github.com/sonicedc/sonicedc.github.io')
        info = [('Version', fields['Version']), ('Package', package),
                ('Architecture', fields['Architecture']),
                ('Author', fields.get('Author', fields.get('Maintainer', 'sonicedc'))),
                ('Dependencies', fields.get('Depends', 'None specified'))]
        summary = ('Customize your CarPlay dashboard, cards, dock, appearance, and status bar from Settings.'
                   if is_carcanvas else fields['Description'].split('\n')[0])
        metadata_path = ROOT / 'metadata' / (package + '_' + fields['Version'] + '.json')
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        sections, notes = [], []
        for block in metadata.get('details', '').split('\n\n'):
            lines = block.strip().splitlines()
            if not lines:
                continue
            if lines[0].startswith('**') and lines[0].endswith('**'):
                sections.append((lines[0][2:-2], '\n'.join(lines[1:])))
            else:
                notes.append(block.strip())
        # Sileo labels are single-line with a fixed 20-point content height.
        # Markdown calculates its height from the available width and wraps naturally.
        def text_block(text):
            return {'class': 'DepictionMarkdownView', 'markdown': text,
                    'useMargins': True, 'useSpacing': True, 'tintColor': '#BFA3F0'}
        def header(title):
            return {'class': 'DepictionHeaderView', 'title': title, 'alignment': 0,
                    'useBoldText': False, 'useMargins': True, 'useBottomMargin': True}
        def subheader(title):
            # Markdown headings also wrap when feature titles exceed a phone's width.
            return text_block('### ' + title)
        about_views = [
            {'class': 'DepictionSpacerView', 'spacing': 12},
            header(fields['Name']),
            text_block(f"**Version {fields['Version']}**\n\n{record['compatibility']}"),
            text_block(summary),
            {'class': 'DepictionSeparatorView'},
            header('Features')]
        for title, body in sections:
            about_views += [subheader(title), text_block(body)]
        if not sections:
            about_views += [text_block(fields['Description'].split('\n')[0])]
        if notes:
            about_views += [{'class': 'DepictionSeparatorView'}, subheader('Compatibility'),
                            text_block('\n\n'.join(notes))]
        about_views += [{'class': 'DepictionSpacerView', 'spacing': 16}]
        information_views = [{'class': 'DepictionSpacerView', 'spacing': 12}, header('Information')]
        for title, value in info:
            information_views += [subheader(title), text_block(value)]
        if notes:
            information_views += [{'class': 'DepictionSeparatorView'}, subheader('Compatibility'),
                                  text_block('\n\n'.join(notes))]
        information_views += [
            {'class': 'DepictionSeparatorView'},
            subheader('Links'),
            {'class': 'DepictionTableButtonView', 'title': 'Source code', 'action': source_url, 'tintColor': '#BFA3F0'},
            {'class': 'DepictionTableButtonView', 'title': 'Report an issue', 'action': source_url + '/issues', 'tintColor': '#BFA3F0'},
            {'class': 'DepictionTableButtonView', 'title': 'sonicedc repository', 'action': BASE + '/', 'tintColor': '#BFA3F0'},
            {'class': 'DepictionSpacerView', 'spacing': 16}]
        depiction_json = {'class': 'DepictionTabView', 'minVersion': '0.4',
            'headerImage': f'{BASE}/assets/sileo-header.png',
            'tintColor': '#BFA3F0', 'backgroundColor': '#17131F', 'tabs': [
                {'class': 'DepictionStackView', 'tabname': 'About', 'views': about_views},
                {'class': 'DepictionStackView', 'tabname': 'Information', 'views': information_views}]}
        (depiction / 'sileo.json').write_text(json.dumps(depiction_json, indent=2) + '\n')
        details = ''.join(f'<div><dt>{escape(k)}</dt><dd>{escape(v)}</dd></div>' for k,v in info)
        features = ''.join(f'<section class="feature"><h3>{escape(title)}</h3>{depiction_html(body)}</section>' for title, body in sections)
        note_html = f'<section class="compatibility"><h2>Compatibility</h2>{depiction_html(chr(10).join(notes))}</section>' if notes else ''
        content = f'''<a class="back" href="/">← All packages</a>
        <div class="project-heading"><img class="project-icon" src="/{record['icon']}" alt="" width="96" height="96"><div><p class="eyebrow">{escape(fields.get('Section', 'Package'))}</p><h1>{escape(fields['Name'])}</h1><div class="project-badges"><span>v{escape(fields['Version'])}</span><span>{escape(record['compatibility'])}</span></div></div></div>
        <p class="project-summary">{escape(summary)}</p>
        <div class="project-layout"><div class="project-content"><h2 class="features-heading">Features</h2><div class="features-grid">{features or '<p>' + escape(summary) + '</p>'}</div>{note_html}</div>
        <aside class="project-information"><h2>Information</h2><dl>{details}</dl><a class="button primary" href="sileo://source/{BASE}/">Add to Sileo <span aria-hidden="true">↗</span></a><div class="project-links"><a href="{source_url}">Source code <span aria-hidden="true">↗</span></a><a href="{source_url}/issues">Report an issue <span aria-hidden="true">↗</span></a></div><details class="package-checksum"><summary>Package checksum</summary><p>SHA-256</p><code>{fields['SHA256']}</code></details></aside></div>'''
        template = (ROOT / 'site' / 'detail.html').read_text()
        (depiction / 'index.html').write_text(template.replace('{{SOURCE}}', source_url).replace('{{TITLE}}', escape(fields['Name'])).replace('{{CONTENT}}', content))
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
    index = (OUT / 'index.html').read_text().replace('{{CARDS}}', cards).replace('{{COUNT}}', str(len(records))).replace('{{UPDATED}}', datetime.now(ZoneInfo('America/New_York')).strftime('%b %d, %Y'))
    (OUT / 'index.html').write_text(index)
    (OUT / 'detail.html').unlink()
    (OUT / '.nojekyll').touch()
    print(f'Built {len(records)} package(s) into {OUT}')

if __name__ == '__main__':
    main()
