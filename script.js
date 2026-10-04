const tg = window.Telegram?.WebApp;

let userData = {
    currency: 0,
    inventory: [],
    catalog: [],
    equipped: [],
    registry: [],
    leaderboard: [],
    foodCatalog: [],
    petCatalog: [],
    pet: null,
    user: null,
    chat: null,
    chatProfile: null,
    selectedRecipient: null,
    rp: 0,
    convertibleRp: 0,
    maxRp: 0
};

let currentPetId = 'barsichela';
let chatContext = { chatId: null, userId: null };

let tttMode = 'solo';
let tttBoard = Array(9).fill(null);
let tttCurrent = 'X';
let tttGameOver = false;
let mySymbol = null;
let socket = null;
let currentRoomId = null;


function initTelegramUser() {
    if (!tg) {
        chatContext = resolveChatContext();
        console.warn('Telegram WebApp не обнаружен');
        return;
    }

    tg.ready();
    tg.expand();
    chatContext = resolveChatContext();

    const user = tg.initDataUnsafe?.user;

    if (!user) {
        console.warn('Данные пользователя не получены');
        return;
    }

    const usernameElement = document.getElementById('username');
    const avatarElement = document.getElementById('user-avatar');
    const avatarFallback = document.getElementById('avatar-fallback');

    if (usernameElement) {
        usernameElement.textContent =
            user.first_name || 'Пользователь';
    }

    if (avatarElement && user.photo_url) {
        avatarElement.src = user.photo_url;
        avatarElement.classList.add('is-visible');
        if (avatarFallback) avatarFallback.hidden = true;

        avatarElement.onerror = () => {
            console.warn('Не удалось загрузить аватарку');
            avatarElement.classList.remove('is-visible');
            if (avatarFallback) {
                avatarFallback.hidden = false;
                avatarFallback.textContent = user.first_name?.slice(0, 1) || '🐾';
            }
        };
    } else if (avatarFallback && user.first_name) {
        avatarFallback.textContent = user.first_name.slice(0, 1);
    }
}


function resolveChatContext() {
    const params = new URLSearchParams(window.location.search);
    let chatId = params.get('chat_id');
    let launchUserId = params.get('user_id');
    const startParam = tg?.initDataUnsafe?.start_param || '';
    const match = startParam.match(/^profile_(-?\d+)_(-?\d+)$/);

    if (match) {
        chatId ||= match[1];
        launchUserId ||= match[2];
    }

    const telegramUserId = tg?.initDataUnsafe?.user?.id;
    return {
        chatId,
        userId: telegramUserId ? String(telegramUserId) : launchUserId
    };
}


const API_REQUEST_TIMEOUT_MS = 120000;
const PING_REQUEST_TIMEOUT_MS = 4500;
const PING_RETRY_INTERVAL_MS = 5000;

async function fetchWithTimeout(url, options = {}, timeoutMs = API_REQUEST_TIMEOUT_MS) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

    try {
        return await fetch(url, {
            ...options,
            signal: controller.signal
        });
    } finally {
        window.clearTimeout(timeoutId);
    }
}

