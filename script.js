const tg = window.Telegram?.WebApp;

let userData = {
    currency: 0,
    inventory: [],
    catalog: [],
    equipped: [],
    registry: [],
    leaderboard: [],
    foodCatalog: [],
    pet: null,
    user: null,
    rp: 0,
    maxRp: 0
};

const AVAILABLE_PETS = [
    {
        id: 'cat',
        name: 'Милый котенок',
        img: 'https://media.giphy.com/media/Geimx3k8w1V9C/giphy.gif'
    },
    {
        id: 'bunny',
        name: 'Зайка',
        img: 'https://media.giphy.com/media/3NtY188QaxDjC/giphy.gif'
    },
    {
        id: 'dog',
        name: 'Щенок',
        img: 'https://media.giphy.com/media/8vQSQ3cNXuDGo/giphy.gif'
    },
    {
        id: 'panda',
        name: 'Пандочка',
        img: 'https://media.giphy.com/media/3o7TKSjRrfIPjeiVyM/giphy.gif'
    }
];

let currentPetId = 'cat';

let tttMode = 'solo';
let tttBoard = Array(9).fill(null);
let tttCurrent = 'X';
let tttGameOver = false;
let mySymbol = null;
let socket = null;
let currentRoomId = null;


function initTelegramUser() {
    if (!tg) {
        console.warn('Telegram WebApp не обнаружен');
        return;
    }

    tg.ready();
    tg.expand();

    const user = tg.initDataUnsafe?.user;

    if (!user) {
        console.warn('Данные пользователя не получены');
        return;
    }

    const usernameElement = document.getElementById('username');
    const avatarElement = document.getElementById('user-avatar');

    if (usernameElement) {
        usernameElement.textContent =
            user.first_name || 'Пользователь';
    }

    if (avatarElement && user.photo_url) {
        avatarElement.src = user.photo_url;

        avatarElement.onerror = () => {
            console.warn('Не удалось загрузить аватарку');
        };
    }
}


async function fetchUserData() {
    try {
        const initData = tg?.initData || '';

        const response = await fetch('/api/me', {
            headers: {
                'X-Telegram-Init-Data': initData
            }
        });

        if (!response.ok) {
            console.error(
                'Ошибка API:',
                response.status,
                response.statusText
            );
            return;
        }

        const data = await response.json();

        userData.currency = data.currency || 0;
        userData.inventory = data.inventory || [];
        userData.catalog = data.catalog || [];
        userData.equipped = data.equipped || [];
        userData.registry = data.registry || [];
        userData.leaderboard = data.leaderboard || [];
        userData.foodCatalog = data.food_catalog || [];
        userData.pet = data.pet || null;
        userData.user = data.user || null;
        userData.rp = data.rp || 0;
        userData.maxRp = data.max_rp || 0;

        const balanceEl =
            document.getElementById('user-balance');

        if (balanceEl) {
            balanceEl.textContent = userData.currency;
        }

        const profileUsername =
            document.getElementById('profile-username');
        const profileRp =
            document.getElementById('profile-rp');
        const profileMaxRp =
            document.getElementById('profile-max-rp');
        const profileCurrency =
            document.getElementById('profile-currency');

        if (profileUsername) {
            profileUsername.textContent =
                userData.user?.username || 'Пользователь';
        }
        if (profileRp) profileRp.textContent = userData.rp;
        if (profileMaxRp) profileMaxRp.textContent = userData.maxRp;
        if (profileCurrency) profileCurrency.textContent = userData.currency;

        updatePetView();
        renderShop();
        renderChatRegistry();
        renderLeaderboard();

    } catch (error) {
        console.error(
            'Не удалось загрузить данные профиля:',
            error
        );
    }
}


function switchTab(tabName) {
    document
        .querySelectorAll('.tab-content')
        .forEach(tab => {
            tab.classList.remove('active');
        });

    document
        .querySelectorAll('.nav-item')
        .forEach(nav => {
            nav.classList.remove('active');
        });

    const targetTab =
        document.getElementById(`tab-${tabName}`);

    if (targetTab) {
        targetTab.classList.add('active');
    }

    const navButtons =
        document.querySelectorAll('.nav-item');

    const indexes = {
        home: 0,
        leaderboard: 1,
        play: 2,
        shop: 3,
        profile: 4
    };

    const index = indexes[tabName];

    if (index !== undefined) {
        navButtons[index]?.classList.add('active');
    }

    if (tabName === 'home') {
        updatePetView();
    }

    if (['leaderboard', 'shop', 'profile'].includes(tabName)) {
        fetchUserData();
    }
}


