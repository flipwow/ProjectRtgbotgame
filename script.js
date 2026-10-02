
const tg = window.Telegram?.WebApp;

if (tg) {
    tg.ready();
    tg.expand();
}

// Каталог предметов
const items = [
    { id: 'cap_pink', name: 'Розовая кепка', price: 20, icon: '🧢', category: 'head' },
    { id: 'cap_black', name: 'Чёрная кепка с черепом', price: 25, icon: '🧢', category: 'head' },
    { id: 'glasses_pink', name: 'Розовые очки', price: 25, icon: '🕶️', category: 'glasses' },
    { id: 'glasses_matrix', name: 'Солнечные очки Матрица', price: 40, icon: '🕶️', category: 'glasses' },
    { id: 'cool_glasses', name: 'Крутые пиксельные очки', price: 55, icon: '😎', category: 'glasses' },
    { id: 'collar', name: 'Ошейник из страз', price: 30, icon: '💎', category: 'accessory' },
    { id: 'crown', name: 'Золотая корона', price: 150, icon: '👑', category: 'head', luxury: true },
    { id: 'leash', name: 'Бриллиантовый поводок', price: 300, icon: '💠', category: 'accessory', luxury: true }
];

// Элементы интерфейса
const openBtn = document.getElementById('openWardrobe');
const wardrobe = document.getElementById('wardrobeView');
const backHome = document.getElementById('backHome');
const grid = document.getElementById('itemsGrid');
const tabs = document.getElementById('categoryTabs');
const detail = document.getElementById('itemDetail');

let selectedCategory = 'all';

// API
// Замени адрес на настоящий HTTPS-адрес своего сервера.
const API_URL = "https://ТВОЙ-СЕРВЕР";

async function apiRequest(endpoint, method = "GET") {
    if (!tg || !tg.initData) {
        throw new Error("Открой Mini App через Telegram");
    }

    const response = await fetch(`${API_URL}${endpoint}`, {
        method: method,
        headers: {
            "Content-Type": "application/json",
            "X-Telegram-Init-Data": tg.initData
        }
    });

    if (!response.ok) {
        throw new Error(`Ошибка API: ${response.status}`);
    }

    return await response.json();
}

// Загрузка профиля
async function loadProfile() {
    try {
        const data = await apiRequest("/api/me");

        console.log("Профиль пользователя:", data);

        return data;
    } catch (error) {
        console.error("Не удалось загрузить профиль:", error);
        return null;
    }
}

// Надеть или снять предмет
async function toggleItem(itemId) {
    try {
        const data = await apiRequest(
            `/api/equip/${encodeURIComponent(itemId)}`,
            "POST"
        );

        console.log("Обновлённый гардероб:", data);

        return data;
    } catch (error) {
        console.error("Ошибка гардероба:", error);
        return null;
    }
}

// Отображение каталога
function renderItems() {
    if (!detail || !grid) return;

    detail.classList.add('hidden');
    grid.classList.remove('hidden');
    grid.innerHTML = '';

    const filtered = items.filter(item =>
        selectedCategory === 'all' ||
        item.category === selectedCategory
    );

    filtered.forEach(item => {
        const card = document.createElement('button');
        card.className = 'item-card';

        card.innerHTML = `
            <div class="item-art">${item.icon}</div>
            <div class="item-name"></div>
            <div class="item-price">
                ${item.price} R$${item.luxury ? ' · Luxury' : ''}
            </div>
        `;

        card.querySelector('.item-name').textContent = item.name;

        card.addEventListener('click', () => showItem(item));

        grid.appendChild(card);
    });
}

// Открытие предмета
function showItem(item) {
    grid.classList.add('hidden');
    detail.classList.remove('hidden');

    document.getElementById('detailArt').textContent = item.icon;
    document.getElementById('detailName').textContent = item.name;

    document.getElementById('detailDescription').textContent =
        item.luxury
            ? 'Предмет из категории Luxury. Для покупки в боте требуется подходящая роль.'
            : 'Предмет из каталога бутика Ритушки.';

    document.getElementById('detailPrice').textContent = `${item.price} R$`;

    const wearButton = document.getElementById('wearButton');
    wearButton.textContent = 'Предмет из каталога';
    wearButton.disabled = true;
}

// Открытие гардероба
if (openBtn && wardrobe) {
    openBtn.addEventListener('click', () => {
        wardrobe.classList.remove('hidden');
        openBtn.classList.add('hidden');

        renderItems();

        wardrobe.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
        });
    });
}

// Возврат на главную
if (backHome && wardrobe && openBtn) {
    backHome.addEventListener('click', () => {
        wardrobe.classList.add('hidden');
        openBtn.classList.remove('hidden');
        detail.classList.add('hidden');
    });
}

// Назад к списку предметов
const detailBack = document.getElementById('detailBack');

if (detailBack) {
    detailBack.addEventListener('click', renderItems);
}

// Переключение категорий
if (tabs) {
    tabs.addEventListener('click', event => {
        const tab = event.target.closest('[data-category]');

        if (!tab) return;

        selectedCategory = tab.dataset.category;

        tabs.querySelectorAll('.category-tab').forEach(button => {
            button.classList.toggle('active', button === tab);
        });

        renderItems();
    });
}

// Загрузка профиля после запуска страницы
document.addEventListener('DOMContentLoaded', () => {
    loadProfile();
});