function showRenderWakeupLoader() {
    let loader = document.getElementById('renderWakeupLoader');

    if (loader) {
        loader.hidden = false;
        return;
    }

    const style = document.createElement('style');
    style.id = 'renderWakeupLoaderStyle';
    style.textContent = `
        #renderWakeupLoader {
            position: fixed;
            inset: 0;
            z-index: 99999;
            display: grid;
            place-items: center;
            padding: 28px;
            background: linear-gradient(145deg, #fff7fb, #f2eaff);
            color: #382447;
            text-align: center;
            font-family: system-ui, sans-serif;
        }
        #renderWakeupLoader[hidden] { display: none; }
        #renderWakeupLoader .render-wakeup-card {
            width: min(100%, 360px);
            padding: 32px 24px;
            border: 1px solid rgba(132, 76, 156, .14);
            border-radius: 24px;
            background: rgba(255, 255, 255, .92);
            box-shadow: 0 18px 60px rgba(82, 43, 103, .14);
        }
        #renderWakeupLoader .render-wakeup-paw {
            margin-bottom: 14px;
            font-size: 48px;
            animation: render-wakeup-bounce 1.2s ease-in-out infinite;
        }
        #renderWakeupLoader .render-wakeup-spinner {
            width: 34px;
            height: 34px;
            margin: 20px auto 0;
            border: 4px solid #ead9f2;
            border-top-color: #a34ec4;
            border-radius: 50%;
            animation: render-wakeup-spin .8s linear infinite;
        }
        #renderWakeupLoader p { margin: 0; line-height: 1.55; }
        @keyframes render-wakeup-spin { to { transform: rotate(360deg); } }
        @keyframes render-wakeup-bounce { 50% { transform: translateY(-6px); } }
    `;
    document.head.appendChild(style);

    loader = document.createElement('div');
    loader.id = 'renderWakeupLoader';
    loader.hidden = true;
    loader.setAttribute('role', 'status');
    loader.setAttribute('aria-live', 'polite');

    const card = document.createElement('div');
    card.className = 'render-wakeup-card';

    const paw = document.createElement('div');
    paw.className = 'render-wakeup-paw';
    paw.setAttribute('aria-hidden', 'true');
    paw.textContent = '🐾';

    const message = document.createElement('p');
    message.textContent =
        'Синхронизация с питомцем... Наш сервер на Render просыпается, это может занять около минуты. Пожалуйста, не закрывайте приложение 🐾';

    const spinner = document.createElement('div');
    spinner.className = 'render-wakeup-spinner';
    spinner.setAttribute('aria-hidden', 'true');

    card.append(paw, message, spinner);
    loader.appendChild(card);
    document.body.appendChild(loader);
    loader.hidden = false;
}

function hideRenderWakeupLoader() {
    const loader = document.getElementById('renderWakeupLoader');
    if (loader) loader.hidden = true;
}

function delay(milliseconds) {
    return new Promise(resolve => window.setTimeout(resolve, milliseconds));
}

async function waitForServerWakeup() {
    while (true) {
        const attemptStartedAt = Date.now();
        const showLoaderTimer = window.setTimeout(showRenderWakeupLoader, 1200);
        let serverIsReady = false;

        try {
            const response = await fetchWithTimeout(
                `/api/ping?ts=${Date.now()}`,
                { cache: 'no-store' },
                PING_REQUEST_TIMEOUT_MS
            );
            const data = await response.json().catch(() => ({}));
            serverIsReady = response.ok && data.status === 'ok';
        } catch (error) {
            console.info('Render ещё не готов; повторная проверка будет через несколько секунд.');
        } finally {
            window.clearTimeout(showLoaderTimer);
        }

        if (serverIsReady) {
            hideRenderWakeupLoader();
            return;
        }

        showRenderWakeupLoader();
        const elapsed = Date.now() - attemptStartedAt;
        await delay(Math.max(0, PING_RETRY_INTERVAL_MS - elapsed));
    }
}

