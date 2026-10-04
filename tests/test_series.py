from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
from app import create_app
from tmdb_client import TMDBError

@pytest.fixture
def setup(tmp_path):
    app = create_app({'TESTING': True, 'DATABASE': str(tmp_path / 'series.db')})
    def get(path, **kwargs):
        if path == 'search/tv':
            return {'results': [{'id': 100, 'name': 'A long series title', 'poster_path': None}], 'total_pages': 1}
        if '/season/' in path:
            return {'episodes': [{'episode_number': 1, 'name': 'Pilot', 'air_date': '2020-01-01'},
                                 {'episode_number': 2, 'name': 'Future', 'air_date': '2999-01-01'}]}
        return {'id': 100, 'name': 'A series', 'seasons': [{'season_number': 1, 'name': 'Season 1'}]}
    app.extensions['tmdb'].get = get
    client = app.test_client()
    client.get('/')
    with client.session_transaction() as s:
        csrf = s['csrf']
    def post(path, **data):
        return client.post(path, data={'csrf': csrf, **data}, follow_redirects=True)
    return app, client, post

def test_journal_progress_restore_and_duplicate(setup):
    app, client, post = setup
    assert post('/add/100').status_code == 200
    post('/series/1/season/1')
    post('/series/1/episode/1/1', watched='1')
    post('/series/1/save', status='On hold', rating='9', note='<script>private</script>', favorite='1')
    db = app.extensions['db']
    before = db.query('SELECT * FROM series')[0]
    post('/series/1/delete')
    assert client.get('/series/1').status_code == 404
    post('/undo')
    assert db.query('SELECT * FROM series')[0] == before
    assert db.query('SELECT watched_at FROM episodes WHERE number=1')[0]['watched_at']
    post('/add/100')
    assert len(db.query('SELECT * FROM series')) == 1
    assert db.query('SELECT * FROM series')[0] == before
    assert b'&lt;script&gt;' in client.get('/series/1').data

def test_security_and_future_episode(setup):
    app, client, post = setup
    assert client.post('/add/100').status_code == 400
    post('/add/100')
    post('/series/1/season/1')
    assert post('/series/1/episode/1/2', watched='1').status_code == 400
    assert post('/series/1/save', status='Wrong', rating='99').status_code == 400
    assert post('/series/1/season/98').status_code == 404
    assert client.get('/', headers={'Host': 'evil.example'}).status_code == 400

def test_next_and_refresh_preserve_progress(setup):
    app, client, post = setup
    post('/add/100')
    assert b'Watched S01 E01' in post('/series/1/next', progress_version='0').data
    assert b'caught up' in post('/series/1/next', progress_version='1').data
    post('/series/1/season/1')
    assert app.extensions['db'].query('SELECT watched_at FROM episodes WHERE number=1')[0]['watched_at']

def test_concurrent_duplicate_add(setup):
    app, _, _ = setup
    db = app.extensions['db']
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(lambda _: db.add({'id': 100, 'name': 'Same series'}), range(8))) == [1] * 8

def test_search_settings_and_error(setup):
    app, client, post = setup
    assert b'A long series title' in client.get('/search?q=test').data
    assert client.get('/search?q=test&page=invalid').status_code == 200
    assert post('/settings', token='private-test-token').status_code == 405
    assert b'private-test-token' not in client.get('/settings').data
    def fail(*args, **kwargs):
        raise TMDBError('Offline', 503)
    app.extensions['tmdb'].get = fail
    assert b'Offline' in client.get('/search?q=test').data
    assert client.get('/').status_code == 200


def test_settings_no_longer_collects_credentials(setup):
    app, client, post = setup
    assert b'Ready to explore' in client.get('/settings').data
    assert b'name="token"' not in client.get('/settings').data
    assert post('/settings', token='secret').status_code == 405
    assert not app.extensions['db'].query("SELECT * FROM settings WHERE key='tmdb_token'")


def test_catalog_does_not_add_and_ajax_add_is_duplicate_safe(setup):
    app, client, post = setup
    assert client.get('/catalog/100').status_code == 200
    assert b'Pilot' in client.get('/catalog/100?season=1').data
    assert client.get('/catalog/100?season=9').status_code == 404
    assert not app.extensions['db'].query('SELECT * FROM series')
    with client.session_transaction() as s:
        csrf = s['csrf']
    for _ in range(2):
        response = client.post('/add/100', data={'csrf': csrf}, headers={'Accept': 'application/json'})
        assert response.json['url'] == '/series/1'
    assert len(app.extensions['db'].query('SELECT * FROM series')) == 1


