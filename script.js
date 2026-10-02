const tg = window.Telegram?.WebApp;

let userData = {
    currency: 0,
    inventory: [],
    catalog: [],
    equipped: [],
    registry: []
};

let selectedWardrobePart = 'all';
let selectedShopCategory = 'all';

const AVAILABLE_PETS = [
    { id: 'cat', name: 'Милый котенок', img: 'https://media.giphy.com/media/Geimx3k8w1V9C/giphy.gif' },
    { id: 'bunny', name: 'Зайка', img: 'https://media.giphy.com/media/3NtY188QaxDjC/giphy.gif' },
    { id: 'dog', name: 'Щенок', img: 'https://media.giphy.com/media/8vQSQ3cNXuDGo/giphy.gif' },
    { id: 'panda', name: 'Пандочка', img: 'https://media.giphy.com/media/3o7TKSjRrfIPjeiVyM/giphy.gif' }
];

let currentPetId = 'cat';

// ===== Tic-Tac-Toe state =====
let tttMode = 'solo';          // 'solo' | 'duo'
let tttBoard = Array(9).fill(null);
let tttCurrent = 'X';
let tttGameOver = false;

if (tg) {
    tg.ready();
    tg.expand();
    const user = tg.initDataUnsafe?.user;
    if (user) {
        document.getElementById('username').textContent = user.first_name || 'Пользователь';
        if (user.photo_url) {
            document.getElementById('user-avatar').src = user.photo_url;
        }
    }
}

async function fetchUserData() {
    try {
        const initData = tg?.initData || '';
        const response = await fetch('/api/me', {
            headers: { 'X-Telegram-Init-Data': initData }
        });
        
        if (response.ok) {
            const data = await response.json();
            userData.currency = data.currency || 0;
            userData.inventory = data.inventory || [];
            userData.catalog = data.catalog || [];
            userData.equipped = data.equipped || [];
            userData.registry = data.registry || [];

            document.getElementById('user-balance').textContent = userData.currency;
            
            updatePetView();
            renderWardrobe();
            renderShop();
            renderChatRegistry();
        } else {
            console.error('Ошибка авторизации в API');
        }
    } catch (e) {
        console.error('Не удалось загрузить данные профиля:', e);
    }
}

function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));

    const targetTab = document.getElementById(`tab-${tabName}`);
    if (targetTab) targetTab.classList.add('active');

    const navButtons = document.querySelectorAll('.nav-item');
    if (tabName === 'home') navButtons[0].classList.add('active');
    if (tabName === 'wardrobe') navButtons[1].classList.add('active');
    if (tabName === 'play') navButtons[2].classList.add('active');
    if (tabName === 'shop') navButtons[3].classList.add('active');
    if (tabName === 'chat') navButtons[4].classList.add('active');

    if (tabName === 'home') updatePetView();
    if (tabName === 'chat') fetchUserData();
}

function renderChatRegistry() {
    const container = document.getElementById('chatUsersList');
    if (!container) return;

    container.innerHTML = '';

    if (!userData.registry || userData.registry.length === 0) {
        container.innerHTML = '<p style="text-align: center; color: var(--text-secondary); padding: 20px; font-size: 13px;">В реестре пока никого нет 💅</p>';
        return;
    }

    userData.registry.forEach(member => {
        const card = document.createElement('div');
        card.className = 'glass-card';
        card.style.cssText = 'padding: 12px; display: flex; align-items: center; justify-content: space-between; cursor: pointer;';

        card.innerHTML = `
            <div>
                <h4 style="font-size: 14px; margin-bottom: 2px;">@${member.username}</h4>
                <p style="font-size: 11px; color: var(--text-secondary);">${member.role_name} • RP: ${member.rp}</p>
            </div>
            <button class="category-tab active" style="padding: 6px 12px; font-size: 11px; pointer-events: none;">Профиль</button>
        `;

        card.onclick = () => showUserProfileModal(member);
        container.appendChild(card);
    });
}

function showUserProfileModal(member) {
    const modal = document.getElementById('userProfileModal');
    const title = document.getElementById('modalUsername');
    const details = document.getElementById('modalUserDetails');
    if (!modal || !title || !details) return;

    title.textContent = `@${member.username}`;
    details.innerHTML = `
        <p><strong>Статус:</strong> ${member.role_name}</p>
        <p><strong>Репутация (RP):</strong> ${member.rp}</p>
        <p><strong>Валюта:</strong> ${member.currency} R$</p>
        <p><strong>Надето вещей:</strong> ${member.equipped_count || 0}</p>
    `;
    modal.style.display = 'flex';
}

function closeUserProfileModal() {
    const modal = document.getElementById('userProfileModal');
    if (modal) modal.style.display = 'none';
}

function openPetSelector() {
    const modal = document.getElementById('petSelectorModal');
    if (modal) {
        modal.style.display = 'flex';
        renderPetChoices();
    }
}

