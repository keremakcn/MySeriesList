import json
from io import BytesIO
from urllib.error import HTTPError, URLError
import pytest
import tmdb_client
from tmdb_client import TMDBClient, TMDBError
from storage import Database
from version import APP_VERSION


def test_gateway_no_credentials_and_single_flight_cache(monkeypatch):
    monkeypatch.setenv('TMDB_ACCESS_TOKEN', 'private-legacy-secret')
    calls=[]
    def respond(req, timeout):
        calls.append(req)
        assert timeout == 12
        return BytesIO(json.dumps({'results': []}).encode())
    monkeypatch.setattr(tmdb_client, 'urlopen', respond)
    client=TMDBClient()
    client.get('search/tv',query='Dark')
    client.get('search/tv',query='Dark')
    assert len(calls)==1
    assert calls[0].full_url == 'https://api.myshelf.cloud/3/search/tv?query=Dark'
    assert calls[0].get_header('Authorization') is None
    assert calls[0].get_header('User-agent') == f'MySeriesList/{APP_VERSION}'
    assert 'private-legacy-secret' not in str(calls[0].headers)


@pytest.mark.parametrize('status',[401,403,404,429,503])
def test_gateway_errors_do_not_request_credentials(monkeypatch,status):
    def fail(*args,**kwargs): raise HTTPError('https://example',status,'error',{'Retry-After':'30'},None)
    monkeypatch.setattr(tmdb_client,'urlopen',fail)
    with pytest.raises(TMDBError) as exc: TMDBClient().get('tv/1399')
    assert 'token' not in str(exc.value).lower()
    if status==429: assert exc.value.retry_after==30


@pytest.mark.parametrize('url',['http://example.com','https://user:key@example.com','https://example.com/other'])
def test_unsafe_gateway_rejected(url):
    with pytest.raises(ValueError): TMDBClient(base_url=url)


def test_migration_removes_credentials_preserves_entire_journal(tmp_path):
    path=tmp_path/'series.db'
    db=Database(path)
    sid=db.add({'id':100,'name':'Private show','seasons':[{'season_number':1,'name':'First'}]})
    db.save_season(sid,1,{'episodes':[{'episode_number':1,'name':'Pilot','air_date':'2020-01-01'}]})
    db.execute("UPDATE series SET note='Private note',rating=9,favorite=1 WHERE id=?",(sid,))
    db.execute("UPDATE episodes SET watched_at='2026-10-01' WHERE series_id=?",(sid,))
    before={table:db.query('SELECT * FROM '+table) for table in ('series','seasons','episodes')}
    db.execute("INSERT INTO settings VALUES('tmdb_token','obsolete-secret')")
    db.execute("INSERT INTO settings VALUES('theme','dark')")
    Database(path)
    assert all(db.query('SELECT * FROM '+table)==rows for table,rows in before.items())
    assert not db.query("SELECT * FROM settings WHERE key='tmdb_token'")
    assert db.query("SELECT value FROM settings WHERE key='theme'")[0]['value']=='dark'
    assert b'obsolete-secret' not in path.read_bytes()