function renderChatRegistry() {
    const containers = [document.getElementById('profileUsersList')].filter(Boolean);

    if (containers.length === 0) return;

    containers.forEach(container => {
        container.innerHTML = '';

        if (!userData.registry || userData.registry.length === 0) {
            container.innerHTML = `
            <p
                style="
                    text-align: center;
                    color: var(--text-secondary);
                    padding: 20px;
                    font-size: 13px;
                "
            >
                Пока никто не запустил бота через /start
            </p>
        `;

            return;
        }

        userData.registry.forEach(member => {
            const card = document.createElement('div');
            card.className = 'glass-card registry-user-card';
            card.innerHTML = `
                <div>
                    <h4>@${escapeHtml(member.username)}</h4>
                    <p>${escapeHtml(member.role_name)} · RP: ${member.rp}</p>
                    <p>Счёт: ${member.currency} R$</p>
                </div>
                <span class="registry-user-arrow">→</span>
            `;

            card.onclick = () => showUserProfileModal(member);
            container.appendChild(card);
        });
    });
}


function renderLeaderboard() {
    const container = document.getElementById('leaderboardList');

    if (!container) return;

    if (!userData.leaderboard || userData.leaderboard.length === 0) {
        container.innerHTML = `
            <p class="leaderboard-empty">
                Пока нет набранных игровых очков
            </p>
        `;
        return;
    }

    const modeNames = {
        tictactoe_online: 'Крестики-нолики · онлайн'
    };

    container.innerHTML = userData.leaderboard.map((member, index) => {
        const modeScores = Object.entries(member.modes || {})
            .map(([mode, points]) => `
                <p>${escapeHtml(modeNames[mode] || mode)}: ${points} очков</p>
            `)
            .join('');

        return `
            <article class="leaderboard-row">
                <span class="leaderboard-rank">${index + 1}</span>
                <div class="leaderboard-user">
                    <h4>@${escapeHtml(member.username)}</h4>
                    ${modeScores}
                </div>
                <strong class="leaderboard-total">${member.total} очков</strong>
            </article>
        `;
    }).join('');
}


function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value ?? '';
    return div.innerHTML;
}


function showUserProfileModal(member) {
    const modal =
        document.getElementById('userProfileModal');

    const title =
        document.getElementById('modalUsername');

    const details =
        document.getElementById('modalUserDetails');

    if (!modal || !title || !details) return;

    title.textContent = `@${member.username}`;

    details.innerHTML = `
        <p>
            <strong>Статус:</strong>
            ${escapeHtml(member.role_name)}
        </p>

        <p>
            <strong>Репутация (RP):</strong>
            ${member.rp}
        </p>

        <p>
            <strong>Валюта:</strong>
            ${member.currency} R$
        </p>

        <p>
            <strong>Надето вещей:</strong>
            ${member.equipped_count || 0}
        </p>
    `;

    modal.style.display = 'flex';
}


function closeUserProfileModal() {
    const modal =
        document.getElementById('userProfileModal');

    if (modal) {
        modal.style.display = 'none';
    }
}


function openPetSelector() {
    const modal =
        document.getElementById('petSelectorModal');

    if (!modal) return;

    modal.style.display = 'flex';

    renderPetChoices();
}


function closePetSelector() {
    const modal =
        document.getElementById('petSelectorModal');

    if (modal) {
        modal.style.display = 'none';
    }
}


function renderPetChoices() {
    const grid =
        document.getElementById('petChoicesGrid');

    if (!grid) return;

    grid.innerHTML = '';

    AVAILABLE_PETS.forEach(pet => {
        const card =
            document.createElement('div');

        card.className =
            `pet-choice-card ${
                currentPetId === pet.id
                    ? 'active'
                    : ''
            }`;

        card.innerHTML = `
            <img
                src="${pet.img}"
                alt="${escapeHtml(pet.name)}"
                class="pet-choice-img"
            >

            <div class="pet-choice-name">
                ${escapeHtml(pet.name)}
            </div>
        `;

        card.onclick = () => {
            currentPetId = pet.id;

            updatePetView();
            closePetSelector();

            if (tg?.HapticFeedback) {
                tg.HapticFeedback.notificationOccurred(
                    'success'
                );
            }
        };

        grid.appendChild(card);
    });
}