function closePetSelector() {
    const modal = document.getElementById('petSelectorModal');
    if (modal) modal.style.display = 'none';
}

function renderPetChoices() {
    const grid = document.getElementById('petChoicesGrid');
    if (!grid) return;
    grid.innerHTML = '';

    AVAILABLE_PETS.forEach(pet => {
        const card = document.createElement('div');
        card.className = `pet-choice-card ${currentPetId === pet.id ? 'active' : ''}`;
        card.innerHTML = `
            <img src="${pet.img}" alt="${pet.name}" class="pet-choice-img">
            <div class="pet-choice-name">${pet.name}</div>
        `;
        card.onclick = () => {
            currentPetId = pet.id;
            updatePetView();
            closePetSelector();
            if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        };
        grid.appendChild(card);
    });
}

function updatePetView() {
    const petDisplay = document.getElementById('petDisplay');
    const equippedPreview = document.getElementById('equippedPreview');
    const equippedItems = userData.inventory.filter(item => userData.equipped.includes(item.id));

    const activePet = AVAILABLE_PETS.find(p => p.id === currentPetId) || AVAILABLE_PETS[0];
    let petHtml = `<img src="${activePet.img}" alt="${activePet.name}" class="pet-avatar-img" style="width: 100px; height: 100px; object-fit: contain;">`;

    if (equippedItems.length === 0) {
        petDisplay.innerHTML = petHtml;
        equippedPreview.textContent = 'Ничего не надето';
    } else {
        petDisplay.innerHTML = `<div style="position: relative; display: inline-block;">${petHtml}<span style="font-size: 22px; position: absolute; top: -8px; right: 18px;">✨</span></div>`;
        equippedPreview.textContent = equippedItems.map(i => i.name).join(' + ');
    }
}

function renderWardrobe() {
    const grid = document.getElementById('itemsGrid');
    if (!grid) return;
    grid.innerHTML = '';

    const filtered = userData.inventory.filter(item => {
        if (selectedWardrobePart === 'all') return true;
        return item.part === selectedWardrobePart;
    });

    if (filtered.length === 0) {
        grid.innerHTML = '<p style="grid-column: span 2; text-align: center; color: var(--text-secondary); padding: 20px; font-size: 13px;">В этой категории пусто. Купи шмотки в магазине! 🛍️</p>';
        return;
    }

    filtered.forEach(item => {
        const isEquipped = userData.equipped.includes(item.id);
        const card = document.createElement('div');
        card.className = `item-card ${isEquipped ? 'equipped' : ''}`;
        card.innerHTML = `
            <div class="item-art">✨</div>
            <div class="item-name">${item.name}</div>
            <div class="item-status-badge">${isEquipped ? 'Надето ✓' : 'Надеть'}</div>
        `;
        card.addEventListener('click', async () => {
            try {
                const res = await fetch(`/api/equip/${item.id}`, {
                    method: 'POST',
                    headers: { 'X-Telegram-Init-Data': tg?.initData || '' }
                });
                if (res.ok) {
                    const data = await res.json();
                    userData.equipped = data.equipped;
                    renderWardrobe();
                    updatePetView();
                    if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
                }
            } catch (e) {
                console.error('Ошибка при переодевании:', e);
            }
        });
        grid.appendChild(card);
    });
}

function renderShop() {
    const grid = document.getElementById('shopItemsGrid');
    if (!grid) return;
    grid.innerHTML = '';

    const filtered = userData.catalog.filter(item => {
        if (selectedShopCategory === 'all') return true;
        return item.category === selectedShopCategory;
    });

    filtered.forEach(item => {
        const card = document.createElement('div');
        card.className = `item-card ${item.owned ? 'equipped' : ''}`;

        let badgeText = `${item.price} R$`;
        if (item.owned) badgeText = 'Куплено ✓';
        else if (!item.allowed) badgeText = 'Нужен VIP 🛑';

        card.innerHTML = `
            <div class="item-art">🛍️</div>
            <div class="item-name">${item.name}</div>
            <div class="item-status-badge">${badgeText}</div>
        `;

        card.addEventListener('click', async () => {
            if (item.owned || !item.allowed) return;
            try {
                const res = await fetch(`/api/buy/${item.id}`, {
                    method: 'POST',
                    headers: { 'X-Telegram-Init-Data': tg?.initData || '' }
                });
                if (res.ok) {
                    const data = await res.json();
                    userData.currency = data.currency;
                    userData.inventory = data.inventory;
                    userData.catalog = data.catalog;
                    document.getElementById('user-balance').textContent = userData.currency;
                    renderShop();
                    renderWardrobe();
                    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
                }
            } catch (e) {
                console.error('Ошибка при покупке:', e);
            }
        });
        grid.appendChild(card);
    });
}

