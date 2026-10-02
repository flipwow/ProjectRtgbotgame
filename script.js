const tg = window.Telegram?.WebApp;

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

// Демо-инвентарь (вещи в гардеробе)
let userInventory = [
    { id: 'cap_pink', name: 'Розовая кепка', icon: '🧢', category: 'head', equipped: true },
    { id: 'glasses_pink', name: 'Розовые очки', icon: '🕶️', category: 'glasses', equipped: false },
    { id: 'collar', name: 'Ошейник из страз', icon: '💎', category: 'accessory', equipped: false }
];

let selectedCategory = 'all';

// Переключение вкладок
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));

    document.getElementById(`tab-${tabName}`).classList.add('active');

    const navButtons = document.querySelectorAll('.nav-item');
    if (tabName === 'home') navButtons[0].classList.add('active');
    if (tabName === 'wardrobe') navButtons[1].classList.add('active');
    if (tabName === 'shop') navButtons[2].classList.add('active');
    if (tabName === 'profile') navButtons[3].classList.add('active');

    if (tabName === 'home') {
        updatePetView();
    }
}

// Обновление питомца на главной
function updatePetView() {
    const petDisplay = document.getElementById('petDisplay');
    const equippedPreview = document.getElementById('equippedPreview');
    const equippedItems = userInventory.filter(item => item.equipped);

    if (equippedItems.length === 0) {
        petDisplay.innerHTML = `<span class="pet-emoji">🐾</span>`;
        equippedPreview.textContent = 'Ничего не надето';
    } else {
        let iconsHtml = `<span class="pet-emoji">🐾</span>`;
        equippedItems.forEach(item => {
            iconsHtml += `<span style="font-size: 36px; margin-left: -8px;">${item.icon}</span>`;
        });
        petDisplay.innerHTML = iconsHtml;
        equippedPreview.textContent = equippedItems.map(i => i.name).join(' + ');
    }
}

// Отрисовка гардероба
function renderWardrobe() {
    const grid = document.getElementById('itemsGrid');
    if (!grid) return;

    grid.innerHTML = '';

    const filtered = userInventory.filter(item => 
        selectedCategory === 'all' || item.category === selectedCategory
    );

    if (filtered.length === 0) {
        grid.innerHTML = '<p style="grid-column: span 2; text-align: center; color: var(--text-secondary); padding: 20px; font-size: 13px;">Здесь пока пусто</p>';
        return;
    }

    filtered.forEach(item => {
        const card = document.createElement('div');
        card.className = `item-card ${item.equipped ? 'equipped' : ''}`;

        card.innerHTML = `
            <div class="item-art">${item.icon}</div>
            <div class="item-name">${item.name}</div>
            <div class="item-status-badge">${item.equipped ? 'Надето ✓' : 'Надеть'}</div>
        `;

        card.addEventListener('click', () => {
            item.equipped = !item.equipped;
            renderWardrobe();
            updatePetView();
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

    updatePetView();
    renderWardrobe();
});