function updatePetView() {
    const petDisplay =
        document.getElementById('petDisplay');

    const equippedPreview =
        document.getElementById('equippedPreview');

    if (!petDisplay || !equippedPreview) {
        return;
    }

    const equippedItems =
        userData.inventory.filter(item =>
            userData.equipped.includes(item.id)
        );

    const activePet =
        AVAILABLE_PETS.find(
            pet => pet.id === currentPetId
        ) || AVAILABLE_PETS[0];
    const level = Math.max(1, Number(userData.pet?.level || 1));
    const health = Math.max(0, Math.min(100, Number(userData.pet?.health ?? 100)));
    const hunger = Math.max(0, Math.min(100, Number(userData.pet?.hunger ?? 100)));

    const statValues = {
        'pet-level-value': `${level} / 10`,
        'pet-health-value': `${health} / 100`,
        'pet-hunger-value': `${hunger} / 100`
    };
    const statProgress = {
        'pet-level-bar': { value: level, max: 10, width: Math.min(level * 10, 100) },
        'pet-health-bar': { value: health, max: 100, width: health },
        'pet-hunger-bar': { value: hunger, max: 100, width: hunger }
    };

    Object.entries(statValues).forEach(([id, value]) => {
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    });

    Object.entries(statProgress).forEach(([id, progress]) => {
        const element = document.getElementById(id);
        if (!element) return;

        element.style.width = `${progress.width}%`;
        element.setAttribute('aria-valuemin', '0');
        element.setAttribute('aria-valuemax', String(progress.max));
        element.setAttribute('aria-valuenow', String(progress.value));
    });

    const petHtml = `
        <img
            src="${activePet.img}"
            alt="${escapeHtml(activePet.name)}"
            style="
                width: 100px;
                height: 100px;
                object-fit: contain;
            "
        >
    `;

    if (equippedItems.length === 0) {
        petDisplay.innerHTML = petHtml;
        equippedPreview.textContent = 'Питомец сыт и доволен ✨';
    } else {
        petDisplay.innerHTML = `
            <div
                style="
                    position: relative;
                    display: inline-block;
                "
            >
                ${petHtml}

                <span
                    style="
                        font-size: 22px;
                        position: absolute;
                        top: -8px;
                        right: 18px;
                    "
                >
                    ✨
                </span>
            </div>
        `;

        equippedPreview.textContent =
            equippedItems
                .map(item => item.name)
                .join(' + ');
    }
}


function renderShop() {
    const grid =
        document.getElementById('shopItemsGrid');

    if (!grid) return;

    grid.innerHTML = '';

    if (!userData.foodCatalog || userData.foodCatalog.length === 0) {
        grid.innerHTML = `
            <p
                style="
                    grid-column: span 2;
                    text-align: center;
                    color: var(--text-secondary);
                    padding: 20px;
                "
            >
                Магазин еды пока пуст
            </p>
        `;

        return;
    }

    userData.foodCatalog.forEach(food => {
        const card = document.createElement('article');
        card.className = 'item-card food-item-card';
        card.innerHTML = `
            <div class="item-art">${escapeHtml(food.name.split(' ')[0])}</div>
            <div class="item-name">${escapeHtml(food.name.replace(/^\S+\s*/, ''))}</div>
            <div class="food-item-effect">🍖 +${food.hunger_restore} · 💖 +${food.happiness_restore}</div>
            <div class="item-status-badge">В холодильнике: ${food.count || 0}</div>
            <button class="food-buy-button" type="button" ${userData.currency < food.price ? 'disabled' : ''}>
                Купить · ${food.price} R$
            </button>
        `;

        card.querySelector('.food-buy-button').addEventListener('click', async event => {
            event.stopPropagation();
            try {
                const response = await fetch(
                    `/api/buy-food/${encodeURIComponent(food.id)}`,
                    {
                        method: 'POST',
                        headers: {
                            'X-Telegram-Init-Data': tg?.initData || ''
                        }
                    }
                );
                const data = await response.json();
                if (!response.ok) {
                    tg?.showAlert?.(data.error === 'Not enough currency'
                        ? 'Недостаточно R$ для покупки.'
                        : 'Не удалось купить еду.');
                    return;
                }

                userData.currency = data.currency;
                userData.foodCatalog = data.food_catalog;
                userData.pet = data.pet;
                document.getElementById('user-balance').textContent = userData.currency;
                const profileCurrency = document.getElementById('profile-currency');
                if (profileCurrency) profileCurrency.textContent = userData.currency;
                renderShop();
                updatePetView();
            } catch (error) {
                console.error('Ошибка при покупке еды:', error);
            }
        });

        grid.appendChild(card);
    });
}


