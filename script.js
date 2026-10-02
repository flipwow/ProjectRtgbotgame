const tg = window.Telegram?.WebApp;

let userData = {
    currency: 0,
    inventory: [],
    catalog: [],
    equipped: []
};
let selectedWardrobePart = 'all';
let selectedShopCategory = 'all';

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
            userData.catalog = data.catalog || [];
            userData.equipped = data.equipped || [];

            // Обновляем баланс на экране
            document.getElementById('user-balance').textContent = userData.currency;
            
            updatePetView();
            renderWardrobe();
            renderShop();
        } else {
            console.error('Ошибка авторизации в API');
        }
    } catch (e) {
        console.error('Не удалось загрузить данные профиля:', e);
    }
}

// Переключение вкладок нижней навигации
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));

    document.getElementById(`tab-${tabName}`).classList.add('active');

    const navButtons = document.querySelectorAll('.nav-item');
    if (tabName === 'home') navButtons[0].classList.add('active');
    if (tabName === 'wardrobe') navButtons[1].classList.add('active');
    if (tabName === 'shop') navButtons[2].classList.add('active');
    if (tabName === 'rules') navButtons[3].classList.add('active');
    if (tabName === 'profile') navButtons[4].classList.add('active');

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
            if (item.id.includes('cap') || item.id.includes('crown')) icon = '🧢';
            else if (item.id.includes('glasses')) icon = '🕶️';
            else if (item.id.includes('collar') || item.id.includes('leash')) icon = '💎';
            
            iconsHtml += `<span style="font-size: 36px; margin-left: -8px;">${icon}</span>`;
        });
        petDisplay.innerHTML = iconsHtml;
        equippedPreview.textContent = equippedItems.map(i => i.name).join(' + ');
    }

    // Добавляем мини-реакцию на клик по животному
    petDisplay.onclick = () => {
        petDisplay.style.transform = 'scale(1.2) rotate(10deg)';
        setTimeout(() => {
            petDisplay.style.transform = 'scale(1)';
        }, 200);
        if (tg?.HapticFeedback) {
            tg.HapticFeedback.impactOccurred('light'); // Легкая вибрация в Telegram, если поддерживается
        }
    };
}

// Отрисовка гардероба (фильтрация по частям тела: Все, Голова, Тело, Ноги, Руки)
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

        let icon = '✨';
        if (item.id.includes('cap') || item.id.includes('crown')) icon = '👑';
        else if (item.id.includes('glasses')) icon = '🕶';
        else icon = '💎';

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

// Отрисовка магазина (покупка за R$)
function renderShop() {
    const grid = document.getElementById('shopItemsGrid');
    if (!grid) return;

    grid.innerHTML = '';

    const filtered = userData.catalog.filter(item => {
        if (selectedShopCategory === 'all') return true;
        return item.category === selectedShopCategory;
    });

    if (filtered.length === 0) {
        grid.innerHTML = '<p style="grid-column: span 2; text-align: center; color: var(--text-secondary); padding: 20px; font-size: 13px;">В магазине ничего нет.</p>';
        return;
    }

    filtered.forEach(item => {
        const card = document.createElement('div');
        card.className = `item-card ${item.owned ? 'equipped' : ''}`;

        let icon = '✨';
        if (item.id.includes('cap') || item.id.includes('crown')) icon = '👑';
        else if (item.id.includes('glasses')) icon = '🕶';
        else icon = '💎';

        let badgeText = `${item.price} R$`;
        if (item.owned) {
            badgeText = 'Куплено ✓';
        } else if (!item.allowed) {
            badgeText = 'Нужен VIP 🛑';
        }

        card.innerHTML = `
            <div class="item-art">${icon}</div>
            <div class="item-name">${item.name}</div>
            <div class="item-status-badge">${badgeText}</div>
        `;

        card.addEventListener('click', async () => {
            if (item.owned) {
                tg?.showAlert?.('У тебя уже есть эта вещь! Проверь гардероб 💅');
                return;
            }
            if (!item.allowed) {
                tg?.showAlert?.('Этот товар доступен только для VIP-статусов (dura / boss)! 🛑');
                return;
            }
            if (userData.currency < item.price) {
                tg?.showAlert?.(`Не хватает R$! Нужно ${item.price} R$, а у тебя всего ${userData.currency} R$. 📉`);
                return;
            }

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
                    tg?.showAlert?.(`Успешная покупка: ${item.name}! 🎉`);
                } else {
                    const err = await res.json();
                    tg?.showAlert?.(`Ошибка покупки: ${err.error || 'неизвестно'}`);
                }
            } catch (e) {
                console.error('Ошибка при покупке:', e);
            }
        });

        grid.appendChild(card);
    });
}

// Инициализация при загрузке
document.addEventListener('DOMContentLoaded', () => {
    // Вкладки фильтрации гардероба по частям тела
    const wardrobeTabsContainer = document.getElementById('wardrobeCategoryTabs');
    if (wardrobeTabsContainer) {
        wardrobeTabsContainer.addEventListener('click', event => {
            const tab = event.target.closest('[data-part]');
            if (!tab) return;

            selectedWardrobePart = tab.dataset.part;
            wardrobeTabsContainer.querySelectorAll('.category-tab').forEach(btn => {
                btn.classList.toggle('active', btn === tab);
            });
            renderWardrobe();
        });
    }

    // Вкладки фильтрации магазина
    const shopTabsContainer = document.getElementById('shopCategoryTabs');
    if (shopTabsContainer) {
        shopTabsContainer.addEventListener('click', event => {
            const tab = event.target.closest('[data-shopcat]');
            if (!tab) return;

            selectedShopCategory = tab.dataset.shopcat;
            shopTabsContainer.querySelectorAll('.category-tab').forEach(btn => {
                btn.classList.toggle('active', btn === tab);
            });
            renderShop();
        });
    }

    fetchUserData();
});