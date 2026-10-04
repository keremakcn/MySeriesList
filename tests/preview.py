"""Isolated deterministic browser fixture. Never opens a personal database."""
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app
from tmdb_client import TMDBError
from waitress import serve

folder = tempfile.TemporaryDirectory()
app = create_app({'DATABASE': str(Path(folder.name) / 'test.db')})
db = app.extensions['db']


def show(tid):
    title = {1: 'Severance', 2: 'The Bear', 3: 'A very long series title that spans multiple lines',
             4: 'Dark', 10: 'The Last Horizon', 11: 'Somewhere New'}.get(tid, 'Unavailable series')
    return {'id': tid, 'name': title, 'first_air_date': '2022-01-01', 'poster_path': None,
            'overview': 'Every episode brings a new perspective. A story of unexpected connections, quiet discoveries and the people who make a place feel like home.',
            'genres': [{'name': 'Drama'}, {'name': 'Mystery'}], 'status': 'Returning Series',
            'vote_average': 8.4, 'number_of_seasons': 2, 'number_of_episodes': 4,
            'created_by': [{'id': 21, 'name': 'Alex Morgan'}], 'tagline': 'There is always another chapter.',
            'credits_complete': True,
            'credits': {'cast': [{'id': 20+i, 'name': n, 'character': c} for i, (n, c) in enumerate([('Robin Taylor', 'Alex'), ('Jamie Ross', 'Charlie'), ('Casey Lane', 'Sam'), ('Morgan Reed', 'Lee')])],
                        'crew': [{'id':21,'name':'Alex Morgan','job':'Director'}]},
            'seasons': [{'season_number': n, 'name': f'Season {n}', 'episode_count': 2} for n in (1, 2)]}


def season(number):
    return {'episodes': [{'episode_number': 1, 'name': 'A new beginning', 'air_date': '2020-01-01', 'overview': 'An unexpected arrival changes everything.'},
                         {'episode_number': 2, 'name': 'A very long episode name to check narrow screens', 'air_date': '2099-01-01' if number == 2 else '2020-01-08'}]}


for tid in range(1, 5):
    sid = db.add(show(tid))
    db.save_season(sid, 1, season(1))


def get(path, **params):
    if path.startswith('person/'):
        return {'id': int(path.split('/')[1]), 'name':'Alex Morgan', 'known_for_department':'Directing',
                'biography':'Stories are a way of seeing the world.',
                'tv_credits': {'cast':[dict(show(10), character='A guest')],
                               'crew':[dict(show(10), job='Director'),dict(show(11),job='Director')]}}
    if path == 'search/tv':
        if params['query'] == 'offline':
            raise TMDBError('Could not reach TMDB. Check your connection and try again.')
        return {'results': [] if params['query'] == 'nothing' else [show(10), show(1), show(11), show(99), show(10)], 'total_pages': 1}
    tid = int(path.split('/')[1])
    if tid == 99:
        raise TMDBError('TMDB is temporarily unavailable. Please try again.')
    return season(int(path.split('/')[-1])) if '/season/' in path else show(tid)



app.extensions['tmdb'].get = get
if __name__ == '__main__':
    serve(app, host='127.0.0.1', port=5063)
