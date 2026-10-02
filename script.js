const tg = window.Telegram?.WebApp;

let userData = {
    currency: 0,
    inventory: [],
    equipped: []
};
let selectedCategory = 'all';

if (tg) {
    tg.ready();
    tg.expand();
    const user = tg.initDataUnsafe?.user;
    if (user) {
        document.getElementById('username').textContent = user.first_name || 'Пользователь';
        document.getElementById('profile-id').textContent = user.id;
        if (user.photo_url) {
            document.getElementById('user-avatar').src = user.photo_url;
        }
    }
}

// Загрузка данных с бэкенда (из users.json через API)
async function fetchUserData() {
    try {
        const initData = tg?.initData || '';
        const response = await fetch('/api/me', {
            headers: {
                'X-Telegram-Init-Data': initData
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            userData.currency = data.currency || 0;
            userData.inventory = data.inventory || [];
            userData.equipped = data.equipped || [];

            // Обновляем баланс на экране
            document.getElementById('user-balance').textContent = userData.currency;
            
            updatePetView();
            renderWardrobe();
        } else {
            console.error('Ошибка авторизации в API');
        }
    } catch (e) {
        console.error('Не удалось загрузить данные профиля:', e);
    }
}

// Переключение вкладок
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));

    document.getElementById(`tab-${tabName}`).classList.add('active');

    const navButtons = document.querySelectorAll('.nav-item');
    if (tabName === 'home') navButtons[0].classList.add('active');
    if (tabName === 'wardrobe') navButtons[1].classList.add('active');
    if (tabName === 'rules') navButtons[2].classList.add('active');
    if (tabName === 'profile') navButtons[3].classList.add('active');

    if (tabName === 'home') {
        updatePetView();
    }
}

// Обновление питомца на главной
function updatePetView() {
    const petDisplay = document.getElementById('petDisplay');
    const equippedPreview = document.getElementById('equippedPreview');
    const equippedItems = userData.inventory.filter(item => userData.equipped.includes(item.id));

    if (equippedItems.length === 0) {
        petDisplay.innerHTML = `<span class="pet-emoji">🐾</span>`;
        equippedPreview.textContent = 'Ничего не надето';
    } else {
        let iconsHtml = `<span class="pet-emoji">🐾</span>`;
        equippedItems.forEach(item => {
            let icon = '✨';
            if (item.id.includes('cap')) icon = '🧢';
            else if (item.id.includes('glasses')) icon = '🕶️';
            else if (item.id.includes('collar')) icon = '💎';
            else if (item.id.includes('crown')) icon = '👑';
            
            iconsHtml += `<span style="font-size: 36px; margin-left: -8px;">${icon}</span>`;
        });
        petDisplay.innerHTML = iconsHtml;
        equippedPreview.textContent = equippedItems.map(i => i.name).join(' + ');
    }
}

// Отрисовка гардероба (вещей из инвентаря)
function renderWardrobe() {
    const grid = document.getElementById('itemsGrid');
    if (!grid) return;

    grid.innerHTML = '';

    const filtered = userData.inventory.filter(item => {
        if (selectedCategory === 'all') return true;
        return item.category === selectedCategory;
    });

    if (filtered.length === 0) {
        grid.innerHTML = '<p style="grid-column: span 2; text-align: center; color: var(--text-secondary); padding: 20px; font-size: 13px;">Инвентарь пуст. Купи что-нибудь через бота! 🛍️</p>';
        return;
    }

    filtered.forEach(item => {
        const isEquipped = userData.equipped.includes(item.id);
        const card = document.createElement('div');
        card.className = `item-card ${isEquipped ? 'equipped' : ''}`;

        let icon = '✨';
        if (item.id.includes('cap')) icon = '🧢';
        else if (item.id.includes('glasses')) icon = '🕶';
        else if (item.id.includes('collar')) icon = '💎';
        else if (item.id.includes('crown')) icon = '👑';

        card.innerHTML = `
            <div class="item-art">${icon}</div>
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

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', () => {
    const tabsContainer = document.getElementById('categoryTabs');
    if (tabsContainer) {
        tabsContainer.addEventListener('click', event => {
            const tab = event.target.closest('[data-category]');
            if (!tab) return;

            selectedCategory = tab.dataset.category;
            tabsContainer.querySelectorAll('.category-tab').forEach(btn => {
                btn.classList.toggle('active', btn === tab);
            });
            renderWardrobe();
        });
    }

    fetchUserData();
});