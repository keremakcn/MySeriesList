"""MySeriesList 1.0.0: private TV journal with independent discovery."""
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, abort, flash, jsonify
from storage import Database, STATUSES, now
from version import APP_VERSION
from tmdb_client import TMDBClient, TMDBError, image_url
from werkzeug.exceptions import SecurityError

def create_app(config=None):
    app = Flask(__name__)
    folder = Path(os.environ.get('SERIES_WATCHLIST_DATA_DIR') or (Path(os.environ.get('APPDATA', str(Path.home()))) / 'SeriesWatchlist'))
    app.config.update(SECRET_KEY=secrets.token_hex(32), DATABASE=str(folder / 'series.db'),
                      MAX_CONTENT_LENGTH=65536, SESSION_COOKIE_NAME='series_watchlist',
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Strict',
                      TRUSTED_HOSTS=['127.0.0.1', 'localhost', '[::1]'])
    app.config.update(config or {})
    db = Database(app.config['DATABASE'])
    tmdb = TMDBClient()
    app.extensions.update(db=db, tmdb=tmdb)

    def wants_json():
        return request.accept_mimetypes.best == 'application/json'

    @app.before_request
    def protect():
        session.setdefault('csrf', secrets.token_hex(32))
        if request.method == 'POST' and not secrets.compare_digest(
                request.form.get('csrf', '').encode(), session['csrf'].encode()):
            abort(400, 'Your session changed. Reload the page and try again.')

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' https://image.tmdb.org; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def context():
        return dict(statuses=STATUSES, image_url=image_url, today=date.today().isoformat(), app_version=APP_VERSION)

    def series(sid):
        rows = db.query('SELECT * FROM series WHERE id=? AND deleted_at IS NULL', (sid,))
        if not rows:
            abort(404)
        item = rows[0]
        item['meta'] = json.loads(item['metadata'])
        return item

    def member(tid):
        rows = db.query('SELECT id FROM series WHERE tmdb_id=? AND deleted_at IS NULL', (tid,))
        return rows[0]['id'] if rows else None

    def fetch_catalog(tid):
        data = dict(tmdb.get(f'tv/{tid}', append_to_response='aggregate_credits'))
        credits = data.get('aggregate_credits') or data.get('credits') or {}
        data['credits'] = {
            'cast': [dict(p, character=', '.join(r['character'] for r in p.get('roles', [])[:2] if r.get('character')) or p.get('character', ''))
                     for p in credits.get('cast', [])],
            'crew': [dict(p, job='Director') for p in credits.get('crew', [])
                     if p.get('job') == 'Director' or any(j.get('job') == 'Director' for j in p.get('jobs', []))]}
        data['credits_complete'] = True
        return data

    def detail_data(sid):
        item = series(sid)
        seasons = db.query('SELECT * FROM seasons WHERE series_id=? ORDER BY number', (sid,))
        episodes = db.query('SELECT * FROM episodes WHERE series_id=? ORDER BY season,number', (sid,))
        available = [ep for ep in episodes if ep['season'] > 0 and not ep['watched_at']
                     and ep['air_date'] and ep['air_date'] <= date.today().isoformat()]
        next_ep = available[0] if available else None
        if next_ep and any(0 < s['number'] < next_ep['season'] and not s['loaded'] for s in seasons):
            next_ep = None
        return dict(item=item, seasons=seasons, episodes=episodes, next_ep=next_ep,
                    progress=dict(watched=sum(bool(ep['watched_at']) for ep in episodes), loaded=len(episodes)))

    @app.errorhandler(TMDBError)
    def tmdb_error(error):
        if wants_json():
            return jsonify(error=str(error)), error.status
        return render_template('error.html', message=str(error)), error.status

    @app.errorhandler(400)
    @app.errorhandler(404)
    def request_error(error):
        if isinstance(error, SecurityError):
            return 'Invalid host.', 400
        if wants_json():
            return jsonify(error=error.description), error.code
        return render_template('error.html', message=error.description), error.code

    @app.errorhandler(500)
    def unexpected(error):
        if wants_json():
            return jsonify(error='Something went wrong. Please try again.'), 500
        return render_template('error.html', message='Something went wrong. Please try again.'), 500

    @app.get('/')
    def library():
        status = request.args.get('status', '')
        q = request.args.get('q', '')[:200]
        favorite = request.args.get('favorite') == '1'
        sort = request.args.get('sort', 'recent')
        order = {'recent': 's.favorite DESC,s.id DESC', 'title': 's.title COLLATE NOCASE',
                 'rating': 's.rating IS NULL,s.rating DESC,s.id DESC'}.get(sort, 's.favorite DESC,s.id DESC')
        items = db.query('''SELECT s.*,
            (SELECT COUNT(*) FROM episodes e WHERE e.series_id=s.id AND e.watched_at IS NOT NULL) watched
            FROM series s WHERE deleted_at IS NULL AND title LIKE ?
            AND (?='' OR status=?) AND (?=0 OR favorite=1) ORDER BY ''' + order,
            ('%' + q + '%', status, status, int(favorite)))
        for item in items:
            item['meta'] = json.loads(item['metadata'])
        stats = db.query("""SELECT COUNT(*) total, COALESCE(SUM(status='Watching'),0) watching,
            COALESCE(SUM(status='Completed'),0) completed FROM series WHERE deleted_at IS NULL""")[0]
        return render_template('library.html', items=items, q=q, selected=status,
                               favorite=favorite, sort=sort, stats=stats)

    @app.get('/search')
    def search():
        q = request.args.get('q', '').strip()[:200]
        try:
            page = max(1, min(500, int(request.args.get('page', 1))))
        except ValueError:
            page = 1
        error = None
        try:
            data = tmdb.get('search/tv', query=q, page=page, include_adult='false') if q else {}
        except TMDBError as exc:
            data, error = {}, str(exc)
        members = {r['tmdb_id']: r['id'] for r in db.query('SELECT id,tmdb_id FROM series WHERE deleted_at IS NULL')}
        items = list({item['id']: item for item in data.get('results', []) if item.get('id')}.values())
        return render_template('search.html', q=q, items=items, members=members,
                               page=page, pages=min(500, data.get('total_pages', 0)), error=error)

    @app.get('/catalog/<int:tid>')
    def catalog(tid):
        data = fetch_catalog(tid)
        item = dict(title=data.get('name') or 'Untitled series', poster=data.get('poster_path'),
                    year=(data.get('first_air_date') or '')[:4], overview=data.get('overview'),
                    meta=data, tmdb_id=tid)
        selected = request.args.get('season', type=int)
        episodes = []
        if selected is not None:
            if selected not in [s['season_number'] for s in data.get('seasons', [])]:
                abort(404)
            episodes = tmdb.get(f'tv/{tid}/season/{selected}').get('episodes', [])
        return render_template('catalog.html', item=item, sid=member(tid), seasons=data.get('seasons', []),
                               episodes=episodes, selected=selected)

    @app.post('/add/<int:tid>')
    def add(tid):
        existing = member(tid)
        sid = existing or db.add(fetch_catalog(tid))
        if wants_json():
            return jsonify(url=url_for('detail', sid=sid), title='Already in your library' if existing else 'Added to your library')
        flash('Series added to your library.')
        return redirect(url_for('detail', sid=sid))

    @app.get('/series/<int:sid>')
    def detail(sid):
        return render_template('detail.html', **detail_data(sid))

    @app.post('/series/<int:sid>/refresh')
    def refresh(sid):
        item = series(sid)
        path = f"tv/{item['tmdb_id']}"
        tmdb.invalidate(path)
        db.refresh(sid, fetch_catalog(item['tmdb_id']))
        if wants_json():
            return jsonify(html=render_template('_people.html', item=series(sid)))
        flash('Series information and seasons refreshed. Your journal and progress are unchanged.', 'success')
        return redirect(url_for('detail', sid=sid))

    @app.post('/series/<int:sid>/season/<int:number>')
    def load_season(sid, number):
        item = series(sid)
        rows = db.query('SELECT * FROM seasons WHERE series_id=? AND number=?', (sid, number))
        if not rows:
            abort(404)
        path = f"tv/{item['tmdb_id']}/season/{number}"
        refresh = request.form.get('refresh') == '1'
        if refresh:
            tmdb.invalidate(path)
        if refresh or not rows[0]['loaded']:
            db.save_season(sid, number, tmdb.get(path))
        if wants_json():
            context = detail_data(sid)
            season = next(s for s in context['seasons'] if s['number'] == number)
            episodes = [ep for ep in context['episodes'] if ep['season'] == number]
            watched = sum(bool(ep['watched_at']) for ep in episodes)
            return jsonify(html=render_template('_season_body.html', item=context['item'], season=season,
                                                season_episodes=episodes, watched=watched),
                           summary=f'{watched} / {len(episodes)} watched',
                           next_html=render_template('_up_next.html', **context))
        return redirect(url_for('detail', sid=sid) + f'#season-{number}')

    @app.post('/series/<int:sid>/episode/<int:season>/<int:episode>')
    def episode(sid, season, episode):
        series(sid)
        try:
            db.progress(sid, season, episode, request.form.get('watched') == '1')
        except ValueError as error:
            abort(400, str(error))
        return redirect(url_for('detail', sid=sid) + f'#season-{season}')

    @app.post('/series/<int:sid>/save')
    def save(sid):
        item = series(sid)
        status = request.form.get('status')
        rating = request.form.get('rating', '')
        if status not in STATUSES or (rating and rating not in [str(i) for i in range(1, 11)]):
            abort(400, 'Choose a valid status and rating.')
        catalog, seasons = None, None
        try:
            if status == 'Completed' and (item['status'] != 'Completed' or request.form.get('complete_all') == '1'):
                tmdb.invalidate(f"tv/{item['tmdb_id']}")
                catalog = fetch_catalog(item['tmdb_id'])
                if not isinstance(catalog.get('seasons'), list):
                    raise TMDBError('TMDB returned incomplete season information. Please try again.')
                numbers = sorted({s['season_number'] for s in catalog.get('seasons', [])})
                def get_season(number):
                    path = f"tv/{item['tmdb_id']}/season/{number}"
                    tmdb.invalidate(path)
                    data = tmdb.get(path)
                    if not isinstance(data.get('episodes'), list):
                        raise TMDBError('TMDB returned an incomplete episode list. Please try again.')
                    return number, data
                with ThreadPoolExecutor(max_workers=4) as pool:
                    seasons = dict(pool.map(get_season, numbers))
            db.save_journal(sid, status, int(rating) if rating else None, request.form.get('note', '')[:10000],
                            int(request.form.get('favorite') == '1'),
                            request.form.get('progress_version', item['progress_version'], type=int), catalog, seasons)
        except (TMDBError, ValueError) as exc:
            message = str(exc) + ' Your journal and progress have not been changed.'
            code = exc.status if isinstance(exc, TMDBError) else 409
            if wants_json():
                return jsonify(error=message), code
            context = detail_data(sid)
            context['item'].update(status=status, rating=int(rating) if rating else None,
                                   note=request.form.get('note', '')[:10000], favorite=int(request.form.get('favorite') == '1'))
            return render_template('detail.html', save_error=message, **context), code
        flash('All aired episodes, including specials, are marked watched.' if catalog is not None else 'Your journal has been saved.', 'success')
        if wants_json():
            return jsonify(url=url_for('detail', sid=sid))
        return redirect(url_for('detail', sid=sid))

    @app.get('/people/<int:pid>')
    def person(pid):
        data = tmdb.get(f'person/{pid}', append_to_response='tv_credits')
        role = request.args.get('role', 'all')
        if role not in ('all', 'acting', 'directing'):
            role = 'all'
        credits = data.get('tv_credits') or {}
        shows = {}
        for group in ('cast', 'crew'):
            for credit in credits.get(group, []):
                if not credit.get('id') or credit.get('adult'):
                    continue
                if role == 'acting' and group != 'cast':
                    continue
                if role == 'directing' and (group != 'crew' or credit.get('job') != 'Director'):
                    continue
                show = shows.setdefault(credit['id'], dict(credit, roles=[]))
                label = (credit.get('character') or 'Actor') if group == 'cast' else (credit.get('job') or 'Crew')
                if label not in show['roles']:
                    show['roles'].append(label)
        items = sorted(shows.values(), key=lambda s: (s.get('first_air_date') or '', s.get('popularity') or 0), reverse=True)
        pages = max(1, (len(items) + 23) // 24)
        page = max(1, min(pages, request.args.get('page', 1, type=int)))
        members = {r['tmdb_id']: r['id'] for r in db.query('SELECT id,tmdb_id FROM series WHERE deleted_at IS NULL')}
        return render_template('person.html', person=data, items=items[(page-1)*24:page*24],
                               total=len(items), page=page, pages=pages, role=role, members=members)

    @app.post('/series/<int:sid>/next')
    def next_episode(sid):
        item = series(sid)
        expected = request.form.get('progress_version', type=int)
        if expected is None:
            abort(400, 'Reload this page before marking the next episode.')
        if expected != item['progress_version']:
            flash('Your progress has already changed. No additional episode was marked.', 'info')
            return redirect(url_for('detail', sid=sid))
        for season in db.query('SELECT * FROM seasons WHERE series_id=? AND number>0 ORDER BY number', (sid,)):
            if not season['loaded']:
                db.save_season(sid, season['number'], tmdb.get(f"tv/{item['tmdb_id']}/season/{season['number']}"))
            available = db.query('''SELECT * FROM episodes WHERE series_id=? AND season=?
                AND watched_at IS NULL AND air_date IS NOT NULL AND air_date<=? ORDER BY number LIMIT 1''',
                (sid, season['number'], date.today().isoformat()))
            if available:
                ep = db.mark_next(sid, expected)
                if ep:
                    flash(f"Watched S{ep['season']:02} E{ep['number']:02}: {ep['title']}", 'success')
                    return redirect(url_for('detail', sid=sid) + f"#season-{ep['season']}")
                flash('Your progress has already changed. No additional episode was marked.', 'info')
                return redirect(url_for('detail', sid=sid))
        flash('You are caught up with the available episodes. Refresh seasons to check for updates.')
        return redirect(url_for('detail', sid=sid))

    @app.post('/series/<int:sid>/delete')
    def delete(sid):
        series(sid)
        db.execute('UPDATE series SET deleted_at=? WHERE id=?', (now(), sid))
        session['undo'] = sid
        flash('Series removed. You can undo this from your library.')
        return redirect(url_for('library'))

    @app.post('/undo')
    def undo():
        sid = session.pop('undo', None)
        if sid:
            db.execute('UPDATE series SET deleted_at=NULL WHERE id=?', (sid,))
            flash('Series restored, including all episode progress.')
        return redirect(url_for('library'))

    @app.get('/settings')
    def settings():
        return render_template('settings.html')
    return app

if __name__ == '__main__':
    import threading
    import webbrowser
    from waitress import create_server
    server = create_server(create_app(), host='127.0.0.1', port=0)
    threading.Timer(1, lambda: webbrowser.open(f'http://127.0.0.1:{server.effective_port}')).start()
    server.run()