async function fetchUserData() {
    try {
        if (!chatContext.chatId || !chatContext.userId) {
            showProfileFeedback('Открой профиль через кнопку бота в нужном чате.', 'error');
            renderChatRegistry();
            return;
        }

        const headers = {
            'X-Telegram-Init-Data': tg?.initData || ''
        };
        const response = await fetchWithTimeout(
            `/api/chat/profile?chat_id=${encodeURIComponent(chatContext.chatId)}`,
            { headers },
            API_REQUEST_TIMEOUT_MS
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        applyChatProfile(data);
        userData.inventory = data.inventory || [];
        userData.catalog = data.catalog || [];
        userData.equipped = data.equipped || [];
        userData.foodCatalog = data.food_catalog || [];
        userData.petCatalog = data.pet_catalog || [];
        userData.pet = normalizePetData(data.pet || data.profile?.pet);
        currentPetId = userData.pet?.id || 'barsichela';
        await fetchLeaderboard();
        renderProfile();

        updatePetView();
        renderShop();
        renderInventory();
        renderChatRegistry();

    } catch (error) {
        console.error(
            'Не удалось загрузить данные профиля:',
            error
        );
        showProfileFeedback('Не удалось загрузить профиль чата. Повтори попытку позже.', 'error');
        renderChatRegistry();
    }
}


function applyChatProfile(data) {
    const profile = data.profile || data;
    userData.chatProfile = profile;
    userData.chat = data.chat || null;
    userData.user = data.user || profile.user || null;
    userData.registry = Array.isArray(data.members)
        ? data.members
        : Array.isArray(data.participants)
            ? data.participants
            : [];
    userData.currency = Number(profile.balance_r ?? data.balance_r ?? 0);
    userData.rp = Number(profile.relationship_rp ?? data.relationship_rp ?? 0);
    userData.convertibleRp = Number(profile.convertible_rp ?? data.convertible_rp ?? 0);
}


async function fetchLeaderboard() {
    if (!chatContext.chatId) {
        userData.leaderboard = [];
        renderLeaderboard();
        return;
    }

    try {
        const response = await fetchWithTimeout(
            `/api/chat/leaderboard?chat_id=${encodeURIComponent(chatContext.chatId)}`,
            {
                headers: {
                    'X-Telegram-Init-Data': tg?.initData || ''
                }
            },
            API_REQUEST_TIMEOUT_MS
        );
        const data = await response.json().catch(() => []);
        if (!response.ok) {
            throw new Error(Array.isArray(data) ? `HTTP ${response.status}` : data.error || `HTTP ${response.status}`);
        }
        userData.leaderboard = Array.isArray(data) ? data : [];
    } catch (error) {
        console.error('Не удалось загрузить лидерборд:', error);
        userData.leaderboard = [];
    }
    renderLeaderboard();
}


function renderProfile() {
    const currentUser = userData.user || {};
    const profile = userData.chatProfile || {};
    const name = currentUser.display_name || currentUser.first_name || currentUser.username || 'Пользователь';
    const headerName = document.getElementById('username');
    const profileName = document.getElementById('profile-username');
    const chatTitle = document.getElementById('profile-chat-title');
    const status = document.getElementById('profile-status');
    const balance = document.getElementById('user-balance');

    if (headerName) headerName.textContent = name;
    if (profileName) profileName.textContent = name;
    if (chatTitle) chatTitle.textContent = userData.chat?.title || 'Участники и экономика чата';
    if (status) {
        status.textContent = profile.status || 'активен';
        status.classList.toggle('is-offended', profile.status === 'обижен');
    }
    if (balance) balance.textContent = userData.currency;

    const currency = document.getElementById('profile-currency');
    const relationshipRp = document.getElementById('profile-rp');
    const convertibleRp = document.getElementById('profile-convertible-rp');
    if (currency) currency.textContent = userData.currency;
    if (relationshipRp) relationshipRp.textContent = userData.rp;
    if (convertibleRp) convertibleRp.textContent = userData.convertibleRp;

    renderProfilePet(userData.pet);
    updateConvertPreview();
}


function renderProfilePet(pet) {
    if (!pet) return;

    const petName = document.getElementById('profile-pet-name');
    const petLevel = document.getElementById('profile-pet-level');
    const petImage = document.getElementById('profile-pet-image');
    if (petName) petName.textContent = pet.name || pet.pet_name || 'Питомец';
    if (petLevel) petLevel.textContent = pet.level ?? 1;

    if (petImage && pet.image) {
        const image = document.createElement('img');
        image.src = pet.image;
        image.alt = '';
        image.onerror = () => {
            petImage.textContent = '🐾';
        };
        petImage.replaceChildren(image);
    }

    const stats = [
        ['health', 'Здоровье'],
        ['hunger', 'Сытость'],
        ['happiness', 'Счастье'],
        ['energy', 'Энергия']
    ];
    stats.forEach(([key]) => {
        const value = Math.max(0, Math.min(100, Number(pet[key] ?? 100)));
        const valueEl = document.getElementById(`profile-pet-${key}-value`);
        const bar = document.getElementById(`profile-pet-${key}-bar`);
        if (valueEl) valueEl.textContent = `${value} / 100`;
        if (bar) {
            bar.style.width = `${value}%`;
            bar.parentElement.setAttribute('aria-valuenow', String(value));
        }
    });
}


function showProfileFeedback(message, kind = '') {
    const feedback = document.getElementById('profile-feedback');
    if (!feedback) return;
    feedback.textContent = message;
    feedback.classList.toggle('is-error', kind === 'error');
    feedback.classList.toggle('is-success', kind === 'success');
}


function updateConvertPreview() {
    const input = document.getElementById('convert-rp-amount');
    const preview = document.getElementById('convert-preview');
    const button = document.getElementById('convert-rp-button');
    if (!input || !preview || !button) return;

    const amount = Number(input.value);
    const valid = Number.isInteger(amount) && amount >= 100 && amount % 100 === 0 && amount <= userData.convertibleRp;
    preview.textContent = Number.isInteger(amount) && amount > 0
        ? `Будет начислено ${Math.floor(amount / 100) * 10} R$`
        : 'Укажи сумму от 100 RP';
    button.disabled = !valid;
}


async function postChatAction(path, payload) {
    const response = await fetch(path, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Telegram-Init-Data': tg?.initData || ''
        },
        body: JSON.stringify({ ...payload, chat_id: chatContext.chatId })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
}


async function convertRp() {
    const amount = Number(document.getElementById('convert-rp-amount')?.value);
    if (!Number.isInteger(amount) || amount < 100 || amount % 100 !== 0 || amount > userData.convertibleRp) {
        showProfileFeedback('Проверь сумму RP для обмена.', 'error');
        return;
    }

    const button = document.getElementById('convert-rp-button');
    if (button) button.disabled = true;
    try {
        await postChatAction('/api/chat/convert', { rp_amount: amount });
        await fetchUserData();
        showProfileFeedback(`Обмен завершён: ${amount} RP → ${amount / 10} R$.`, 'success');
        tg?.HapticFeedback?.notificationOccurred('success');
    } catch (error) {
        showProfileFeedback(error.message || 'Не удалось выполнить обмен.', 'error');
    } finally {
        updateConvertPreview();
    }
}


function openGiftModal(member) {
    if (!member || member.user_id == null) return;
    userData.selectedRecipient = member;

    const title = document.getElementById('gift-recipient-name');
    const note = document.getElementById('gift-balance-note');
    const amount = document.getElementById('gift-amount');
    const feedback = document.getElementById('gift-feedback');
    const modal = document.getElementById('giftModal');
    if (!title || !note || !amount || !modal) return;

    title.textContent = member.display_name || member.username || 'Участник';
    note.textContent = `Доступно: ${userData.currency} R$`;
    amount.max = String(userData.currency);
    amount.value = '';
    if (feedback) feedback.textContent = '';
    modal.style.display = 'flex';
    amount.focus();
}


function closeGiftModal() {
    const modal = document.getElementById('giftModal');
    if (modal) modal.style.display = 'none';
    userData.selectedRecipient = null;
}


async function sendGift() {
    const recipient = userData.selectedRecipient;
    const amount = Number(document.getElementById('gift-amount')?.value);
    const feedback = document.getElementById('gift-feedback');
    const button = document.getElementById('gift-submit');
    if (!recipient || !Number.isInteger(amount) || amount <= 0 || amount > userData.currency) {
        if (feedback) feedback.textContent = 'Укажи целую сумму в пределах баланса.';
        return;
    }

    if (button) button.disabled = true;
    try {
        await postChatAction('/api/chat/gift', {
            recipient_user_id: recipient.user_id,
            amount
        });
        closeGiftModal();
        await fetchUserData();
        showProfileFeedback(`Подарок отправлен: ${amount} R$.`, 'success');
        tg?.HapticFeedback?.notificationOccurred('success');
    } catch (error) {
        if (feedback) feedback.textContent = error.message || 'Не удалось отправить подарок.';
    } finally {
        if (button) button.disabled = false;
    }
}


function normalizePetData(pet) {
    if (!pet) return null;

    const id = pet.id || pet.pet_id || 'barsichela';
    const definition = userData.petCatalog.find(item => item.id === id) || {};
    return {
        ...definition,
        ...pet,
        id,
        name: pet.name || pet.pet_name || definition.name || 'Питомец',
        image: pet.image || definition.image || '/Barsichela.png',
        level: pet.level ?? 1,
        max_level: pet.max_level || 10
    };
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
    const container = document.getElementById('profileUsersList');
    const count = document.getElementById('members-count');
    if (!container) return;

    const members = (Array.isArray(userData.registry) ? userData.registry : []).filter(member =>
        String(member.user_id ?? member.id) !== String(chatContext.userId)
    );
    if (count) count.textContent = members.length;

    if (members.length === 0) {
        container.innerHTML = '<p class="list-state">Другие участники пока не активировали бота в этом чате.</p>';
        return;
    }

    const fragment = document.createDocumentFragment();
    members.forEach(member => {
        const userId = member.user_id ?? member.id;
        const name = member.display_name || member.username || `Игрок ${userId}`;
        const balance = Number(member.balance_r ?? member.currency ?? 0);
        const rp = Number(member.relationship_rp ?? member.rp ?? 0);
        const button = document.createElement('button');
        button.className = 'profile-member-row';
        button.type = 'button';
        button.disabled = userId == null;

        const avatar = document.createElement('span');
        avatar.className = 'member-avatar';
        avatar.setAttribute('aria-hidden', 'true');
        avatar.textContent = name.slice(0, 1).toUpperCase();

        const details = document.createElement('span');
        details.className = 'member-details';
        const displayName = document.createElement('strong');
        displayName.textContent = name;
        const stats = document.createElement('small');
        stats.textContent = `${rp} RP · ${balance} R$`;
        details.append(displayName, stats);

        const giftIcon = document.createElement('span');
        giftIcon.className = 'member-gift-icon';
        giftIcon.setAttribute('aria-hidden', 'true');
        giftIcon.textContent = '＋';

        button.append(avatar, details, giftIcon);
        button.addEventListener('click', () => openGiftModal(member));
        fragment.appendChild(button);
    });
    container.replaceChildren(fragment);
}


function renderLeaderboard() {
    const container = document.getElementById('leaderboardList');
    if (!container) return;

    const leaderboard = Array.isArray(userData.leaderboard)
        ? userData.leaderboard
        : [];
    if (leaderboard.length === 0) {
        const empty = document.createElement('p');
        empty.className = 'leaderboard-empty';
        empty.textContent = 'В этом чате пока нет участников рейтинга.';
        container.replaceChildren(empty);
        return;
    }

    const fragment = document.createDocumentFragment();
    leaderboard.forEach((member, index) => {
        const row = document.createElement('article');
        row.className = 'leaderboard-row';

        const rank = document.createElement('span');
        rank.className = 'leaderboard-rank';
        rank.textContent = String(index + 1);

        const user = document.createElement('div');
        user.className = 'leaderboard-user';
        const name = document.createElement('h4');
        name.textContent = member.display_name
            || (member.username ? `@${member.username}` : `Игрок ${member.user_id || ''}`);
        const stats = document.createElement('p');
        stats.textContent = `${Number(member.convertible_rp || 0)} RP · ${Number(member.balance_r || 0)} R$`;

        const points = document.createElement('strong');
        points.className = 'leaderboard-total';
        points.textContent = `${Number(member.convertible_rp || 0)} RP`;

        user.append(name, stats);
        row.append(rank, user, points);
        fragment.appendChild(row);
    });
    container.replaceChildren(fragment);
}


function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = value ?? '';
    return div.innerHTML;
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

    userData.petCatalog.forEach(pet => {
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
                src="${escapeHtml(pet.image)}"
                alt="${escapeHtml(pet.name)}"
                class="pet-choice-img"
            >

            <div class="pet-choice-name">
                ${escapeHtml(pet.name)}
            </div>
        `;

        card.onclick = async () => {
            try {
                const response = await fetch('/api/me', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Telegram-Init-Data': tg?.initData || ''
                    },
                    body: JSON.stringify({ pet_id: pet.id })
                });
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Pet selection failed');
                }

                userData.pet = normalizePetData(data.pet);
                currentPetId = userData.pet.id;
                updatePetView();
                closePetSelector();

                if (tg?.HapticFeedback) {
                    tg.HapticFeedback.notificationOccurred('success');
                }
            } catch (error) {
                console.error('Не удалось сохранить питомца:', error);
                tg?.showAlert?.('Не удалось выбрать питомца. Попробуй ещё раз.');
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
        userData.petCatalog.find(
            pet => pet.id === currentPetId
        ) || userData.petCatalog[0] || userData.pet || {
            name: 'Питомец',
            image: '/Barsichela.png'
        };
    const maxLevel = Math.max(1, Number(userData.pet?.max_level || 10));
    const level = Math.max(1, Number(userData.pet?.level || 1));
    const health = Math.max(0, Math.min(100, Number(userData.pet?.health ?? 100)));
    const hunger = Math.max(0, Math.min(100, Number(userData.pet?.hunger ?? 100)));
    const happiness = Math.max(0, Math.min(100, Number(userData.pet?.happiness ?? 100)));
    const energy = Math.max(0, Math.min(100, Number(userData.pet?.energy ?? 100)));

    const petName = document.getElementById('pet-name');
    if (petName) petName.textContent = userData.pet?.name || activePet.name;

    const statValues = {
        'pet-level-value': `${level} / ${maxLevel}`,
        'pet-health-value': `${health} / 100`,
        'pet-hunger-value': `${hunger} / 100`,
        'pet-happiness-value': `${happiness} / 100`,
        'pet-energy-value': `${energy} / 100`
    };
    const statProgress = {
        'pet-level-bar': { value: level, max: maxLevel, width: Math.min(level / maxLevel * 100, 100) },
        'pet-health-bar': { value: health, max: 100, width: health },
        'pet-hunger-bar': { value: hunger, max: 100, width: hunger },
        'pet-happiness-bar': { value: happiness, max: 100, width: happiness },
        'pet-energy-bar': { value: energy, max: 100, width: energy }
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
            src="${escapeHtml(userData.pet?.image || activePet.image)}"
            alt="${escapeHtml(userData.pet?.name || activePet.name)}"
            class="active-pet-image"
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

    petDisplay.querySelectorAll('img').forEach(image => {
        image.onerror = () => image.replaceWith(document.createTextNode('🐾'));
    });
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
                userData.pet = normalizePetData(data.pet);
                const balance = document.getElementById('user-balance');
                if (balance) balance.textContent = userData.currency;
                const profileCurrency = document.getElementById('profile-currency');
                if (profileCurrency) profileCurrency.textContent = userData.currency;
                renderShop();
                renderInventory();
                updatePetView();
            } catch (error) {
                console.error('Ошибка при покупке еды:', error);
            }
        });

        grid.appendChild(card);
    });
}


function renderInventory() {
    const grid = document.getElementById('inventoryGrid');
    if (!grid) return;

    const ownedFood = userData.foodCatalog
        .filter(food => food.count > 0)
        .map(food => ({
            icon: food.name.split(' ')[0],
            name: food.name.replace(/^\S+\s*/, ''),
            status: `×${food.count}`,
            equipped: false
        }));
    const ownedItems = userData.inventory.map(item => ({
        icon: item.name.split(' ')[0],
        name: item.name.replace(/^\S+\s*/, ''),
        status: item.equipped ? 'Надето' : 'В коллекции',
        equipped: item.equipped
    }));
    const inventoryItems = [...ownedItems, ...ownedFood];

    if (inventoryItems.length === 0) {
        grid.innerHTML = '<p class="inventory-empty">Пока нет предметов</p>';
        return;
    }

    grid.innerHTML = inventoryItems.map(item => `
        <article class="inventory-item">
            <span class="inventory-item-icon">${escapeHtml(item.icon)}</span>
            <span class="inventory-item-name">${escapeHtml(item.name)}</span>
            <strong class="inventory-item-count ${item.equipped ? 'is-equipped' : ''}">${escapeHtml(item.status)}</strong>
        </article>
    `).join('');
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

            if (data.type === 'error') {
                tttGameOver = true;
                if (statusEl) {
                    statusEl.textContent = data.message || 'Не удалось подключиться к дуэли.';
                }
                updateTttUI();
                return;
            }

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

        userData.pet = normalizePetData(data.pet);
        userData.foodCatalog = userData.foodCatalog.map(food => ({
            ...food,
            count: data.pet.inventory?.[food.id] || 0
        }));
        renderFeedItems();
        renderShop();
        renderInventory();
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

        document.getElementById('convert-rp-amount')
            ?.addEventListener('input', updateConvertPreview);
        updateConvertPreview();
        checkDuelParams();

        void (async () => {
            await waitForServerWakeup();
            await fetchUserData();
        })();
    }
);