function openGameMenu(name) {
    if (name !== 'tictactoe') {
        return;
    }

    const gamesMenu =
        document.getElementById('games-menu');

    const modesMenu =
        document.getElementById('tictactoe-modes');

    if (gamesMenu) {
        gamesMenu.style.display = 'none';
    }

    if (modesMenu) {
        modesMenu.style.display = 'flex';
    }
}


function startTttGame(mode) {
    tttMode = mode;

    const gamesMenu =
        document.getElementById('games-menu');

    const modesMenu =
        document.getElementById('tictactoe-modes');

    const gameTtt =
        document.getElementById('game-tictactoe');

    if (gamesMenu) {
        gamesMenu.style.display = 'none';
    }

    if (modesMenu) {
        modesMenu.style.display = 'none';
    }

    if (gameTtt) {
        gameTtt.style.display = 'flex';
    }

    if (mode === 'solo' || mode === 'local') {
        resetTtt();
    }
}


function closeGame() {
    if (socket) {
        socket.close();
        socket = null;
    }

    const gameTtt =
        document.getElementById('game-tictactoe');

    const modesMenu =
        document.getElementById('tictactoe-modes');

    const gamesMenu =
        document.getElementById('games-menu');

    if (gameTtt) {
        gameTtt.style.display = 'none';
    }

    if (modesMenu) {
        modesMenu.style.display = 'none';
    }

    if (gamesMenu) {
        gamesMenu.style.display = 'flex';
    }
}


function backTttModes() {
    if (socket) {
        socket.close();
        socket = null;
    }

    const gameTtt =
        document.getElementById('game-tictactoe');

    const modesMenu =
        document.getElementById('tictactoe-modes');

    if (gameTtt) {
        gameTtt.style.display = 'none';
    }

    if (modesMenu) {
        modesMenu.style.display = 'flex';
    }
}


function resetTtt() {
    if (socket) {
        socket.close();
        socket = null;
    }

    tttBoard = Array(9).fill(null);
    tttCurrent = 'X';
    tttGameOver = false;
    mySymbol = null;

    updateTttUI();

    const statusEl =
        document.getElementById('ttt-status');

    if (statusEl) {
        statusEl.textContent =
            'Ходит: X (Крестики)';
    }
}


function makeMove(index) {
    if (
        tttGameOver ||
        tttBoard[index] !== null
    ) {
        return;
    }

    if (tttMode === 'online') {
        if (
            !socket ||
            socket.readyState !== WebSocket.OPEN
        ) {
            return;
        }

        if (tttCurrent !== mySymbol) {
            return;
        }

        socket.send(
            JSON.stringify({
                type: 'move',
                index
            })
        );

        return;
    }

    tttBoard[index] = tttCurrent;

    updateTttUI();

    if (checkWinner()) {
        tttGameOver = true;

        const statusEl =
            document.getElementById('ttt-status');

        if (statusEl) {
            statusEl.textContent =
                `Победа: ${tttCurrent}! 🎉`;
        }

        if (tg?.HapticFeedback) {
            tg.HapticFeedback.notificationOccurred(
                'success'
            );
        }

        updateTttUI();
        return;
    }

    if (tttBoard.every(cell => cell !== null)) {
        tttGameOver = true;

        const statusEl =
            document.getElementById('ttt-status');

        if (statusEl) {
            statusEl.textContent =
                'Ничья! 🤝';
        }

        updateTttUI();
        return;
    }

    tttCurrent =
        tttCurrent === 'X'
            ? 'O'
            : 'X';

    const statusEl =
        document.getElementById('ttt-status');

    if (statusEl) {
        statusEl.textContent =
            `Ходит: ${tttCurrent}`;
    }

    updateTttUI();

    if (
        tttMode === 'solo' &&
        tttCurrent === 'O' &&
        !tttGameOver
    ) {
        setTimeout(botMove, 450);
    }
}


