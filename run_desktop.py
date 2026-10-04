import threading
from pathlib import Path
import webview
from waitress import create_server
from app import create_app
from version import APP_VERSION

if __name__ == '__main__':
    # target=_blank links are handled by the operating system's default browser.
    webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True
    webview.settings['ALLOW_FILE_URLS'] = False
    server = create_server(create_app(), host='127.0.0.1', port=0)
    threading.Thread(target=server.run, daemon=True).start()
    try:
        webview.create_window(f'MySeriesList · {APP_VERSION}', f'http://127.0.0.1:{server.effective_port}',
                              width=1280, height=860, min_size=(760, 600), background_color='#111318')
        webview.start(icon=str(Path(__file__).resolve().parent / 'static' / 'branding' / 'series-watchlist.ico'))
    finally:
        server.close()
