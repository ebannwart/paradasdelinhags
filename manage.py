"""Optional CLI import for the Excel files already in the project directory."""
import argparse
from pathlib import Path
from app import ROOT
from database import initialize
from importer import import_file

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description='Importar planilhas de paradas para o banco local.')
    parser.add_argument('files',nargs='*',help='Arquivos .xlsx; sem argumentos importa os .xlsx da pasta do projeto.')
    args=parser.parse_args()
    db=ROOT/'data'/'paradas.sqlite3';initialize(db)
    files=[Path(f) for f in args.files] if args.files else sorted(ROOT.glob('*.xlsx'))
    for path in files:
        print(f'Importando {path.name}...',flush=True)
        try:print(import_file(db,path),flush=True)
        except Exception as exc:print(f'ERRO {path.name}: {exc}',flush=True)