function botMove() {
    if (tttGameOver) {
        return;
    }

    const empty =
        tttBoard
            .map((value, index) =>
                value === null
                    ? index
                    : null
            )
            .filter(value => value !== null);

    if (empty.length === 0) {
        return;
    }

    const move =
        findBestMove('O') ??
        findBestMove('X') ??
        empty[
            Math.floor(
                Math.random() * empty.length
            )
        ];

    makeMove(move);
}


function findBestMove(player) {
    const wins = [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
        [0, 3, 6],
        [1, 4, 7],
        [2, 5, 8],
        [0, 4, 8],
        [2, 4, 6]
    ];

    for (const [a, b, c] of wins) {
        const line = [
            tttBoard[a],
            tttBoard[b],
            tttBoard[c]
        ];

        if (
            line.filter(
                value => value === player
            ).length === 2 &&
            line.includes(null)
        ) {
            return [a, b, c].find(
                index => tttBoard[index] === null
            );
        }
    }

    return null;
}


function checkWinner() {
    const wins = [
        [0, 1, 2],
        [3, 4, 5],
        [6, 7, 8],
        [0, 3, 6],
        [1, 4, 7],
        [2, 5, 8],
        [0, 4, 8],
        [2, 4, 6]
    ];

    return wins.some(
        ([a, b, c]) =>
            tttBoard[a] &&
            tttBoard[a] === tttBoard[b] &&
            tttBoard[a] === tttBoard[c]
    );
}


function updateTttUI() {
    document
        .querySelectorAll('.ttt-cell')
        .forEach((cell, index) => {

            cell.textContent =
                tttBoard[index] || '';

            cell.style.color =
                tttBoard[index] === 'X'
                    ? '#ec4899'
                    : '#8b5cf6';

            cell.disabled =
                tttGameOver ||
                tttBoard[index] !== null ||
                (
                    tttMode === 'online' &&
                    tttCurrent !== mySymbol
                );
        });
}


function connectToRoom(roomId) {
    if (!roomId) {
        return;
    }

    if (socket) {
        socket.close();
    }

    currentRoomId = roomId;
    tttMode = 'online';
    tttGameOver = false;

    const protocol =
        window.location.protocol === 'https:'
            ? 'wss:'
            : 'ws:';

    const wsUrl =
        `${protocol}//${window.location.host}/ws/game/${encodeURIComponent(roomId)}`;

    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        socket.send(JSON.stringify({
            type: 'auth',
            init_data: tg?.initData || ''
        }));

        const statusEl =
            document.getElementById('ttt-status');

        if (statusEl) {
            statusEl.textContent =
                'Ожидание соперника...';
        }
    };

    socket.onmessage = event => {
        try {
            const data =
                JSON.parse(event.data);

            const statusEl =
                document.getElementById('ttt-status');

            if (data.type === 'joined') {
                mySymbol = data.symbol;
                tttBoard = data.board || Array(9).fill(null);
                tttCurrent = data.current || 'X';

                updateTttUI();

                if (statusEl) {
                    statusEl.textContent =
                        data.status === 'waiting'
                            ? `Ты играешь за ${mySymbol}. Ожидание соперника...`
                            : `Ты: ${mySymbol} | Ходит: ${tttCurrent}`;
                }
            }

            if (
                data.type === 'start' ||
                data.type === 'update'
            ) {
                tttBoard =
                    data.board || Array(9).fill(null);

                tttCurrent =
                    data.current || 'X';

                tttGameOver =
                    data.status === 'finished';

                updateTttUI();

                if (data.status === 'finished') {

                    if (data.winner === 'draw') {
                        if (statusEl) {
                            statusEl.textContent =
                                'Ничья! 🤝';
                        }
                    } else {
                        const isWin =
                            data.winner === mySymbol;

                        if (statusEl) {
                            statusEl.textContent =
                                isWin
                                    ? 'Ты победил! 🎉'
                                    : `Победил ${data.winner}`;
                        }

                        if (
                            isWin &&
                            tg?.HapticFeedback
                        ) {
                            tg.HapticFeedback.notificationOccurred(
                                'success'
                            );
                        }
                    }

                } else {
                    const turnText =
                        tttCurrent === mySymbol
                            ? 'Твой ход!'
                            : `Ход соперника (${tttCurrent})`;

                    if (statusEl) {
                        statusEl.textContent =
                            `Ты: ${mySymbol} | ${turnText}`;
                    }
                }
            }

        } catch (error) {
            console.error(
                'Ошибка обработки WebSocket:',
                error
            );
        }
    };

    socket.onerror = error => {
        console.error(
            'WebSocket error:',
            error
        );
    };

    socket.onclose = () => {
        if (socket) {
            socket = null;
        }
    };
}