def test_replayed_next_does_not_skip_an_episode(setup):
    app, client, post = setup
    post('/add/100')
    db = app.extensions['db']
    db.save_season(1, 1, {'episodes': [{'episode_number': i, 'name': str(i), 'air_date': '2020-01-01'} for i in (1,2)]})
    post('/series/1/next', progress_version='0')
    response = post('/series/1/next', progress_version='0')
    assert b'No additional episode was marked' in response.data
    assert len(db.query('SELECT * FROM episodes WHERE watched_at IS NOT NULL')) == 1
    before = db.query('SELECT watched_at FROM episodes WHERE number=1')[0]['watched_at']
    post('/series/1/episode/1/1', watched='1')
    assert db.query('SELECT watched_at FROM episodes WHERE number=1')[0]['watched_at'] == before


def test_refresh_preserves_journal_and_adds_new_season(setup):
    app, client, post = setup
    post('/add/100')
    post('/series/1/save', status='On hold', rating='8', favorite='1', note='Keep my journal')
    app.extensions['tmdb'].get = lambda *a, **kw: {'id':100, 'name':'Updated title', 'seasons':[{'season_number':2,'name':'Season 2'}]}
    post('/series/1/refresh')
    item = app.extensions['db'].query('SELECT * FROM series')[0]
    assert (item['title'],item['note'],item['status'],item['rating'],item['favorite']) == ('Updated title','Keep my journal','On hold',8,1)
    assert b'Season 2' in client.get('/series/1').data


def test_v1_migration_preserves_existing_database(tmp_path):
    import sqlite3
    from storage import Database
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as c:
        c.executescript("""CREATE TABLE series(id INTEGER PRIMARY KEY,tmdb_id INTEGER UNIQUE,title TEXT,
            overview TEXT,poster TEXT,year TEXT,status TEXT,note TEXT,rating INTEGER,favorite INTEGER,
            created_at TEXT,deleted_at TEXT);
            INSERT INTO series VALUES(1,10,'Old show','','','2001','Watching','Keep this',9,1,'original',NULL);
            PRAGMA user_version=1;""")
    db = Database(path)
    item = db.query('SELECT * FROM series')[0]
    assert item['note'] == 'Keep this' and item['created_at'] == 'original'
    assert item['progress_version'] == 0
    assert Path(str(path)+'.before-v2.bak').exists()


def test_search_deduplicates_provider_results(setup):
    app, client, _ = setup
    app.extensions['tmdb'].get = lambda *a, **kw: {'results': [{'id': 1, 'name': 'Unique title'}] * 2}
    response = client.get('/search?q=unique')
    assert response.data.count(b'aria-label="Explore Unique title"') == 1


def test_next_preview_does_not_skip_unloaded_earlier_season(setup):
    app, client, post = setup
    post('/add/100')
    db = app.extensions['db']
    db.execute("INSERT INTO seasons VALUES(1,2,'Season 2',0)")
    db.save_season(1, 2, {'episodes': [{'episode_number': 1, 'name': 'Later chapter', 'air_date': '2020-01-01'}]})
    assert b'<h2>Continue at your pace.</h2>' in client.get('/series/1').data
    post('/series/1/next', progress_version='0')
    assert db.query('SELECT season FROM episodes WHERE watched_at IS NOT NULL') == [{'season': 1}]


def test_season_json_load_is_lazy_cached_and_refreshable(setup):
    app, client, post = setup
    post('/add/100')
    original = app.extensions['tmdb'].get
    calls = []
    def get(path, **kwargs):
        calls.append(path)
        return original(path, **kwargs)
    app.extensions['tmdb'].get = get
    with client.session_transaction() as s:
        csrf = s['csrf']
    for _ in range(2):
        response = client.post('/series/1/season/1', data={'csrf':csrf}, headers={'Accept':'application/json'})
        assert response.status_code == 200 and 'Pilot' in response.json['html']
        assert response.json['summary'] == '0 / 2 watched'
    assert calls == ['tv/100/season/1']
    client.post('/series/1/season/1', data={'csrf':csrf,'refresh':'1'}, headers={'Accept':'application/json'})
    assert len(calls) == 2
    assert client.post('/series/1/season/9', data={'csrf':csrf}, headers={'Accept':'application/json'}).status_code == 404


def completion_provider(path, **kwargs):
    if '/season/' in path:
        return {'episodes':[{'episode_number':1,'name':'Aired','air_date':'2020-01-01'},
                            {'episode_number':2,'name':'Future','air_date':'2999-01-01'},
                            {'episode_number':3,'name':'Unknown','air_date':None}]}
    return {'id':100,'name':'Completed show','seasons':[{'season_number':i,'name':str(i)} for i in (0,1,2)]}


