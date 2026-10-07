"""Start the local application and open its browser when ready."""
import os
from pathlib import Path
import runpy
import threading
import time
from urllib.error import URLError
from urllib.request import urlopen
import webbrowser


def open_when_ready(url):
    for _ in range(60):
        try:
            with urlopen(url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(url)
                    return
        except (URLError, OSError):
            pass
        time.sleep(1)
    print(f'Abra manualmente no navegador: {url}', flush=True)


if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    os.chdir(root)
    port = int(os.environ.get('PARADAS_PORT', '5000'))
    threading.Thread(target=open_when_ready, args=(f'http://127.0.0.1:{port}/',), daemon=True).start()
    try:
        runpy.run_path(str(root / 'app.py'), run_name='__main__')
    except KeyboardInterrupt:
        print('\nAplicacao encerrada.')
