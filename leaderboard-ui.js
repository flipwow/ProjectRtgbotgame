(() => {
    const GAME_OPTIONS = [{ id: 'tictactoe', label: 'Крестики-нолики' }];
    const TYPE_LABELS = { bots: 'Боты', duel: 'Дуэль' };
    const STORAGE_KEY = 'ritushka-leaderboard-selection-v1';
    let gameId = GAME_OPTIONS[0].id;
    let typeId = '';

    try {
        const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
        if (GAME_OPTIONS.some(game => game.id === saved.gameId)) gameId = saved.gameId;
        typeId = saved.typeId || '';
    } catch (_) {
        // Continue with the default selection when browser storage is unavailable.
    }

    const number = value => {
        const parsed = Number(value);
        return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
    };
    const leaderboard = () => Array.isArray(userData?.leaderboard) ? userData.leaderboard : [];
    const element = id => document.getElementById(id);

    function availableTypes() {
        const types = new Set();
        leaderboard().forEach(member => {
            const scores = member.mode_scores || {};
            if (number(scores.solo)) types.add('bots');
            if (number(scores.online)) types.add('duel');
        });
        return ['bots', 'duel'].filter(type => types.has(type));
    }

    function scoreFor(member, type) {
        const scores = member.mode_scores || {};
        return type === 'bots' ? number(scores.solo) : number(scores.online);
    }

    function storeSelection() {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ gameId, typeId })); }
        catch (_) { /* Selection remains usable for this page session. */ }
    }

    function renderRows(container, rows, emptyMessage, detailsForRow) {
        if (!container) return;
        if (!rows.length) {
            const empty = document.createElement('p');
            empty.className = 'leaderboard-empty';
            empty.textContent = emptyMessage;
            container.replaceChildren(empty);
            return;
        }

        const fragment = document.createDocumentFragment();
        rows.forEach((member, index) => {
            const row = document.createElement('article');
            row.className = 'leaderboard-row';
            const rank = document.createElement('span');
            rank.className = 'leaderboard-rank';
            rank.textContent = String(index + 1);
            const user = document.createElement('div');
            user.className = 'leaderboard-user';
            const name = document.createElement('h4');
            name.textContent = member.display_name || (member.username ? `@${member.username}` : `Игрок ${member.user_id || ''}`);
            const details = document.createElement('p');
            const result = detailsForRow(member);
            details.textContent = result.description;
            const total = document.createElement('strong');
            total.className = 'leaderboard-total';
            total.textContent = `${result.score} очк.`;
            user.append(name, details);
            row.append(rank, user, total);
            fragment.appendChild(row);
        });
        container.replaceChildren(fragment);
    }

    function renderGameOptions() {
        const options = element('leaderboardGameOptions');
        if (!options) return;
        options.replaceChildren();
        GAME_OPTIONS.forEach(game => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'category-tab leaderboard-game-option';
            button.textContent = game.label;
            button.setAttribute('aria-current', String(game.id === gameId));
            button.addEventListener('click', () => {
                gameId = game.id;
                typeId = availableTypes()[0] || '';
                storeSelection();
                element('leaderboardGameModal').style.display = 'none';
                renderLeaderboard();
            });
            options.appendChild(button);
        });
    }

    function renderLeaderboard() {
        const rows = leaderboard();
        const game = GAME_OPTIONS.find(item => item.id === gameId) || GAME_OPTIONS[0];
        const gameName = element('leaderboardGameName');
        if (gameName) gameName.textContent = game.label;

        const totalRows = rows.filter(member => number(member.score_value) > 0)
            .slice().sort((a, b) => number(b.score_value) - number(a.score_value));
        renderRows(element('overallLeaderboardList'), totalRows, 'Пока нет набранных очков.', member => ({
            description: `Очки: ${number(member.score_value)} · RP: ${number(member.convertible_rp)} · R$: ${number(member.balance_r)}`,
            score: number(member.score_value)
        }));

        const types = availableTypes();
        if (!types.includes(typeId)) typeId = types[0] || '';
        const tabs = element('leaderboardTypeTabs');
        if (tabs) {
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
                    storeSelection();
                    renderLeaderboard();
                });
                tabs.appendChild(button);
            });
        }

        const list = element('leaderboardList');
        if (!types.length || !typeId) {
            renderRows(list, [], 'Для этого игрового режима пока нет статистики.', () => ({ score: 0, description: '' }));
            return;
        }
        const modeRows = rows.filter(member => scoreFor(member, typeId) > 0)
            .slice().sort((a, b) => scoreFor(b, typeId) - scoreFor(a, typeId));
        renderRows(list, modeRows, 'В этом типе игры пока нет результатов.', member => ({
            description: `Очки: ${scoreFor(member, typeId)}`,
            score: scoreFor(member, typeId)
        }));
    }

    window.renderLeaderboard = renderLeaderboard;

    function init() {
        element('leaderboardGamePicker')?.addEventListener('click', () => {
            renderGameOptions();
            element('leaderboardGameModal').style.display = 'flex';
        });
        element('leaderboardGameModalClose')?.addEventListener('click', () => {
            element('leaderboardGameModal').style.display = 'none';
        });
        element('leaderboardGameModal')?.addEventListener('click', event => {
            if (event.target.id === 'leaderboardGameModal') event.currentTarget.style.display = 'none';
        });
        document.querySelectorAll('.nav-item').forEach((button, index) => {
            if (index === 1) button.addEventListener('click', () => setTimeout(renderLeaderboard, 0));
        });
        renderLeaderboard();
    }

    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
    else init();
})();
