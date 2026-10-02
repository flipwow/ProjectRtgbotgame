// Инициализация Telegram Web App
const tg = window.Telegram.WebApp;
tg.expand();

// Переключение вкладок
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.nav-item').forEach(nav => {
        nav.classList.remove('active');
    });

    document.getElementById(`tab-${tabName}`).classList.add('active');
    event.currentTarget.classList.add('active');
}

// Заглушки для загрузки данных (будут связаны с твоим бэкендом)
function loadUserData() {
    const user = tg.initDataUnsafe?.user;
    
    if (user) {
        document.getElementById('username').textContent = user.first_name || 'Пользователь';
        document.getElementById('profile-id').textContent = user.id;
        if (user.photo_url) {
            document.getElementById('user-avatar').src = user.photo_url;
        }
    } else {
        // Тестовые данные для браузера (когда запущено не из Telegram)
        document.getElementById('username').textContent = 'Гость';
        document.getElementById('profile-id').textContent = '12345678';
    }

    // Здесь можно вызывать твой бэкенд для получения баланса и гардероба
    // fetch('/api/profile?user_id=' + (user?.id || 12345678)) ...
}

// Рендер демонстрационных товаров в магазине
function renderShop() {
    const shopContainer = document.getElementById('shop-items');
    const demoItems = [
        { id: 1, name: 'Стильная куртка', price: 150, image: 'https://via.placeholder.com/100?text=Jacket' },
        { id: 2, name: 'Крутые очки', price: 75, image: 'https://via.placeholder.com/100?text=Glasses' }
    ];

    shopContainer.innerHTML = demoItems.map(item => `
        <div class="item-card">
            <img src="${item.image}" alt="${item.name}" class="item-image">
            <div class="item-title">${item.name}</div>
            <button class="action-btn" onclick="buyItem(${item.id})">Купить (${item.price} 💎)</button>
        </div>
    `).join('');
}

function buyItem(itemId) {
    alert(`Покупка товара с ID: ${itemId} в разработке!`);
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    loadUserData();
    renderShop();
});