def test_completed_loads_every_season_preserves_timestamps_and_skips_future(setup):
    app, client, post = setup
    app.extensions['tmdb'].get = completion_provider
    post('/add/100')
    post('/series/1/season/1')
    post('/series/1/episode/1/1', watched='1')
    db = app.extensions['db']
    old = db.query('SELECT * FROM episodes WHERE season=1 AND number=1')[0]['watched_at']
    response = post('/series/1/save', status='Completed',rating='9',note='Private note',favorite='1')
    assert response.status_code == 200
    assert len(db.query('SELECT * FROM episodes WHERE watched_at IS NOT NULL')) == 3
    assert not db.query('SELECT * FROM episodes WHERE number>1 AND watched_at IS NOT NULL')
    assert db.query('SELECT watched_at FROM episodes WHERE season=1 AND number=1')[0]['watched_at'] == old
    assert all(s['loaded'] for s in db.query('SELECT * FROM seasons'))
    item = db.query('SELECT * FROM series')[0]
    assert (item['status'],item['rating'],item['note'],item['favorite']) == ('Completed',9,'Private note',1)
    before = db.query('SELECT * FROM episodes')
    post('/series/1/save',status='Completed',rating='9',note='Private note',favorite='1')
    assert db.query('SELECT * FROM episodes') == before
    post('/series/1/episode/1/1',watched='0')
    assert db.query('SELECT status FROM series')[0]['status'] == 'Watching'


def test_failed_completed_is_atomic_and_keeps_unsaved_form_values(setup):
    app, client, post = setup
    app.extensions['tmdb'].get = completion_provider
    post('/add/100')
    post('/series/1/save',status='Watching',rating='8',note='Old note')
    db = app.extensions['db']
    before = db.query('SELECT * FROM series')
    def failure(path, **kwargs):
        if path.endswith('/season/2'):
            raise TMDBError('Temporary failure')
        return completion_provider(path, **kwargs)
    app.extensions['tmdb'].get = failure
    response = post('/series/1/save',status='Completed',note='Unsaved new note',rating='10')
    assert response.status_code == 502 and b'Unsaved new note' in response.data
    assert db.query('SELECT * FROM series') == before
    assert not db.query('SELECT * FROM episodes')
    assert not db.query('SELECT * FROM seasons WHERE loaded=1')


def test_completed_rejects_progress_change_during_network_reads(setup):
    app, client, post = setup
    app.extensions['tmdb'].get = completion_provider
    post('/add/100')
    db = app.extensions['db']
    def changed(path, **kwargs):
        if '/season/' not in path:
            db.execute('UPDATE series SET progress_version=progress_version+1 WHERE id=1')
        return completion_provider(path, **kwargs)
    app.extensions['tmdb'].get = changed
    response = post('/series/1/save',status='Completed',note='new')
    assert response.status_code == 409
    assert db.query('SELECT status FROM series')[0]['status'] == 'Want to watch'
    assert not db.query('SELECT * FROM episodes')


def test_aggregate_credits_links_and_person_filmography(setup):
    app, client, post = setup
    def get(path, **kwargs):
        if path.startswith('person/'):
            show = {'id':100,'name':'Shared series','first_air_date':'2020-01-01'}
            return {'id':2,'name':'The Director','known_for_department':'Directing',
                    'tv_credits':{'cast':[dict(show,character='Guest')],
                                  'crew':[dict(show,job='Director'),dict(show,job='Director'),
                                          {'id':101,'name':'Produced only','job':'Producer'}]}}
        assert kwargs['append_to_response'] == 'aggregate_credits'
        return {'id':100,'name':'Shared series','seasons':[],
                'created_by':[{'id':3,'name':'Creator'}],
                'aggregate_credits':{'cast':[{'id':1,'name':'Actor','roles':[{'character':'Hero'}]}],
                    'crew':[{'id':2,'name':'The Director','jobs':[{'job':'Director'}]},
                            {'id':3,'name':'Creator','jobs':[{'job':'Producer'}]}]}}
    app.extensions['tmdb'].get = get
    post('/add/100')
    for url in ('/','/series/1','/catalog/100'):
        html = client.get(url).data
        assert b'/people/1?role=acting' in html
        assert b'/people/2?role=directing' in html
        assert b'/people/3?role=directing' not in html
    response = client.get('/people/2?role=directing')
    assert response.status_code == 200
    assert response.data.count(b'aria-label="Explore Shared series"') == 1
    assert b'Produced only' not in response.data
    assert b'In your library' in response.data
    assert client.get('/people/2?page=invalid').status_code == 200
    assert client.get('/people/2?role=acting&page=999').status_code == 200


def test_incomplete_completion_payload_does_not_save(setup):
    app, client, post = setup
    post('/add/100')
    app.extensions['tmdb'].get = lambda *a, **kw: {'id':100,'name':'Incomplete'}
    assert post('/series/1/save',status='Completed').status_code == 502
    assert app.extensions['db'].query('SELECT status FROM series')[0]['status'] == 'Want to watch'


def test_completed_journal_can_be_edited_offline(setup):
    app, client, post = setup
    app.extensions['tmdb'].get = completion_provider
    post('/add/100')
    post('/series/1/save',status='Completed',note='Before')
    def offline(*args, **kwargs):
        raise TMDBError('Offline')
    app.extensions['tmdb'].get = offline
    response = post('/series/1/save',status='Completed',note='Offline note',rating='10')
    assert response.status_code == 200
    assert app.extensions['db'].query('SELECT note FROM series')[0]['note'] == 'Offline note'