function checkDuelParams() {
    const startParam =
        tg?.initDataUnsafe?.start_param || '';

    let roomId = null;

    if (startParam.startsWith('duel_')) {
        roomId = startParam.substring(5);
    } else if (
        startParam.startsWith('online_')
    ) {
        roomId = startParam.substring(7);
    }

    if (!roomId) {
        return;
    }

    switchTab('play');

    setTimeout(() => {
        const gamesMenu =
            document.getElementById('games-menu');

        const modesMenu =
            document.getElementById('tictactoe-modes');

        const game =
            document.getElementById('game-tictactoe');

        if (gamesMenu) {
            gamesMenu.style.display = 'none';
        }

        if (modesMenu) {
            modesMenu.style.display = 'none';
        }

        if (game) {
            game.style.display = 'flex';
        }

        connectToRoom(roomId);
    }, 500);
}


function openFeedMenuModal() {
    const modal =
        document.getElementById('feedMenuModal');

    if (!modal) {
        return;
    }

    modal.style.display = 'flex';

    renderFeedItems();
}


function closeFeedMenuModal() {
    const modal =
        document.getElementById('feedMenuModal');

    if (modal) {
        modal.style.display = 'none';
    }
}


function renderFeedItems() {
    const grid =
        document.getElementById('feedItemsGrid');

    if (!grid) {
        return;
    }

    const availableFood = userData.foodCatalog.filter(food => food.count > 0);

    if (availableFood.length === 0) {
        grid.innerHTML = `
            <p
                style="
                    text-align: center;
                    color: var(--text-secondary);
                    padding: 15px;
                "
            >
                Холодильник пуст. Загляни в магазин еды 🛍
            </p>
        `;

        return;
    }

    grid.innerHTML = availableFood.map(food => `
        <button class="feed-food-button" type="button" data-food-id="${escapeHtml(food.id)}">
            <span>${escapeHtml(food.name)} <small>×${food.count}</small></span>
            <span class="feed-food-effect">Накормить</span>
        </button>
    `).join('');

    grid.querySelectorAll('[data-food-id]').forEach(button => {
        button.addEventListener('click', () => feedPet(button.dataset.foodId));
    });
}


async function feedPet(foodId) {
    try {
        const response = await fetch('/api/pet/feed', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': tg?.initData || ''
            },
            body: JSON.stringify({ food_id: foodId })
        });
        const data = await response.json();

        if (!response.ok) {
            tg?.showAlert?.('Не удалось покормить питомца.');
            return;
        }

        userData.pet = data.pet;
        userData.foodCatalog = userData.foodCatalog.map(food => ({
            ...food,
            count: data.pet.inventory?.[food.id] || 0
        }));
        renderFeedItems();
        renderShop();
        updatePetView();
        if (tg?.HapticFeedback) {
            tg.HapticFeedback.notificationOccurred('success');
        }
    } catch (error) {
        console.error('Ошибка при кормлении питомца:', error);
    }
}


document.addEventListener(
    'DOMContentLoaded',
    () => {

        initTelegramUser();

        fetchUserData();
        checkDuelParams();
    }
);