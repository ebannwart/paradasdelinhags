import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from app import create_app


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids[attrs['id']] = attrs


class NavigationTests(unittest.TestCase):
    def test_requested_view_is_visible_before_javascript_or_data_load(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            client = create_app(root / 'test.sqlite3', root).test_client()
            for route, view in [('/kpi-manutencao', 'maintenance'),
                                ('/ofensores', 'dashboard'),
                                ('/ofensores?aba=lancamentos', 'records'),
                                ('/ofensores?aba=gerenciamento', 'offenders'), ('/ofensores?aba=acoes', 'actions')]:
                with self.subTest(route=route):
                    response = client.get(route)
                    self.assertEqual(response.status_code, 200)
                    elements = Elements(response.get_data(as_text=True)).ids
                    for candidate in ['maintenance', 'dashboard', 'records', 'offenders', 'actions']:
                        self.assertEqual('hidden' not in elements['view-' + candidate], candidate == view)
                    self.assertEqual('hidden' in elements['offender-tabs'], view == 'maintenance')
                    self.assertEqual('active' in elements['nav-offenders']['class'], view != 'maintenance')
