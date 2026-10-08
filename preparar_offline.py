"""Bundle installed, audited dependencies without executables or private data."""
from datetime import datetime
from importlib.metadata import distribution
from pathlib import Path
import hashlib
import shutil
import zipfile

ROOT = Path(__file__).resolve().parent
PACKAGES = ['Flask', 'Werkzeug', 'Jinja2', 'MarkupSafe', 'openpyxl', 'et_xmlfile',
            'waitress', 'plotly', 'narwhals', 'packaging', 'click', 'itsdangerous', 'blinker']


def build():
    destination = ROOT / 'dist' / datetime.now().strftime('offline-%Y%m%d-%H%M%S')
    app = destination / 'ParadasDeLinha'
    libs = app / 'libs'
    libs.mkdir(parents=True, exist_ok=False)
    manifest = ['Dependencias locais; MarkupSafe sem aceleracao nativa opcional.']
    for name in PACKAGES:
        dist = distribution(name)
        manifest.append(f'{dist.metadata["Name"]}=={dist.version}')
        for item in dist.files or []:
            rel = Path(str(item))
            if '..' in rel.parts or '__pycache__' in rel.parts or rel.suffix in ('.pyc', '.pyo'):
                continue
            if rel.suffix.lower() in ('.exe', '.dll', '.pyd', '.so'):
                if name == 'MarkupSafe' and rel.name.startswith('_speedups'):
                    continue
                raise RuntimeError(f'Binario inesperado: {name}/{rel}')
            source = Path(dist.locate_file(item))
            if source.is_file():
                target = libs / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    for pattern in ('*.py', '*.md', '*.bat', '*.xlsx', 'requirements.txt'):
        for source in ROOT.glob(pattern):
            shutil.copy2(source, app / source.name)
    for folder in ('static', 'templates', 'tests'):
        shutil.copytree(ROOT / folder, app / folder, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (app / 'DEPENDENCIAS-OFFLINE.txt').write_text('\n'.join(manifest)+'\n', encoding='utf-8')
    archive = destination / 'ParadasDeLinha-offline.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in sorted(app.rglob('*')):
            if path.is_file():
                z.write(path, path.relative_to(destination))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(archive)


if __name__ == '__main__':
    build()
