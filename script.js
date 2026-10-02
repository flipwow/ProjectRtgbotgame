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
    { id: 'cat', name: 'Милый котенок', img: 'https://i.giphy.com/media/v1.Y2lkPTc5MGI3NjExM3Z2dXZvZnM2dnR6aXJ3ZXpxbWZ0NHJ1cTF4aTZ4ajN6bmR4YmdzaiZlcD12MV9pbninternalX9naWZfYnlfaWQmY3Q9Zw/Geimx3k8w1V9C/giphy.gif' },
    { id: 'bunny', name: 'Зайка', img: 'https://i.giphy.com/media/v1.Y2lkPTc5MGI3NjExOHp1dzF3ZHFhY3M3dDF2Z3lscml0anZ6aWJneGhkeXJ4aTlhczFjYyZlcD12MV9pbninternalX9naWZfYnlfaWQmY3Q9Zw/3NtY188QaxDjC/giphy.gif' },
    { id: 'dog', name: 'Щенок', img: 'https://i.giphy.com/media/v1.Y2lkPTc5MGI3NjExNWx1ZWhud3NtdXF4djlhdTN5NXU0a3N0aWNubmJmbTFzMWprOXAzayZlcD12MV9pbninternalX9naWZfYnlfaWQmY3Q9Zw/8vQSQ3cNXuDGo/giphy.gif' },
    { id: 'panda', name: 'Пандочка', img: 'https://i.giphy.com/media/v1.Y2lkPTc5MGI3NjExdTB6a3Z5dGoxdTZhNjdyNGk4MG55dHRyZndrMGF5NDJmdXExbnM4NyZlcD12MV9pbninternalX9naWZfYnlfaWQmY3Q9Zw/3o7TKSjRrfIPjeiVyM/giphy.gif' }
];

let currentPetId = 'cat';

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

    if (tabName === 'home') {
        updatePetView();
    } else if (tabName === 'chat') {
        fetchUserData(); // Обновляем реестр при переходе во вкладку
    }
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
        card.style.cssText = 'padding: 12px; display: flex; align-items: center; justify-content: space-between;';

        card.innerHTML = `
            <div>
                <h4 style="font-size: 14px; margin-bottom: 2px;">@${member.username}</h4>
                <p style="font-size: 11px; color: var(--text-secondary);">${member.role_name} • RP: ${member.rp}</p>
            </div>
            <button class="category-tab active" style="padding: 6px 12px; font-size: 11px;">Профиль</button>
        `;

        card.onclick = () => {
            showUserProfileModal(member);
        };

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
        let accessoriesHtml = '';
        equippedItems.forEach(() => {
            accessoriesHtml += `<span style="font-size: 24px; position: absolute; top: -5px; right: 25px;">✨</span>`;
        });
        petDisplay.innerHTML = `<div style="position: relative; display: inline-block;">${petHtml}${accessoriesHtml}</div>`;
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
                }
            } catch (e) {
                console.error('Ошибка при покупке:', e);
            }
        });

        grid.appendChild(card);
    });
}

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

// Мини-игры и дуэли
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
function openChallengeModal() { document.getElementById('challenge-modal').style.display = 'flex'; }
function closeChallengeModal() { document.getElementById('challenge-modal').style.display = 'none'; }
function shareChallengeLink() {
    const userId = tg?.initDataUnsafe?.user?.id || '0';
    if (tg?.switchInlineQuery) tg.switchInlineQuery(`challenge_ttt_${userId}`);
    closeChallengeModal();
}