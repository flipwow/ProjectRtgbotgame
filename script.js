const tg = window.Telegram?.WebApp;

let userData = {
    currency: 0,
    inventory: [],
    catalog: [],
    equipped: []
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
        document.getElementById('profile-id').textContent = user.id;
        if (user.photo_url) {
            document.getElementById('user-avatar').src = user.photo_url;
        }
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
        
        if (response.ok) {
            const data = await response.json();
            userData.currency = data.currency || 0;
            userData.inventory = data.inventory || [];
            userData.catalog = data.catalog || [];
            userData.equipped = data.equipped || [];

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
    if (tabName === 'profile') navButtons[4].classList.add('active');

    if (tabName === 'home') {
        updatePetView();
    }
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
    if (modal) {
        modal.style.display = 'none';
    }
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
            if (tg?.HapticFeedback) {
                tg.HapticFeedback.notificationOccurred('success');
            }
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
        equippedItems.forEach(item => {
            let icon = '✨';
            if (item.id.includes('cap') || item.id.includes('crown')) icon = '👑';
            else if (item.id.includes('glasses')) icon = '🕶';
            else if (item.id.includes('collar') || item.id.includes('leash')) icon = '💎';
            
            accessoriesHtml += `<span style="font-size: 24px; position: absolute; top: -5px; right: 25px;">${icon}</span>`;
        });

        petDisplay.innerHTML = `<div style="position: relative; display: inline-block;">${petHtml}${accessoriesHtml}</div>`;
        equippedPreview.textContent = equippedItems.map(i => i.name).join(' + ');
    }

    petDisplay.onclick = () => {
        const img = petDisplay.querySelector('.pet-avatar-img');
        if (img) {
            img.style.transform = 'scale(1.15) rotate(5deg)';
            setTimeout(() => {
                img.style.transform = 'scale(1)';
            }, 200);
        }
        if (tg?.HapticFeedback) {
            tg.HapticFeedback.impactOccurred('medium');
        }
    };
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

// Автоматический перехват параметров URL и навешивание слушателей
window.addEventListener('DOMContentLoaded', () => {
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

    // Обработка параметров URL при старте (дуэль)
    const urlParams = new URLSearchParams(window.location.search);
    const mode = urlParams.get('mode');
    const challenger = urlParams.get('challenger');

    if (mode === 'duo' && challenger) {
        switchTab('play');
        startTttGame('duo');
    }

    fetchUserData();
});

// --- ЛОГИКА МИНИ-ИГР ВО ВКЛАДКЕ PLAY ---

function openGameMenu(gameName) {
    if (gameName === 'tictactoe') {
        document.getElementById('games-menu').style.display = 'none';
        document.getElementById('tictactoe-modes').style.display = 'flex';
        document.getElementById('play-subtitle').textContent = 'Выберите режим игры ⚔️';
    } else if (gameName === 'fortune') {
        alert('Скоро открытие Колеса Фортуны! 💅');
    }
}

function startTttGame(mode) {
    tttMode = mode; // 'solo' или 'duo'
    document.getElementById('games-menu').style.display = 'none';
    document.getElementById('tictactoe-modes').style.display = 'none';
    document.getElementById('game-tictactoe').style.display = 'flex';
    document.getElementById('play-subtitle').textContent = mode === 'solo' ? 'Игра против бота 🤖' : 'Крестики-нолики на двоих 👥';
    resetTtt();
}

function backTttModes() {
    document.getElementById('game-tictactoe').style.display = 'none';
    document.getElementById('tictactoe-modes').style.display = 'flex';
    document.getElementById('play-subtitle').textContent = 'Выберите режим игры ⚔️️';
}

function closeGame() {
    document.getElementById('game-tictactoe').style.display = 'none';
    document.getElementById('tictactoe-modes').style.display = 'none';
    document.getElementById('games-menu').style.display = 'flex';
    document.getElementById('play-subtitle').textContent = 'Выбирай развлечение и играй 🎮';
}

// --- ЛОГИКА КРЕСТИКОВ-НОЛИКОВ ---
let tttBoard = ['', '', '', '', '', '', '', '', ''];
let tttCurrentPlayer = 'X';
let tttIsActive = true;
let tttMode = 'duo';

const winningCombinations = [
    [0, 1, 2], [3, 4, 5], [6, 7, 8],
    [0, 3, 6], [1, 4, 7], [2, 5, 8],
    [0, 4, 8], [2, 4, 6]
];

function makeMove(index) {
    if (!tttIsActive || tttBoard[index] !== '') return;
    if (tttMode === 'solo' && tttCurrentPlayer === 'O') return;

    tttBoard[index] = tttCurrentPlayer;
    
    if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }

    renderTttBoard();
    
    if (checkTttWinOrDraw()) return;

    tttCurrentPlayer = tttCurrentPlayer === 'X' ? 'O' : 'X';
    updateTttStatus();

    if (tttMode === 'solo' && tttCurrentPlayer === 'O' && tttIsActive) {
        setTimeout(botMove, 500);
    }
}

