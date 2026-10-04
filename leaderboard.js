(() => {
    const LABELS = {
        tictactoe: 'Крестики-нолики',
        snake: 'Змейка',
        bots: 'Боты',
        duel: 'Дуэль',
        solo: 'Соло'
    };
    const TYPE_LABELS = { bots: 'Боты', duel: 'Дуэль', solo: 'Соло' };
    const STORAGE_KEY = 'ritushka-leaderboard-selection-v1';
    let rows = [];
    let gameId = '';
    let typeId = '';

    const el = id => document.getElementById(id);
    const asNumber = value => {
        const number = Number(value);
        return Number.isFinite(number) && number > 0 ? number : 0;
    };
    const labelFor = id => LABELS[id] || id.replace(/[_-]+/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase());
    const savedSelection = () => {
        try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
        catch (_) { return {}; }
    };
    const saveSelection = () => {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ gameId, typeId })); }
        catch (_) { /* Storage can be disabled in private browsing. */ }
    };

    function getStats(member, game, type) {
        const value = member.game_scores?.[game]?.[type];
        if (value && typeof value === 'object') {
            return { score: asNumber(value.score), peak: asNumber(value.peak) };
        }
        if (game === 'tictactoe') {
            const legacyMode = type === 'duel' ? 'online' : type === 'bots' ? 'solo' : 'single';
            return { score: asNumber(member.mode_scores?.[legacyMode]), peak: 0 };
        }
        return { score: 0, peak: 0 };
    }

    function getGames() {
        const games = new Set(['tictactoe']);
        rows.forEach(member => Object.entries(member.game_scores || {}).forEach(([game, types]) => {
            if (types && Object.values(types).some(stats => asNumber(stats?.score) || asNumber(stats?.peak))) games.add(game);
        }));
        return [...games].map(id => ({ id, label: labelFor(id) }));
    }

    function getTypes(game) {
        const available = new Set();
        rows.forEach(member => Object.entries(member.game_scores?.[game] || {}).forEach(([type, stats]) => {
            if (TYPE_LABELS[type] && (asNumber(stats?.score) || asNumber(stats?.peak))) available.add(type);
        }));
        if (game === 'tictactoe') {
            available.add('bots');
            available.add('duel');
            rows.forEach(member => {
                if (asNumber(member.mode_scores?.solo)) available.add('bots');
                if (asNumber(member.mode_scores?.online) || asNumber(member.mode_scores?.local)) available.add('duel');
            });
        }
        return ['bots', 'duel', 'solo'].filter(type => available.has(type));
    }

    function renderOverall() {
        const container = el('overallLeaderboardList');
        if (!container) return;
        const totals = rows.filter(member => asNumber(member.score_value) > 0)
            .slice().sort((a, b) => asNumber(b.score_value) - asNumber(a.score_value));
        renderRows(container, totals, member => ({
            description: `Очки: ${asNumber(member.score_value)} · RP: ${asNumber(member.convertible_rp)} · R$: ${asNumber(member.balance_r)}`,
            score: asNumber(member.score_value)
        }), 'Пока нет набранных очков.');
    }

    function renderRows(container, list, readStats, emptyMessage) {
        if (!list.length) {
            const empty = document.createElement('p');
            empty.className = 'leaderboard-empty';
            empty.textContent = emptyMessage;
            container.replaceChildren(empty);
            return;
        }
        const fragment = document.createDocumentFragment();
        list.forEach((member, index) => {
            const stats = readStats(member);
            const row = document.createElement('article');
            row.className = 'leaderboard-row';
            const rank = document.createElement('span');
            rank.className = 'leaderboard-rank';
            rank.textContent = String(index + 1);
            const user = document.createElement('div');
            user.className = 'leaderboard-user';
            const name = document.createElement('h4');
            name.textContent = member.display_name || (member.username ? `@${member.username}` : `Игрок ${member.user_id || ''}`);
            const detail = document.createElement('p');
            detail.textContent = stats.description;
            const score = document.createElement('strong');
            score.className = 'leaderboard-total';
            score.textContent = `${stats.score} очк.`;
            user.append(name, detail);
            row.append(rank, user, score);
            fragment.appendChild(row);
        });
        container.replaceChildren(fragment);
    }

    function renderTypeTabs() {
        const tabs = el('leaderboardTypeTabs');
        if (!tabs) return;
        const types = getTypes(gameId);
        if (!types.includes(typeId)) typeId = types[0] || '';
        tabs.replaceChildren();
        types.forEach(type => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = `category-tab${type === typeId ? ' active' : ''}`;
            button.setAttribute('role', 'tab');
            button.setAttribute('aria-selected', String(type === typeId));
            button.textContent = TYPE_LABELS[type];
            button.addEventListener('click', () => {
                typeId = type;
                saveSelection();
                render();
            });
            tabs.appendChild(button);
        });
    }

    function renderGameChoices(games) {
        const choices = el('leaderboardGameOptions');
        choices.replaceChildren();
        games.forEach(game => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'leaderboard-game-option';
            button.textContent = game.label;
            button.setAttribute('aria-current', String(game.id === gameId));
            button.addEventListener('click', () => {
                gameId = game.id;
                typeId = getTypes(gameId)[0] || '';
                saveSelection();
                el('leaderboardGameModal').style.display = 'none';
                render();
            });
            choices.appendChild(button);
        });
    }

    function render() {
        const games = getGames();
        if (!games.some(game => game.id === gameId)) gameId = games[0]?.id || '';
        const game = games.find(item => item.id === gameId);
        const gameName = el('leaderboardGameName');
        if (gameName) gameName.textContent = game?.label || 'Нет игровых режимов';
        renderGameChoices(games);
        renderTypeTabs();
        renderOverall();

        const container = el('leaderboardList');
        if (!container) return;
        const types = getTypes(gameId);
        if (!gameId || !types.length || !typeId) {
            renderRows(container, [], () => ({ score: 0, description: '' }), 'Для игровых режимов пока нет статистики.');
            return;
        }
        const scored = rows.map(member => ({ member, stats: getStats(member, gameId, typeId) }))
            .filter(item => item.stats.score > 0 || item.stats.peak > 0)
            .sort((a, b) => b.stats.score - a.stats.score);
        renderRows(container, scored.map(item => item.member), member => {
            const stats = getStats(member, gameId, typeId);
            const details = [`Очки: ${stats.score}`];
            if (stats.peak > 0) details.push(`Рекорд за игру: ${stats.peak}`);
            return { description: details.join(' · '), score: stats.score || stats.peak };
        }, 'В этом типе игры пока нет результатов.');
    }

    async function refresh() {
        try {
            if (typeof window.fetchLeaderboard === 'function') await window.fetchLeaderboard();
            rows = Array.isArray(userData?.leaderboard) ? userData.leaderboard : [];
        } catch (_) {
            rows = Array.isArray(userData?.leaderboard) ? userData.leaderboard : [];
        }
        render();
    }

    function init() {
        const saved = savedSelection();
        gameId = saved.gameId || '';
        typeId = saved.typeId || '';
        el('leaderboardGamePicker')?.addEventListener('click', () => {
            renderGameChoices(getGames());
            el('leaderboardGameModal').style.display = 'flex';
        });
        el('leaderboardGameModalClose')?.addEventListener('click', () => { el('leaderboardGameModal').style.display = 'none'; });
        el('leaderboardGameModal')?.addEventListener('click', event => {
            if (event.target.id === 'leaderboardGameModal') event.currentTarget.style.display = 'none';
        });
        document.querySelectorAll('.nav-item').forEach((button, index) => {
            if (index === 1) button.addEventListener('click', () => setTimeout(refresh, 0));
        });
        window.addEventListener('focus', refresh);
        refresh();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
    else init();
})();
