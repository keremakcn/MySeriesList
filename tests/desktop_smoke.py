"""Windows WebView2 smoke check, with an isolated DB and intercepted browser handoff."""
import sys
import tempfile
import threading
import webbrowser
from pathlib import Path

import webview
from waitress import create_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app


def main():
    with tempfile.TemporaryDirectory() as directory:
        app = create_app({'DATABASE': str(Path(directory) / 'smoke.db')})
        server = create_server(app, host='127.0.0.1', port=0)
        threading.Thread(target=server.run, daemon=True).start()
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
        webview.settings['ALLOW_FILE_URLS'] = False
        ready = threading.Event()
        opened = threading.Event()
        targets, failures = [], []
        original = webbrowser.open

        def intercept(url, *args, **kwargs):
            targets.append(url)
            opened.set()
            return True

        webbrowser.open = intercept
        window = webview.create_window('Isolated MySeriesList QA',
                                      f'http://127.0.0.1:{server.effective_port}/settings', hidden=True)
        window.events.loaded += lambda: ready.set()

        def exercise():
            try:
                assert ready.wait(20), 'Settings did not load in WebView2'
                assert 'Settings' in window.evaluate_js('document.title')
                window.evaluate_js("document.querySelector('a.external-link').click()")
                assert opened.wait(10), 'External link was not handed to the OS browser opener'
                assert targets == ['https://www.themoviedb.org']
                assert '/settings' in window.get_current_url(), 'App navigated away from Settings'
            except Exception as exc:
                failures.append(str(exc))
            finally:
                window.destroy()

        try:
            webview.start(exercise, gui='edgechromium',
                          icon=str(Path(__file__).resolve().parents[1] / 'static' / 'branding' / 'series-watchlist.ico'))
        finally:
            server.close()
            webbrowser.open = original
        assert not failures, failures
        print('WebView2 Settings render and default-browser handoff passed (OS opener intercepted).')


if __name__ == '__main__':
    main()
