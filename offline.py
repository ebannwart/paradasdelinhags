"""Run with the installed Python and dependencies shipped beside the app."""
import io
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent


def check():
    if sys.version_info < (3, 11):
        raise RuntimeError('Este pacote requer Python 3.11 ou superior.')
    libs = ROOT / 'libs'
    if not libs.is_dir():
        raise RuntimeError('Pasta libs ausente. Extraia o ZIP offline completo, nao apenas o codigo-fonte.')
    sys.path.insert(0, str(libs))
    from importlib.metadata import version
    import flask
    import openpyxl
    import waitress
    import plotly
    import markupsafe
    from plotly.offline import get_plotlyjs
    for module in (flask, openpyxl, waitress, plotly, markupsafe):
        if not Path(module.__file__).resolve().is_relative_to(libs):
            raise RuntimeError(f'Biblioteca fora do pacote: {module.__name__}')
        print(f'{module.__name__}: {version(module.__name__)}', flush=True)
    stream = io.BytesIO()
    book = openpyxl.Workbook()
    book.active['A1'] = 'OK'
    book.save(stream)
    book.close()
    stream.seek(0)
    restored = openpyxl.load_workbook(stream)
    assert restored.active['A1'].value == 'OK'
    restored.close()
    assert 'plotly' in get_plotlyjs().lower()
    print('OK: bibliotecas locais, leitura Excel e graficos disponiveis.', flush=True)


if __name__ == '__main__':
    try:
        print(f'Python: {sys.version}\nExecutavel: {sys.executable}', flush=True)
        check()
        if '--diagnostico' not in sys.argv:
            os.chdir(ROOT)
            runpy.run_path(str(ROOT / 'iniciar.py'), run_name='__main__')
    except Exception as exc:
        print(f'ERRO: {exc}\nConsulte INSTALACAO-OFFLINE.md.', file=sys.stderr)
        sys.exit(1)
