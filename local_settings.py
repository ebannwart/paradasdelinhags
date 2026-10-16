"""Per-user settings and restart-only selection of the operational database."""
from contextlib import closing
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from flask import jsonify, request
from database import connect


def prepare(directory):
    directory=Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    local=directory/'preferences.sqlite3'
    with connect(local) as db:
        db.executescript("CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE IF NOT EXISTS sap_source_choices(kind TEXT PRIMARY KEY,path TEXT NOT NULL);")
    pointer=directory/'database.json'
    saved=json.loads(pointer.read_text(encoding='utf-8')) if pointer.exists() else {}
    return local,pointer,saved.get('path','')


def _validate_existing(path):
    if not path.is_file():
        raise ValueError('Banco não encontrado. O arquivo existente não será criado automaticamente.')
    with closing(sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,timeout=5)) as db:
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'records','offenders','files','settings','failure_snapshots','sap_groups'} <= tables:
            raise ValueError('O arquivo não é um banco desta aplicação.')
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise ValueError('O banco não passou na verificação de integridade.')
        db.execute('BEGIN IMMEDIATE')
        db.rollback()
    # Journals require directory write access, not just permission on the file.
    with tempfile.TemporaryFile(dir=path.parent):
        pass


def validate_existing(path):
    try:
        _validate_existing(path)
    except (sqlite3.Error, OSError) as exc:
        raise ValueError('Não foi possível acessar o banco. Verifique se é um SQLite válido, se a rede está disponível e se há permissão de gravação. Feche outras instâncias durante a configuração. Detalhe: ' + str(exc)) from exc


def register(app):
    pointer=Path(app.config['DATABASE_POINTER'])

    @app.get('/api/configuration/database')
    def database_settings():
        selected=json.loads(pointer.read_text(encoding='utf-8')).get('path','') if pointer.exists() else ''
        active=app.config['DB_PATH']
        return jsonify(active=active,selected=selected or active,pending=bool(selected and selected!=active),
                       local_directory=str(pointer.parent),pointer=str(pointer))

    @app.post('/api/configuration/database')
    def database_save():
        body=request.get_json() or {}
        value=body.get('path','')
        if not isinstance(value,str) or not value.strip() or len(value)>4096:
            raise ValueError('Informe o caminho completo do arquivo SQLite.')
        target=Path(value.strip().strip('"')).expanduser()
        if not target.is_absolute() or target.suffix.lower() not in ('.sqlite3','.sqlite','.db'):
            raise ValueError('Use um caminho absoluto com extensão .sqlite3, .sqlite ou .db.')
        target=target.resolve()
        if not target.parent.is_dir():
            raise ValueError('A pasta de destino não existe ou está indisponível.')
        mode=body.get('mode','existing')
        if mode not in ('existing','copy'):
            raise ValueError('Selecione banco existente ou cópia inicial.')
        if mode=='copy':
            # Reserve exclusively: never overwrite an existing database.
            try:
                with target.open('xb'):
                    pass
            except FileExistsError:
                raise ValueError('O destino já existe. Use conectar a banco existente; nenhum arquivo foi sobrescrito.')
            try:
                with connect(app.config['DB_PATH']) as source:
                    destination=sqlite3.connect(target)
                    try:
                        source.backup(destination)
                        destination.execute('PRAGMA journal_mode=DELETE')
                        destination.execute("DELETE FROM settings WHERE key='application_sources'")
                        destination.execute('DELETE FROM sap_source_choices')
                        destination.commit()
                    finally:
                        destination.close()
                validate_existing(target)
            except Exception:
                target.unlink(missing_ok=True)
                raise
        else:
            validate_existing(target)
        # Atomic local pointer update. Active requests keep the old database until restart.
        fd,name=tempfile.mkstemp(dir=pointer.parent,suffix='.tmp')
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as f:
                json.dump({'path':str(target)},f,ensure_ascii=False,indent=2)
                f.flush();os.fsync(f.fileno())
            os.replace(name,pointer)
        finally:
            Path(name).unlink(missing_ok=True)
        return jsonify(ok=True,pending=str(target)!=app.config['DB_PATH'],path=str(target))