function botMove() {
    if (!tttIsActive) return;

    let emptyCells = [];
    tttBoard.forEach((cell, idx) => {
        if (cell === '') emptyCells.push(idx);
    });

    if (emptyCells.length === 0) return;

    let randomIndex = emptyCells[Math.floor(Math.random() * emptyCells.length)];
    tttBoard[randomIndex] = 'O';

    if (tg?.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('medium');
    }

    renderTttBoard();

    if (checkTttWinOrDraw()) return;

    tttCurrentPlayer = 'X';
    updateTttStatus();
}

function renderTttBoard() {
    const cells = document.querySelectorAll('.ttt-cell');
    cells.forEach((cell, index) => {
        cell.textContent = tttBoard[index];
        cell.style.color = tttBoard[index] === 'X' ? '#ec4899' : '#8b5cf6';
    });
}

function checkTttWinOrDraw() {
    let roundWon = false;

    for (let i = 0; i < winningCombinations.length; i++) {
        const [a, b, c] = winningCombinations[i];
        if (tttBoard[a] && tttBoard[a] === tttBoard[b] && tttBoard[a] === tttBoard[c]) {
            roundWon = true;
            break;
        }
    }

    const statusText = document.getElementById('ttt-status');

    if (roundWon) {
        if (tttMode === 'solo') {
            statusText.textContent = tttCurrentPlayer === 'X' ? 'Вы победили! 🎉' : 'Бот победил! 🤖';
        } else {
            statusText.textContent = `Победил игрок ${tttCurrentPlayer} 🎉`;
        }
        tttIsActive = false;
        if (tg?.HapticFeedback) {
            tg.HapticFeedback.notificationOccurred('success');
        }
        return true;
    }

    if (!tttBoard.includes('')) {
        statusText.textContent = `Ничья! 🤝`;
        tttIsActive = false;
        return true;
    }

    return false;
}

function updateTttStatus() {
    const statusText = document.getElementById('ttt-status');
    if (!statusText) return;

    if (tttMode === 'solo') {
        statusText.textContent = tttCurrentPlayer === 'X' ? 'Ваш ход (Х)' : 'Бот думает... (О)';
    } else {
        statusText.textContent = `Ходит: ${tttCurrentPlayer} (${tttCurrentPlayer === 'X' ? 'Крестики' : 'Нолики'})`;
    }
}

function resetTtt() {
    tttBoard = ['', '', '', '', '', '', '', '', ''];
    tttCurrentPlayer = 'X';
    tttIsActive = true;
    updateTttStatus();
    renderTttBoard();
}

// Управление модальным окном дуэли
function openChallengeModal() {
    const modal = document.getElementById('challenge-modal');
    if (modal) modal.style.display = 'flex';
}

function closeChallengeModal() {
    const modal = document.getElementById('challenge-modal');
    if (modal) modal.style.display = 'none';
}

// Отправка вызова через Telegram WebApp (через inline-запрос в чат)
function shareChallengeLink() {
    const gameSelect = document.getElementById('challenge-game-select');
    const gameType = gameSelect ? gameSelect.value : 'ttt';
    
    // Берем реальный ID пользователя из Telegram, а если его нет — заглушку
    const userId = tg?.initDataUnsafe?.user?.id || '0';
    const query = `challenge_${gameType}_${userId}`;
    
    if (tg?.switchInlineQuery) {
        // Передаем параметры без ограничений по типу чатов
        tg.switchInlineQuery(query);
    } else {
        alert('Функция доступна только внутри Telegram!');
    }
    closeChallengeModal();
}