const busy = (button, active) => {
    if (!button) return;
    if (active) {
        button.dataset.original = button.textContent;
        button.disabled = true;
        button.textContent = button.dataset.busyLabel || 'Saving…';
    } else {
        button.disabled = false;
        if (button.dataset.original) button.textContent = button.dataset.original;
        delete button.dataset.original;
    }
};
async function submitForm(form, button, onSuccess, feedback) {
    if (form.dataset.pending) return;
    form.dataset.pending = 'true';
    const data = new FormData(form);
    busy(button, true);
    feedback.textContent = button.dataset.busyLabel || 'Saving…';
    feedback.classList.remove('error', 'success');
    try {
        const response = await fetch(form.action || location.href, {
            method: 'POST', body: data, headers: {Accept: 'application/json'}
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Please try again.');
        onSuccess(result);
    } catch (error) {
        feedback.textContent = error instanceof TypeError || error instanceof SyntaxError
            ? 'Could not complete the request. Please check your connection and try again.' : error.message;
        feedback.classList.add('error');
    } finally {
        busy(button, false);
        delete form.dataset.pending;
    }
}
document.addEventListener('submit', event => {
    const form = event.target;
    const button = event.submitter || form.querySelector('button:not([type="button"])');
    if (form.matches('[data-season-refresh]')) {
        event.preventDefault();
        loadSeason(form.closest('.season'), true);
    } else if (form.matches('[data-journal-form]')) {
        event.preventDefault();
        button.dataset.busyLabel = form.elements.status.value === 'Completed' && form.elements.complete_all.value === '1'
            ? 'Loading seasons & completing…' : 'Saving journal…';
        submitForm(form, button, result => location.assign(result.url), form.querySelector('.form-feedback'));
    } else if (form.matches('[data-add-form]')) {
        event.preventDefault();
        const feedback = form.querySelector('.form-message');
        submitForm(form, button, result => {
            const link = document.createElement('a');
            link.className = 'button success full-width';
            link.href = result.url;
            link.textContent = '✓ In your library · Open';
            form.replaceWith(link);
        }, feedback);
    } else if (form.method.toLowerCase() === 'post' || form.matches('[data-search-form]')) {
        busy(button, true);
    }
});
async function loadSeason(season, refresh = false) {
    if (!season || season.dataset.pending || (!refresh && season.dataset.loaded === '1')) return;
    season.dataset.pending = 'true';
    season.setAttribute('aria-busy', 'true');
    const feedback = season.querySelector('.season-feedback');
    feedback.classList.remove('error');
    feedback.textContent = 'Loading episodes…';
    const data = new FormData();
    data.set('csrf', document.querySelector('input[name="csrf"]').value);
    if (refresh) data.set('refresh', '1');
    try {
        const response = await fetch(season.dataset.url, {method:'POST',body:data,headers:{Accept:'application/json'}});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not load episodes. Try again.');
        season.querySelector('.season-body').innerHTML = result.html;
        season.querySelector('.season-count').textContent = result.summary;
        season.dataset.loaded = '1';
        document.getElementById('up-next').innerHTML = result.next_html;
        feedback.textContent = '';
    } catch (error) {
        feedback.textContent = error instanceof TypeError || error instanceof SyntaxError
            ? 'Could not load episodes. Check your connection and try again.' : error.message;
        feedback.classList.add('error');
    } finally {
        delete season.dataset.pending;
        season.removeAttribute('aria-busy');
    }
}
document.addEventListener('toggle', event => {
    if (event.target.matches('.season') && event.target.open) loadSeason(event.target);
}, true);
document.querySelectorAll('.season[open]').forEach(season => loadSeason(season));

const journal = document.querySelector('[data-journal-form]');
journal?.elements.status.addEventListener('change', () => {
    document.getElementById('completion-help').hidden = journal.elements.status.value !== 'Completed';
    journal.elements.complete_all.value = journal.elements.status.value === 'Completed' ? '1' : '0';
});

const people = document.querySelector('[data-people-url]');
async function loadPeople() {
    if (!people || people.dataset.pending) return;
    people.dataset.pending = 'true';
    let feedback = people.querySelector('.people-feedback');
    if (!feedback) {
        feedback = document.createElement('p');
        feedback.className = 'help people-feedback';
        feedback.setAttribute('role', 'status');
        people.prepend(feedback);
    }
    feedback.textContent = 'Loading cast & directors…';
    try {
        const data = new FormData();
        data.set('csrf', document.querySelector('input[name="csrf"]').value);
        const response = await fetch(people.dataset.peopleUrl, {method:'POST',body:data,headers:{Accept:'application/json'}});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Could not load cast & directors.');
        people.innerHTML = result.html;
        delete people.dataset.peopleUrl;
    } catch (error) {
        feedback.textContent = 'Cast & directors could not be updated. Your saved information is still available. ';
        const retry = document.createElement('button');
        retry.type = 'button'; retry.className = 'quiet'; retry.textContent = 'Try again';
        retry.addEventListener('click', loadPeople);
        feedback.append(retry);
    } finally { delete people.dataset.pending; }
}
loadPeople();
document.addEventListener('click', event => {
    if (event.target.closest('[data-dismiss]')) event.target.closest('.notice').remove();
});
window.addEventListener('pageshow', () => {
    document.querySelectorAll('button[data-original]').forEach(button => busy(button, false));
});
function openHashSeason() {
    if (!location.hash.startsWith('#season-')) return;
    const season = document.getElementById(location.hash.slice(1));
    if (season instanceof HTMLDetailsElement) season.open = true;
}
openHashSeason();
if (location.hash === '#search') document.getElementById('search')?.focus();
window.addEventListener('hashchange', openHashSeason);
document.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        const search = document.getElementById('search');
        if (search) search.focus(); else location.href = '/search#search';
    }
});