// ===== Tic-Tac-Toe =====
function openGameMenu(name) {
    if (name === 'tictactoe') {
        document.getElementById('games-menu').style.display = 'none';
        document.getElementById('tictactoe-modes').style.display = 'flex';
    }
}

function startTttGame(mode) {
    tttMode = mode;
    document.getElementById('games-menu').style.display = 'none';
    document.getElementById('tictactoe-modes').style.display = 'none';
    document.getElementById('game-tictactoe').style.display = 'flex';
    resetTtt();
}

function closeGame() {
    document.getElementById('game-tictactoe').style.display = 'none';
    document.getElementById('tictactoe-modes').style.display = 'none';
    document.getElementById('games-menu').style.display = 'flex';
}

function backTttModes() {
    document.getElementById('game-tictactoe').style.display = 'none';
    document.getElementById('tictactoe-modes').style.display = 'flex';
}

function openChallengeModal() {
    document.getElementById('challenge-modal').style.display = 'flex';
}

function closeChallengeModal() {
    document.getElementById('challenge-modal').style.display = 'none';
}

function shareChallengeLink() {
    const userId = tg?.initDataUnsafe?.user?.id || '0';
    if (tg?.switchInlineQuery) {
        tg.switchInlineQuery(`challenge_ttt_${userId}`);
    }
    closeChallengeModal();
}

function resetTtt() {
    tttBoard = Array(9).fill(null);
    tttCurrent = 'X';
    tttGameOver = false;
    updateTttUI();
    document.getElementById('ttt-status').textContent = 'Ходит: X (Крестики)';
}

function makeMove(index) {
    if (tttGameOver || tttBoard[index] !== null) return;

    tttBoard[index] = tttCurrent;
    updateTttUI();

    if (checkWinner()) {
        tttGameOver = true;
        document.getElementById('ttt-status').textContent = `Победа: ${tttCurrent}! 🎉`;
        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        return;
    }

    if (tttBoard.every(c => c !== null)) {
        tttGameOver = true;
        document.getElementById('ttt-status').textContent = 'Ничья! 🤝';
        return;
    }

    tttCurrent = tttCurrent === 'X' ? 'O' : 'X';
    document.getElementById('ttt-status').textContent = `Ходит: ${tttCurrent}`;

    // Ход бота в solo-режиме
    if (tttMode === 'solo' && tttCurrent === 'O' && !tttGameOver) {
        setTimeout(botMove, 450);
    }
}

function botMove() {
    const empty = tttBoard.map((v, i) => v === null ? i : null).filter(v => v !== null);
    if (empty.length === 0) return;

    // Простой AI: сначала пытается выиграть, потом блокирует, иначе случайно
    let move = findBestMove('O') ?? findBestMove('X') ?? empty[Math.floor(Math.random() * empty.length)];
    makeMove(move);
}

function findBestMove(player) {
    const wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
    for (const [a,b,c] of wins) {
        const line = [tttBoard[a], tttBoard[b], tttBoard[c]];
        if (line.filter(x => x === player).length === 2 && line.includes(null)) {
            return [a,b,c].find(i => tttBoard[i] === null);
        }
    }
    return null;
}

function checkWinner() {
    const wins = [[0,1,2],[3,4,5],[6,7,8],[0,3,6],[1,4,7],[2,5,8],[0,4,8],[2,4,6]];
    return wins.some(([a,b,c]) => tttBoard[a] && tttBoard[a] === tttBoard[b] && tttBoard[a] === tttBoard[c]);
}

function updateTttUI() {
    document.querySelectorAll('.ttt-cell').forEach((cell, i) => {
        cell.textContent = tttBoard[i] || '';
        cell.style.color = tttBoard[i] === 'X' ? '#ec4899' : '#8b5cf6';
        cell.disabled = tttGameOver || tttBoard[i] !== null;
    });
}

// ===== Init =====
window.addEventListener('DOMContentLoaded', () => {
    const wardrobeTabs = document.getElementById('wardrobeCategoryTabs');
    if (wardrobeTabs) {
        wardrobeTabs.addEventListener('click', event => {
            const tab = event.target.closest('[data-part]');
            if (!tab) return;
            selectedWardrobePart = tab.dataset.part;
            wardrobeTabs.querySelectorAll('.category-tab').forEach(b => b.classList.toggle('active', b === tab));
            renderWardrobe();
        });
    }

    const shopTabs = document.getElementById('shopCategoryTabs');
    if (shopTabs) {
        shopTabs.addEventListener('click', event => {
            const tab = event.target.closest('[data-shopcat]');
            if (!tab) return;
            selectedShopCategory = tab.dataset.shopcat;
            shopTabs.querySelectorAll('.category-tab').forEach(b => b.classList.toggle('active', b === tab));
            renderShop();
        });
    }

    fetchUserData();
});