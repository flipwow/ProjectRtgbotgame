// === ВСТАВИТЬ СТРОГО НА ПЕРВУЮ СТРОКУ SCRIPT.JS ===
(() => {
    const originalFetch = window.fetch.bind(window);

    window.fetch = function(input, init) {
        if (typeof input === 'string' && input.startsWith('/api/')) {
            input = apiUrl(input);
        }
        return originalFetch(input, init);
    };
})();
// ===================================================
const tg = window.Telegram?.WebApp;

let userData = {
    currency: 0,
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

let selectedLeaderboardMode = 'online';
let currentPetId = 'bars';
let chatContext = { chatId: null, userId: null };
let chatMembersRefreshInFlight = false;

let tttMode = 'solo';
let tttBoard = Array(9).fill(null);
let tttCurrent = 'X';
let tttGameOver = false;
let mySymbol = null;
let socket = null;
let currentRoomId = null;

const SETTINGS_KEY = 'ritushka-miniapp-settings';
const textSourceCache = new WeakMap();
let appSettings = loadAppSettings();

const englishText = {
    'Загрузка...': 'Loading...', 'Пользователь': 'User', 'Питомец': 'Pet', 'Лидеры': 'Leaders', 'Игры': 'Games', 'Еда': 'Food', 'Профиль': 'Profile',
    'Твой любимый дерзкий пушистик 💅': 'Your favorite sassy fluffball 💅', 'Переименовать питомца': 'Rename pet', 'Уровень': 'Level', 'Здоровье': 'Health', 'Голод': 'Hunger', 'Счастье': 'Happiness', 'Энергия': 'Energy',
    'Сменить питомца': 'Change pet', 'Покормить питомца': 'Feed pet', '👑 Таблица лидеров': '👑 Leaderboard', 'Очки за победы в онлайн-крестиках-ноликах': 'Points for online tic-tac-toe wins',
    '🎮 Мини-игры': '🎮 Mini-games', 'Сразись с другими пешками': 'Challenge other pawns', '❌ Крестики-нолики ⭕️': '❌ Tic-tac-toe ⭕️', 'Играй с ботом или устрой дуэль с другом': 'Play with the bot or challenge a friend',
    '🤖 Играть с ботом': '🤖 Play against the bot', '👥 Играть с другом (на одном телефоне)': '👥 Play with a friend (on one phone)', '◀️ Назад к играм': '◀️ Back to games', 'Сдаться / Назад': 'Forfeit / Back',
    'Чтобы вызвать друга на дуэль онлайн, отправь боту команду': 'To challenge a friend online, send the bot the command', '🥣 Магазин питомца': '🥣 Pet shop', 'Покупай еду за R$ и пополняй холодильник': 'Buy food with R$ and stock the fridge', 'Еда': 'Food',
    'ПРОФИЛЬ ЧАТА': 'CHAT PROFILE', 'Telegram Mini App': 'Telegram Mini App', 'Загрузка': 'Loading', 'Баланс': 'Balance', 'Отношения': 'Relationship', 'Доступно к обмену': 'Available to exchange',
    'Обмен RP на R$': 'Exchange RP for R$', 'Курс: 100 RP = 10 R$': 'Rate: 100 RP = 10 R$', 'Сумма RP': 'RP amount', 'Обменять RP на R$': 'Exchange RP for R$',
    'СООБЩЕСТВО': 'COMMUNITY', 'Участники чата': 'Chat members', '⚙️ Настройки': '⚙️ Settings', 'Настройки': 'Settings', 'Язык / Language': 'Language', 'Язык: Русский / English': 'Language: Russian / English',
    'Тема': 'Theme', 'Исходная': 'Original', 'Светлая': 'Light', 'Тёмная': 'Dark', '📖 Правила': '📖 Rules', 'Правила': 'Rules', 'Готово': 'Done',
    'Основные команды бота': 'Main bot commands', '/start</code> — запустить бота и открыть приложение.': '/start</code> — start the bot and open the app.',
    '/duel</code> — создать онлайн-дуэль в крестики-нолики и отправить вызов в чат.': '/duel</code> — create an online tic-tac-toe duel and post the challenge in chat.',
    '/menu</code> — открыть меню; <code>/balance</code> — проверить баланс; <code>/pet</code> — посмотреть питомца.': '/menu</code> — open the menu; <code>/balance</code> — check your balance; <code>/pet</code> — view your pet.',
    'В онлайн-дуэли ходи только в свой ход. Победитель получает 30–60 RP, ничья не награждается.': 'In an online duel, make a move only on your turn. The winner receives 30–60 RP; a draw has no reward.',
    'Заботься о питомце, покупай еду за R$ и используй RP для обмена на валюту.': 'Take care of your pet, buy food with R$, and exchange RP for currency.', 'Играйте честно и уважайте других участников чата.': 'Play fair and respect other chat members.',
    'Другие участники пока не активировали бота в этом чате.': 'Other members have not activated the bot in this chat yet.', 'В этом чате пока нет участников рейтинга.': 'There are no ranked players in this chat yet.',
    'Очки за победы': 'win points', 'Подарить R$': 'Gift R$', 'Посмотреть питомца': 'View pet', 'Профиль чата': 'Chat profile', 'Участники и экономика чата': 'Chat members and economy',
    'Обмен завершён': 'Exchange complete', 'Подарок отправлен': 'Gift sent', 'Имя питомца изменено.': 'Pet name updated.', 'Новое имя': 'New name', 'Имя питомца': 'Pet name', 'Отмена': 'Cancel', 'Сохранить': 'Save',
    'Выбор питомца': 'Choose a pet', 'Покормить Барсичелу': 'Feed Barsichela', 'Выбери лакомство из инвентаря:': 'Choose a treat from your inventory:', 'Холодильник пока пуст 🛍': 'The fridge is empty 🛍',
    'Холодильник пуст. Загляни в магазин еды 🛍': 'The fridge is empty. Visit the food shop 🛍', 'Накормить': 'Feed', 'Магазин еды пока пуст': 'The food shop is empty', 'В холодильнике:': 'In fridge:', 'Купить ·': 'Buy ·',
    'Режимы': 'Modes', 'Ходит: X': 'Turn: X', 'Победа:': 'Winner:', 'Ничья! 🤝': 'Draw! 🤝', 'Ожидание соперника...': 'Waiting for opponent...', 'Твой ход!': 'Your turn!', 'Победил': 'Winner', 'Ты победил! 🎉': 'You won! 🎉', 'Награда:': 'Reward:', 'R$.': 'RP.', 'Твой ход': 'Your turn',
    'Твой любимый дерзкий пушистик': 'Your favorite sassy fluffball', 'Питомец участника': 'MEMBER PET', 'Участник': 'Member', 'Участники пока не активировали бота': 'Members have not activated the bot yet',
    'Доступно:': 'Available:', 'Сумма перевода': 'Transfer amount', 'Например, 25': 'For example, 25', 'Отправить подарок': 'Send gift', 'Перевод R$': 'Transfer R$', 'Закрыть': 'Close',
    'Ракурс': 'View', 'Назад': 'Back', 'Уровень питомца': 'Pet level', 'Синхронизация с питомцем... Наш сервер на Render просыпается, это может занять около минуты. Пожалуйста, не закрывайте приложение 🐾': 'Syncing with your pet... The server is waking up and may take about a minute. Please keep the app open 🐾',
    'Барсичела': 'Barsichela', 'RITUSHKA PET': 'RITUSHKA PET', 'Переименовать питомца': 'Rename pet', 'Имя питомца': 'Pet name', 'Новое имя': 'New name', 'Отмена': 'Cancel', 'Сохранить': 'Save',
    'Сменить питомца': 'Change pet', 'Покормить питомца': 'Feed pet', 'Сытость': 'Satiety', 'Выбери лакомство из инвентаря:': 'Choose a treat from your inventory:',
    'Очки за победы в онлайн-крестиках-ноликах': 'Points for online tic-tac-toe wins', 'Сразись с другими пешками': 'Challenge other players', 'Играй с ботом или устрой дуэль с другом': 'Play the bot or challenge a friend',
    'Играть с другом (на одном телефоне)': 'Play with a friend (on one phone)', 'Назад к играм': 'Back to games', 'Сдаться / Назад': 'Forfeit / Back', 'Магазин питомца': 'Pet shop',
    'Покупай еду за R$ и пополняй холодильник': 'Buy food with R$ and stock the fridge', 'ПРОФИЛЬ ЧАТА': 'CHAT PROFILE', 'Загрузка участников...': 'Loading members...',
    'Курс: 100 RP = 10 R$': 'Rate: 100 RP = 10 R$', 'Сумма RP': 'RP amount', 'Участники чата': 'Chat members',
    'Другие участники пока не активировали бота в этом чате.': 'Other members have not activated the bot in this chat yet.', 'В этом чате пока нет участников рейтинга.': 'There are no ranked members in this chat yet.',
    'Недостаточно R$ для покупки.': 'Not enough R$ to buy this.', 'Магазин еды пока пуст': 'The food shop is empty', 'Холодильник пока пуст': 'The fridge is empty',
    'Покормить Барсичелу': 'Feed Barsichela', 'Отправить подарок': 'Send gift', 'Сумма перевода': 'Transfer amount', 'Ожидание соперника...': 'Waiting for opponent...',
    'Ходит: X (Крестики)': 'Turn: X (Crosses)', 'Язык / Language': 'Language', 'Русский': 'Russian', 'Исходная': 'Original', 'Светлая': 'Light', 'Тёмная': 'Dark',
    'Основные команды бота': 'Main bot commands', ' — запустить бота и открыть приложение.': ' — start the bot and open the app.',
    ' — создать онлайн-дуэль в крестики-нолики и отправить вызов в чат.': ' — create an online tic-tac-toe duel and send a challenge to the chat.',
    ' — открыть профиль чата; ': ' — open the chat profile; ', ' — проверить баланс; ': ' — check your balance; ', ' — посмотреть питомца.': ' — view your pet.',
    'В онлайн-дуэли ходи только в свой ход. Победитель получает 30–60 RP, ничья не награждается.': 'In an online duel, make a move only on your turn. The winner receives 30–60 RP; draws have no reward.',
    'Заботься о питомце, покупай еду за R$ и используй RP для обмена на валюту.': 'Care for your pet, buy food with R$, and exchange RP for currency.',
    'Играйте честно и уважайте других участников чата.': 'Play fair and respect other chat members.'
  };

Object.assign(englishText, {
    'Общий рейтинг и очки по игровым режимам': 'Overall ranking and points by game mode',
    'Общий рейтинг · за всё время': 'Overall ranking · all time',
    'Очки по режимам': 'Points by mode',
    'Режим игры': 'Game mode',
    'Онлайн-дуэли': 'Online duels',
    'С ботом': 'Against the bot',
    'На одном телефоне': 'Local two-player',
    'Суммарные очки во всех игровых режимах': 'Total points across all game modes',
    'Пока нет набранных очков.': 'No points have been earned yet.',
    'В этом режиме пока нет набранных очков.': 'No points have been earned in this mode yet.'
});

function loadAppSettings() {
    try {
        const saved = JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}');
        return {
            language: saved.language === 'en' ? 'en' : 'ru',
            theme: ['current', 'light', 'dark'].includes(saved.theme) ? saved.theme : 'current'
        };
    } catch {
        return { language: 'ru', theme: 'current' };
    }
}

function translateSource(source) {
    if (appSettings.language !== 'en') return source;
    const clean = source.trim();
    let result = englishText[clean];
    if (!result) {
        const patterns = [
            [/^Очки: (\d+)$/, 'Points: $1'],
            [/^(\d+) очк\.$/, '$1 pts.'],
            [/^Будет начислено (\d+) R\$$/, 'You will receive $1 R$'],
            [/^Обмен завершён: (\d+) RP → (\d+) R\$$/, 'Exchange complete: $1 RP → $2 R$'],
            [/^Подарок отправлен: (\d+) R\$$/, 'Gift sent: $1 R$'],
                        [/^Награда: (\d+) RP\.$/, 'Reward: $1 RP.'],
            [/^Ты победил! 🎉 Награда: (\d+) RP\.$/, 'You won! 🎉 Reward: $1 RP.'],
            [/^Ты играешь за ([XO])\. Ожидание соперника\.\.\.$/, 'You are playing as $1. Waiting for opponent...'],
            [/^Ты: ([XO]) \| Твой ход!$/, 'You: $1 | Your turn!'],
            [/^Ты: ([XO]) \| Ход соперника \(([XO])\)$/, "You: $1 | Opponent's turn ($2)"],
            [/^Ты: ([XO]) \| Ходит: ([XO])$/, 'You: $1 | Turn: $2'],
            [/^Ты: ([XO]) \| (.+)$/, 'You: $1 | $2'],
            [/^Ход соперника \(([XO])\)$/, "Opponent's turn ($1)"],
            [/^Победил ([XO])$/, 'Player $1 won'],
            [/^Победа: ([XO])! 🎉$/, 'Winner: $1! 🎉'],
            [/^В холодильнике: (\d+)$/, 'In fridge: $1'],
            [/^Купить · (\d+) R\$$/, 'Buy · $1 R$'],
            [/^Игрок (.+)$/, 'Player $1'],
            [/^(\d+) очков побед · (\d+) RP · (\d+) R\$$/, '$1 win points · $2 RP · $3 R$'],
            [/^(\d+) очк\.$/, '$1 pts.'],
            [/^(\d+) RP · (\d+) R\$$/, '$1 RP · $2 R$'],
            [/^Доступно: (\d+) R\$$/, 'Available: $1 R$'],
            [/^(\d+) \/ (\d+)$/, '$1 / $2']
        ];
        for (const [pattern, replacement] of patterns) {
            if (pattern.test(clean)) {
                result = clean.replace(pattern, replacement);
                break;
            }
        }
    }
    if (!result) return source;
    const leading = source.match(/^\s*/)?.[0] || '';
    const trailing = source.match(/\s*$/)?.[0] || '';
    return `${leading}${result}${trailing}`;
}

function translateNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return;
    if (!textSourceCache.has(node)) textSourceCache.set(node, node.nodeValue);
    const translated = translateSource(textSourceCache.get(node));
    if (node.nodeValue !== translated) node.nodeValue = translated;
}

function applyLanguage() {
    document.documentElement.lang = appSettings.language;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) translateNode(node);
    document.querySelectorAll('[title], [aria-label], [placeholder]').forEach(element => {
        if (!element) return;

        ['title', 'aria-label', 'placeholder'].forEach(attribute => {
            try {
                if (!element.hasAttribute(attribute)) return;

                const datasetKey = `i18n${attribute}`;
                if (!element.dataset[datasetKey]) {
                    element.dataset[datasetKey] = element.getAttribute(attribute);
                }
                element.setAttribute(
                    attribute,
                    translateSource(element.dataset[datasetKey])
                );
            } catch (error) {
                // Один некорректный атрибут не должен прерывать локализацию остальных элементов.
                console.warn(`Не удалось локализовать атрибут ${attribute}:`, error);
            }
        });
    });
}

function persistAppSettings() {
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(appSettings)); } catch (error) { console.warn('Не удалось сохранить настройки', error); }
}

function applyTheme() {
    if (appSettings.theme === 'current') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.dataset.theme = appSettings.theme;
}

function setAppLanguage(language) {
    appSettings.language = language === 'en' ? 'en' : 'ru';
    persistAppSettings();
    applyLanguage();
}

function setAppTheme(theme) {
    appSettings.theme = ['current', 'light', 'dark'].includes(theme) ? theme : 'current';
    persistAppSettings();
    applyTheme();
}

function openSettings() {
    document.getElementById('language-select').value = appSettings.language;
    document.getElementById('theme-select').value = appSettings.theme;
    document.getElementById('settingsModal').style.display = 'flex';
}

function closeSettings() {
    document.getElementById('settingsModal').style.display = 'none';
}

function openRules() {
    closeSettings();
    document.getElementById('rulesModal').style.display = 'flex';
}

function closeRules() {
    document.getElementById('rulesModal').style.display = 'none';
}

function initSettings() {
    applyTheme();
    applyLanguage();
    const observer = new MutationObserver(records => {
        records.forEach(record => {
            if (record.type === 'characterData') translateNode(record.target);
            record.addedNodes?.forEach(added => {
                if (added.nodeType === Node.TEXT_NODE) translateNode(added);
                else if (added.nodeType === Node.ELEMENT_NODE) {
                    const walker = document.createTreeWalker(added, NodeFilter.SHOW_TEXT);
                    let text;
                    while ((text = walker.nextNode())) translateNode(text);
                }
            });
        });
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });
}

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


    if (usernameElement) {
        usernameElement.textContent =
            user.first_name || 'Пользователь';
    }

            
    

    loadTelegramAvatar(user);

}


function setAvatarFallback(user = {}) {
    const avatarElement = document.getElementById('user-avatar');
    const avatarFallback = document.getElementById('avatar-fallback');
    if (avatarElement) {
        avatarElement.classList.remove('is-visible');
        avatarElement.removeAttribute('src');
        avatarElement.onload = null;
        avatarElement.onerror = null;
        const previousObjectUrl = avatarElement.dataset.objectUrl;
        if (previousObjectUrl) URL.revokeObjectURL(previousObjectUrl);
        delete avatarElement.dataset.objectUrl;
    }
    if (avatarFallback) {
        avatarFallback.hidden = false;
        avatarFallback.textContent = user.first_name?.slice(0, 1) || '🐾';
    }
}


async function loadTelegramAvatar(user = {}) {
    const avatarElement = document.getElementById('user-avatar');
    const avatarFallback = document.getElementById('avatar-fallback');
    setAvatarFallback(user);
    if (!avatarElement) return;

    const photoUrl = user.photo_url || tg?.initDataUnsafe?.user?.photo_url;
    if (photoUrl) {
        avatarElement.onload = () => {
            avatarElement.classList.add('is-visible');
            if (avatarFallback) avatarFallback.hidden = true;
        };
        avatarElement.onerror = () => setAvatarFallback(user);
        avatarElement.src = photoUrl;
        return;
    }
    if (!tg?.initData) return;

    try {
        const response = await fetchWithTimeout('/api/avatar', {
            headers: { 'X-Telegram-Init-Data': tg.initData },
            cache: 'no-store'
        }, 10000);
        if (!response.ok) throw new Error(`Avatar request failed: ${response.status}`);

        const image = await response.blob();
        if (!image.type.startsWith('image/') || image.size === 0) {
            throw new Error('Telegram returned no usable profile photo');
        }

        const objectUrl = URL.createObjectURL(image);
        avatarElement.dataset.objectUrl = objectUrl;
        avatarElement.onload = () => {
            avatarElement.classList.add('is-visible');
            const avatarFallback = document.getElementById('avatar-fallback');
            if (avatarFallback) avatarFallback.hidden = true;
        };
        avatarElement.onerror = () => setAvatarFallback(user);
        avatarElement.src = objectUrl;
    } catch (error) {
        console.info('Profile photo unavailable; showing the default avatar.', error);
        setAvatarFallback(user);
    }
}


function resolveChatContext() {
    const params = new URLSearchParams(window.location.search);
    let chatId = params.get('chat_id');
    let launchUserId = params.get('user_id');
    const startParam = tg?.initDataUnsafe?.start_param
        || params.get('start_param')
        || '';
    const profileMatch = startParam.match(/^profile_(-?\d+)_(-?\d+)$/);
    const chatMatch = startParam.match(/^chat_(-?\d+)$/);

    if (profileMatch) {
        chatId ||= profileMatch[1];
        launchUserId ||= profileMatch[2];
    } else if (chatMatch) {
        chatId ||= chatMatch[1];
    }

            const telegramUserId = tg?.initDataUnsafe?.user?.id;

    // Telegram private-chat IDs equal the user's ID; they are not group context.
    if (chatId && telegramUserId && String(chatId) === String(telegramUserId)) {
        chatId = null;
    }

    return {
        chatId,
        userId: telegramUserId ? String(telegramUserId) : launchUserId
    };
}


const API_REQUEST_TIMEOUT_MS = 30000;
const PING_REQUEST_TIMEOUT_MS = 4500;
const PING_RETRY_INTERVAL_MS = 5000;

const API_BASE_URL = (() => {
    const configuredUrl =
        window.APP_CONFIG?.apiBaseUrl
        || new URLSearchParams(window.location.search).get('api_url');

    if (configuredUrl) {
        return configuredUrl.replace(/\/+$/, '');
    }

    const isLocalHost = ['localhost', '127.0.0.1', '::1']
        .includes(window.location.hostname);

    if (isLocalHost && window.location.port === '4173') {
        const host = window.location.hostname === '::1'
            ? '[::1]'
            : window.location.hostname;
        return `${window.location.protocol}//${host}:8080`;
    }

    return '';
})();

function apiUrl(path) {
    return `${API_BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

async function fetchWithTimeout(url, options = {}, timeoutMs = API_REQUEST_TIMEOUT_MS) {
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

    try {
        return await fetch(apiUrl(url), {
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
        if (chatContext.chatId && !chatContext.userId) {
            showProfileFeedback('Открой профиль через кнопку бота в нужном чате.', 'error');
            renderChatRegistry();
            return;
        }
        showProfileFeedback('');

        const isChatProfile = Boolean(chatContext.chatId);
        const endpoint = isChatProfile
            ? `/api/chat/profile?chat_id=${encodeURIComponent(chatContext.chatId)}`
            : '/api/me';
        const headers = {
            'X-Telegram-Init-Data': tg?.initData || ''
        };
        const response = await fetchWithTimeout(
            endpoint,
            { headers },
            API_REQUEST_TIMEOUT_MS
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        userData.foodCatalog = data.food_catalog || data.catalog || [];
        userData.petCatalog = data.pet_catalog || [];
        if (isChatProfile) {
            if (data.chat?.id) chatContext.chatId = String(data.chat.id);
            applyChatProfile(data);
        } else {
            applyPersonalProfile(data);
        }

        userData.pet = normalizePetData(data.pet || data.profile?.pet);
        currentPetId = userData.pet?.id || '';

        // Если у пользователя вообще нет питомца или не задан его ID — открываем выбор 4 стартовых
        if (!userData.pet || !userData.pet.id) {
            openFirstPetSelector();
        }

        userData.leaderboard = Array.isArray(data.leaderboard) ? data.leaderboard : [];
        renderLeaderboard();
        renderProfile();

        updatePetView();
        renderShop();
        renderFoodInventory();
        renderChatRegistry();

    } catch (error) {
        console.error(
            'Не удалось загрузить данные профиля:',
            error
        );
        showProfileFeedback('Не удалось загрузить профиль чата. Повтори попытку позже.', 'error');
        renderChatRegistry();
    } finally {
        const status = document.getElementById('profile-status');
        if (status && !userData.user) status.textContent = 'Unavailable';
    }
}

async function refreshChatMembers() {
    const profileTab = document.getElementById('tab-profile');
    if (
        !chatContext.chatId
        || document.hidden
        || !profileTab?.classList.contains('active')
        || chatMembersRefreshInFlight
    ) return;

    chatMembersRefreshInFlight = true;
    try {
        const response = await fetchWithTimeout(
            `/api/chat/profile?chat_id=${encodeURIComponent(chatContext.chatId)}`,
            { headers: { 'X-Telegram-Init-Data': tg?.initData || '' } },
            10000
        );
        if (!response.ok) return;

        const data = await response.json().catch(() => ({}));
        userData.registry = Array.isArray(data.members) ? data.members : [];
        renderChatRegistry();
    } catch (error) {
        console.debug('Chat member list refresh failed.', error);
    } finally {
        chatMembersRefreshInFlight = false;
    }
}


function applyPersonalProfile(data) {
    const user = data.user || tg?.initDataUnsafe?.user || {};
    const relationshipRp = Number(data.rp ?? 0);
        const balance = Number(data.currency ?? 0);
    userData.user = {
        ...user,
        display_name: user.display_name || [user.first_name, user.last_name].filter(Boolean).join(' ')
    };
    userData.owned_pets = data.owned_pets && typeof data.owned_pets === 'object'
        ? data.owned_pets
        : {};
    userData.chat = null;
    userData.chatProfile = {
        status: 'Active',
        balance_r: balance,
        relationship_rp: relationshipRp,
        convertible_rp: 0
    };
    userData.registry = [];
    userData.currency = balance;
    userData.rp = relationshipRp;
    userData.convertibleRp = 0;
    userData.leaderboard = Array.isArray(data.leaderboard) ? data.leaderboard : [];
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
    
    // Добавьте эту строку в самый конец функции:
    userData.owned_pets = data.owned_pets && typeof data.owned_pets === 'object' ? data.owned_pets : {};
}

async function fetchLeaderboard() {
    try {
        const endpoint = chatContext.chatId
            ? `/api/chat/leaderboard?chat_id=${encodeURIComponent(chatContext.chatId)}`
            : '/api/leaderboard';
        const response = await fetchWithTimeout(
            endpoint,
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

    if (currency) currency.textContent = userData.currency;
    if (relationshipRp) relationshipRp.textContent = userData.rp;

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
        ['happiness', 'Счастье']
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

function openRenamePetModal() {
    const modal = document.getElementById('renamePetModal');
    const input = document.getElementById('rename-pet-input');
    const feedback = document.getElementById('rename-pet-feedback');
    if (!modal || !input) return;

    input.value = userData.pet?.name || '';
    if (feedback) feedback.textContent = '';
    modal.style.display = 'flex';
    input.focus();
    input.select();
}

function closeRenamePetModal() {
    const modal = document.getElementById('renamePetModal');
    if (modal) modal.style.display = 'none';
}

async function submitPetRename(event) {
    event.preventDefault();

    const input = document.getElementById('rename-pet-input');
    const feedback = document.getElementById('rename-pet-feedback');
    const button = document.getElementById('rename-pet-submit');
    const newName = input?.value.trim();

    if (!newName || newName.length > 32) {
        if (feedback) feedback.textContent = 'Имя должно содержать от 1 до 32 символов.';
        return;
    }

    // ИСПРАВЛЕНО: Используем правильный JavaScript метод String() вместо Python-метода str()
    const currentChatId = String(chatContext.chatId || "");
    const currentUserId = String(chatContext.userId || "");
    if (!currentUserId) {
        if (feedback) feedback.textContent = 'Не удалось определить пользователя.';
        return;
    }

    const currentPetId = userData.pet?.id || userData.pet?.pet_id || "";

    if (button) button.disabled = true;
    try {
        const response = await fetchWithTimeout('/api/pet/rename', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': tg?.initData || ''
            },
            body: JSON.stringify({
                user_id: currentUserId,
                chat_id: currentChatId,
                pet_id: currentPetId,
                new_name: newName
            })
        });

        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        // Локально изолируем имя питомца во фронтенде
        if (userData.pet) userData.pet.name = newName;
        if (userData.owned_pets && currentPetId) {
            if (!userData.owned_pets[currentPetId]) {
                userData.owned_pets[currentPetId] = {};
            }
            userData.owned_pets[currentPetId].custom_name = newName;
        }

        updatePetView();
        renderProfilePet(userData.pet);
        closeRenamePetModal();
        showProfileFeedback('Имя питомца изменено.', 'success');
        tg?.HapticFeedback?.notificationOccurred('success');
    } catch (error) {
        if (feedback) feedback.textContent = error.message || 'Не удалось изменить имя.';
    } finally {
        if (button) button.disabled = false;
    }
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
    const response = await fetchWithTimeout(path, {
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


async function openMemberPet(member) {
    if (!member || member.user_id == null || !chatContext.chatId) return;

    try {
        const data = await postChatAction('/api/chat/member/pet', {
            target_user_id: member.user_id
        });
        renderMemberPet(data.member, data.pet);
        const modal = document.getElementById('memberPetModal');
        if (modal) modal.style.display = 'flex';
    } catch (error) {
        showProfileFeedback(error.message || 'Не удалось открыть питомца.', 'error');
    }
}


function closeMemberPetModal() {
    const modal = document.getElementById('memberPetModal');
    if (modal) modal.style.display = 'none';
}


function renderMemberPet(member, pet) {
    const name = document.getElementById('member-pet-owner');
    const petName = document.getElementById('member-pet-name');
    const level = document.getElementById('member-pet-level');
    const image = document.getElementById('member-pet-image');
    if (name) name.textContent = member?.display_name || 'Участник';
    if (petName) petName.textContent = pet.name || 'Питомец';
    if (level) level.textContent = pet.level ?? 1;
    if (image) {
        image.src = pet.image || '/Pets/Slava.png';
        image.alt = pet.name || 'Питомец';
        image.onerror = () => {
            image.replaceWith(document.createTextNode('🐾'));
        };
    }

    ['health', 'hunger', 'happiness', 'energy'].forEach(key => {
        const value = Math.max(0, Math.min(100, Number(pet[key] ?? 100)));
        const valueElement = document.getElementById(`member-pet-${key}-value`);
        const bar = document.getElementById(`member-pet-${key}-bar`);
        if (valueElement) valueElement.textContent = `${value} / 100`;
        if (bar) {
            bar.style.width = `${value}%`;
            bar.parentElement.setAttribute('aria-valuenow', String(value));
        }
    });
}


function normalizePetData(pet) {
    if (!pet) return null;

    const id = pet.id || pet.pet_id || 'bars';
    const definition = userData.petCatalog.find(item => item.id === id) || {};
    return {
        ...definition,
        ...pet,
        id,
        name: pet.name || pet.pet_name || definition.name || 'Питомец',
        image: pet.image || definition.image || '/Pets/Slava.png',
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
    } else if (tabName === 'profile' && chatContext.chatId) {
        void refreshChatMembers();
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
        const row = document.createElement('article');
        row.className = 'profile-member-row';

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

        const actions = document.createElement('div');
        actions.className = 'member-actions';

        const giftButton = document.createElement('button');
        giftButton.className = 'member-action-button member-gift-action';
        giftButton.type = 'button';
        giftButton.disabled = userId == null;
        giftButton.textContent = '🎁 Подарить R$';
        giftButton.addEventListener('click', () => openGiftModal(member));

        const petButton = document.createElement('button');
        petButton.className = 'member-action-button member-pet-action';
        petButton.type = 'button';
        petButton.disabled = userId == null;
        petButton.textContent = '🐾 Посмотреть питомца';
        petButton.addEventListener('click', () => openMemberPet(member));

        actions.append(giftButton, petButton);
        row.append(avatar, details, actions);
        fragment.appendChild(row);
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
        stats.textContent = `${Number(member.score_value || 0)} очков побед · ${Number(member.convertible_rp || 0)} RP · ${Number(member.balance_r || 0)} R$`;

        const points = document.createElement('strong');
        points.className = 'leaderboard-total';
        points.textContent = `${Number(member.score_value || 0)} очк.`;

        user.append(name, stats);
        row.append(rank, user, points);
        fragment.appendChild(row);
    });
    container.replaceChildren(fragment);
}




function selectLeaderboardMode(mode) {
    if (!['online', 'solo', 'local'].includes(mode)) return;
    selectedLeaderboardMode = mode;
    document.querySelectorAll('[data-leaderboard-mode]').forEach(button => {
        const isActive = button.dataset.leaderboardMode === mode;
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-selected', String(isActive));
    });
        renderLeaderboard();
    fetchLeaderboard();
}

function renderLeaderboard() {
    const overallContainer = document.getElementById('overallLeaderboardList');
    const modeContainer = document.getElementById('leaderboardList');
    const leaderboard = Array.isArray(userData.leaderboard) ? userData.leaderboard : [];

    const renderRows = (container, rows, emptyMessage, mode) => {
        if (!container) return;
        if (rows.length === 0) {
            const empty = document.createElement('p');
            empty.className = 'leaderboard-empty';
            empty.textContent = emptyMessage;
            container.replaceChildren(empty);
            return;
        }

        const fragment = document.createDocumentFragment();
        rows.forEach((member, index) => {
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
            stats.textContent = mode === null
                ? 'Суммарные очки во всех игровых режимах'
                : `Очки: ${Number(member.mode_scores?.[mode] || 0)}`;
            const points = document.createElement('strong');
            points.className = 'leaderboard-total';
            const score = mode === null
                ? Number(member.score_value || 0)
                : Number(member.mode_scores?.[mode] || 0);
            points.textContent = `${score} очк.`;
            user.append(name, stats);
            row.append(rank, user, points);
            fragment.appendChild(row);
        });
        container.replaceChildren(fragment);
    };

    const totals = leaderboard
        .filter(member => Number(member.score_value || 0) > 0)
        .slice()
        .sort((a, b) => Number(b.score_value || 0) - Number(a.score_value || 0));
    renderRows(overallContainer, totals, 'Пока нет набранных очков.', null);

    const modeRows = leaderboard
        .filter(member => Number(member.mode_scores?.[selectedLeaderboardMode] || 0) > 0)
        .slice()
        .sort((a, b) => Number(b.mode_scores?.[selectedLeaderboardMode] || 0) - Number(a.mode_scores?.[selectedLeaderboardMode] || 0));
    renderRows(modeContainer, modeRows, 'В этом режиме пока нет набранных очков.', selectedLeaderboardMode);
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
    const grid = document.getElementById('petChoicesGrid');
    if (!grid) return;

        grid.innerHTML = '';

    const ownedPets = userData.owned_pets && typeof userData.owned_pets === 'object'
        ? userData.owned_pets
        : {};
    const selectablePets = (userData.petCatalog || []).filter(pet =>
        Object.prototype.hasOwnProperty.call(ownedPets, pet.id)
    );

    selectablePets.forEach(pet => {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = `pet-choice-card ${currentPetId === pet.id ? 'active' : ''}`;
        card.setAttribute('aria-pressed', String(currentPetId === pet.id));

        // Добавили кнопку «i» прямо внутрь карточки
        card.innerHTML = `
            <img src="${escapeHtml(pet.image || '/Pets/SnowLeopard.png')}" alt="Питомец" class="pet-choice-img">
            <button type="button" class="pet-info-btn" title="Информация о питомце">i</button>
        `;

        card.querySelector('img').onerror = event => {
            event.currentTarget.replaceWith(document.createTextNode('🐾'));
        };

        // Обработчик для кнопки информации (не дает выбрать питомец при клике на «i»)
        card.querySelector('.pet-info-btn').onclick = (e) => {
            e.stopPropagation();
            showPetInfo(pet);
        };

        // Клик по самой карточке выбирает питомца
        card.onclick = async () => {
            try {
                // Берём сохраненное имя текущего питомца из стейта, если кликнули по тому же питомцу,
                // либо берем дефолтное имя нового питомца, если переключаем на другого.
                let customName = '';
                if (currentPetId === pet.id) {
                    const customNameInput = document.getElementById('pet-name');
                    customName = customNameInput ? customNameInput.value.trim() : '';
                } else {
                    // Если выбираем другого питомца, берем его дефолтное имя из каталога 
                    // или то, что уже было сохранено для него ранее
                    customName = userData.owned_pets?.[pet.id]?.custom_name || pet.name || '';
                }

                const response = await fetchWithTimeout('/api/me', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Telegram-Init-Data': tg?.initData || ''
                    },
                    body: JSON.stringify({
                        pet_id: pet.id,
                        pet_name: customName
                    })
                });

                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Pet selection failed');
                                                }

                userData.pet = normalizePetData(data.pet);
                currentPetId = userData.pet.id;
                userData.owned_pets = userData.owned_pets || {};
                userData.owned_pets[currentPetId] = {
                    ...(userData.owned_pets[currentPetId] || {}),
                    custom_name: data.pet.custom_name || data.pet.name || pet.name
                };
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


async function savePetName(event) {
    const petNameInput = event.currentTarget;
    const petId = currentPetId || userData.pet?.id;
    if (!petNameInput || !petId) return;

    try {
        if (chatContext.chatId) {
            await postChatAction('/api/pet/rename', {
                new_name: petNameInput.value
            });
            await fetchUserData();
            return;
        }

        const response = await fetchWithTimeout(
            '/api/me',
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': tg?.initData || ''
                },
                body: JSON.stringify({
                    pet_id: petId,
                    pet_name: petNameInput.value
                })
            },
            API_REQUEST_TIMEOUT_MS
        );
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.error || 'Failed to save pet name');
                        }

                userData.pet = normalizePetData(data.pet);
        currentPetId = userData.pet?.id || petId;
        userData.owned_pets = userData.owned_pets || {};
        userData.owned_pets[currentPetId] = {
            ...(userData.owned_pets[currentPetId] || {}),
            custom_name: data.pet?.custom_name || data.pet?.name || petNameInput.value.trim()
        };
        updatePetView();
    } catch (error) {
        console.error('Failed to save pet name:', error);
        tg?.showAlert?.('Could not save the pet name. Please try again.');
        updatePetView();
    }
}


function updatePetView() {
    const petDisplay = document.getElementById('petDisplay');
    if (!petDisplay) return;

    if (!userData.pet?.id) {
        const petNameInput = document.getElementById('pet-name');
        if (petNameInput) petNameInput.value = '';
        petDisplay.replaceChildren();
        return;
    }

        const activePet = userData.petCatalog.find(
        pet => pet.id === currentPetId
    ) || userData.petCatalog[0] || userData.pet || {
        name: 'Питомец',
        image: '/Pets/Slava.png'
    };
    const maxLevel = Math.max(1, Number(userData.pet?.max_level || 10));
    const level = Math.max(1, Number(userData.pet?.level || 1));
    const health = Math.max(0, Math.min(100, Number(userData.pet?.health ?? 100)));
    const hunger = Math.max(0, Math.min(100, Number(userData.pet?.hunger ?? 100)));
        const happiness = Math.max(0, Math.min(100, Number(userData.pet?.happiness ?? 100)));
    const petName = document.getElementById('pet-name');
    if (petName) {
        petName.value = userData.pet?.custom_name
            || userData.owned_pets?.[currentPetId]?.custom_name
            || userData.pet_name
            || userData.custom_name
            || userData.pet?.pet_name
            || userData.pet?.name
            || activePet.name;
        if (petName.dataset.saveHandlerAttached !== 'true') {
            petName.addEventListener('change', savePetName);
            petName.dataset.saveHandlerAttached = 'true';
        }

        const savePetNameButton = document.getElementById('save-pet-name-btn');
        if (savePetNameButton && savePetNameButton.dataset.saveHandlerAttached !== 'true') {
            savePetNameButton.addEventListener('mousedown', event => event.preventDefault());
            savePetNameButton.addEventListener('click', () => {
                savePetName({ currentTarget: petName });
                petName.blur();
                if (tg?.HapticFeedback) {
                    tg.HapticFeedback.notificationOccurred('success');
                }
            });
            savePetNameButton.dataset.saveHandlerAttached = 'true';
        }
    }









        const statValues = {
            'pet-level-value': `${level} / ${maxLevel}`,
            'pet-health-value': `${health} / 100`,
            'pet-hunger-value': `${hunger} / 100`,
        'pet-happiness-value': `${happiness} / 100`
    };
    const statProgress = {
        'pet-level-bar': { value: level, max: maxLevel, width: Math.min(level / maxLevel * 100, 100) },
        'pet-health-bar': { value: health, max: 100, width: health },
        'pet-hunger-bar': { value: hunger, max: 100, width: hunger },
        'pet-happiness-bar': { value: happiness, max: 100, width: happiness }
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

    petDisplay.innerHTML = `
        <img
                        src="${escapeHtml(userData.pet?.image || activePet.image)}"
            alt="${escapeHtml(userData.pet?.name || activePet.name)}"
            class="active-pet-image"
        >
    `;

    petDisplay.querySelectorAll('img').forEach(image => {
        image.onerror = () => image.replaceWith(document.createTextNode('🐾'));
    });
}


function renderShop() {
    const grid = document.getElementById('shopItemsGrid');

    if (!grid) return;

    if (typeof currentShopTab === 'undefined') {
        window.currentShopTab = userData.pet?.type || 'Human';
    }

    let tabs = document.getElementById('shopCategoryTabs');

    if (!tabs) {
        tabs = document.createElement('div');
        tabs.id = 'shopCategoryTabs';
        tabs.className = 'shop-category-tabs';
        grid.parentNode.insertBefore(tabs, grid);
    }

    tabs.innerHTML = '';

    ['Human', 'Animal', 'Robot'].forEach(type => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = type;
        button.className = 'shop-category-tab';
        button.setAttribute('aria-pressed', String(currentShopTab === type));

        button.addEventListener('click', () => {
            currentShopTab = type;
            renderShop();
        });

        tabs.appendChild(button);
    });

    grid.innerHTML = '';

    const foods = (userData.foodCatalog || []).filter(
        food => food.compatible_with === currentShopTab
    );

    if (foods.length === 0) {
        grid.innerHTML = '<p>В этой категории пока нет товаров</p>';
        return;
    }

    foods.forEach(food => {
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
                renderFoodInventory();
                updatePetView();
            } catch (error) {
                console.error('Ошибка при покупке еды:', error);
            }
        });

        grid.appendChild(card);
    });
}


function renderFoodInventory() {
    const grid = document.getElementById('inventoryGrid');
    if (!grid) return;

    const petType = userData.pet?.type;
    const foodItems = (userData.foodCatalog || [])
        .filter(food => food.count > 0 && food.compatible_with === petType)
        .map(food => ({
            icon: food.name.split(' ')[0],
            name: food.name.replace(/^\S+\s*/, ''),
            count: `×${food.count}`
        }));

    if (foodItems.length === 0) {
        grid.innerHTML = `
            <div style="text-align: center; padding: 20px;">
                <p style="margin: 0 0 16px; color: var(--text-secondary);">
                    Пора закупиться вкусняшками 🛍
                </p>
                <button
                    class="primary-action"
                    type="button"
                    data-open-shop
                    style="padding: 10px 18px; border: 0; border-radius: 12px; cursor: pointer;"
                >
                    Перейти в магазин
                </button>
            </div>
        `;

        grid.querySelector('[data-open-shop]').addEventListener('click', () => {
            closeFeedMenuModal();
            switchTab('shop');
            renderShop();
        });
        return;
    }

    grid.innerHTML = foodItems.map(food => `
        <article class="inventory-item">
            <span class="inventory-item-icon">${escapeHtml(food.icon)}</span>
            <span class="inventory-item-name">${escapeHtml(food.name)}</span>
            <strong class="inventory-item-count">${escapeHtml(food.count)}</strong>
        </article>
    `).join('');
}

function renderFeedItems() {
    const grid = document.getElementById('feedItemsGrid');
    if (!grid) return;

    const petType = userData.pet?.type;
    const availableFood = (userData.foodCatalog || []).filter(
        food => food.count > 0 && food.compatible_with === petType
    );

    if (availableFood.length === 0) {
        grid.innerHTML = `
            <div style="text-align: center; padding: 20px;">
                <p style="margin: 0 0 16px; color: var(--text-secondary);">
                    Пора закупиться вкусняшками 🛍
                </p>
                <button
                    class="primary-action"
                    type="button"
                    data-open-shop
                    style="padding: 10px 18px; border: 0; border-radius: 12px; cursor: pointer;"
                >
                    Перейти в магазин
                </button>
            </div>
        `;

        grid.querySelector('[data-open-shop]').addEventListener('click', () => {
            closeFeedMenuModal();
            switchTab('shop');
            renderShop();
        });

        return;
    }

    grid.innerHTML = availableFood.map(food => `
        <button class="feed-food-button" type="button" data-food-id="${escapeHtml(food.id)}">
            <span>${escapeHtml(food.name)} <small>×${escapeHtml(food.count)}</small></span>
            <span class="feed-food-effect">Накормить</span>
        </button>
    `).join('');

    grid.querySelectorAll('[data-food-id]').forEach(button => {
        button.addEventListener('click', () => feedPet(button.dataset.foodId));
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

    const backendOrigin = API_BASE_URL
        ? new URL(API_BASE_URL, window.location.href)
        : window.location;
    const protocol = backendOrigin.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl =
        `${protocol}//${backendOrigin.host}/ws/game/${encodeURIComponent(roomId)}`;

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
                            statusEl.textContent = 'Ничья! 🤝';
                        }
                    } else {
                        const isWin = data.winner === mySymbol;

                        if (statusEl) {
                            statusEl.textContent = isWin
                                ? `Ты победил! 🎉${Number(data.reward) > 0 ? ` Награда: ${Number(data.reward)} RP.` : ''}`
                                : `Победил ${data.winner}`;
                        }

                        if (isWin && Number(data.reward) > 0) {
                            void fetchUserData();
                        }

                        if (isWin && tg?.HapticFeedback) {
                            tg.HapticFeedback.notificationOccurred('success');
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
    const params = new URLSearchParams(window.location.search);
    const startParam =
        tg?.initDataUnsafe?.start_param
        || params.get('tgWebAppStartParam')
        || params.get('startapp')
        || params.get('start_param')
        || '';
    let roomId = params.get('duel_id') || params.get('room_id') || '';
    const duelStartMatch = startParam.match(/^(?:duel|online)_(.+)$/);
    if (!roomId && duelStartMatch) roomId = duelStartMatch[1];
    roomId = roomId.trim();

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
        renderFoodInventory();
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
        const initializeSafely = (name, initialize) => {
            try {
                initialize();
            } catch (error) {
                console.error(`Ошибка инициализации ${name}:`, error);
            }
        };

        try {
            initializeSafely('настроек', initSettings);
            initializeSafely('данных Telegram', initTelegramUser);
            initializeSafely('обработчика суммы обмена', () => {
                document.getElementById('convert-rp-amount')
                    ?.addEventListener('input', updateConvertPreview);
            });
            initializeSafely('предпросмотра обмена', updateConvertPreview);
            initializeSafely('параметров дуэли', checkDuelParams);
        } catch (error) {
            // Ошибка необязательной инициализации интерфейса не должна блокировать авторизацию.
            console.error('Ошибка запуска интерфейса:', error);
        } finally {
            // Запрашиваем профиль независимо от ошибок инициализации UI.
            void fetchUserData();
        }
    }
);

function showPetInfo(pet) {
    document.getElementById("modal-pet-name").innerText = pet.name || "Питомец";
    document.getElementById("modal-pet-rarity").innerText = `Редкость: ${pet.rarity || "Обычный"}`;
    document.getElementById("modal-pet-series").innerText = `Серия: ${pet.series || "Default"}`;
    document.getElementById("modal-pet-type").innerText = `Тип: ${pet.type || "Unknown"}`;
    document.getElementById("modal-pet-desc").innerText = pet.description || "У этого персонажа пока нет описания.";
    
    const imgEl = document.getElementById("modal-pet-img");
    if (pet.image) {
        imgEl.src = pet.image;
    }
    
    document.getElementById("pet-info-modal").style.display = "flex";
}

function closePetInfoModal() {
    document.getElementById("pet-info-modal").style.display = "none";
}

// Открытие модального окна выбора СТАРТОВОГО питомца (фильтрация по is_starter)
function openFirstPetSelector() {
    const modal = document.getElementById('firstPetModal');
    const grid = document.getElementById('firstPetChoicesGrid');
    if (!modal || !grid) return;

    modal.style.display = 'flex';
    grid.innerHTML = '';

    // Берем только тех питомцев, у которых is_starter: true
        const starterPets = (userData.petCatalog || []).filter(pet => pet.is_starter === true);

    if (starterPets.length === 0) {
        grid.textContent = 'Не удалось загрузить стартовых питомцев. Закрой и открой приложение ещё раз.';
        return;
    }

    starterPets.forEach(pet => {
        const card = document.createElement('button');
        card.type = 'button';
        card.className = 'pet-choice-card';
        card.style.minHeight = '120px';

        card.innerHTML = `
            <img src="${escapeHtml(pet.image || '/Pets/SnowLeopard.png')}" alt="${escapeHtml(pet.name)}" class="pet-choice-img" style="width: 70px; height: 70px;">
            <span class="pet-choice-name">${escapeHtml(pet.name)}</span>
        `;

        card.querySelector('img').onerror = event => {
            event.currentTarget.replaceWith(document.createTextNode('🐾'));
        };

        // Клик по карточке сохраняет выбор и закрывает модалку
        card.onclick = async () => {
            try {
                const response = await fetchWithTimeout('/api/me', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Telegram-Init-Data': tg?.initData || ''
                    },
                    body: JSON.stringify({
                        pet_id: pet.id,
                        pet_name: pet.name
                    })
                });

                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Starter pet selection failed');
                                                }

                userData.pet = normalizePetData(data.pet);
                currentPetId = userData.pet.id;
                userData.owned_pets = userData.owned_pets || {};
                userData.owned_pets[currentPetId] = {
                    ...(userData.owned_pets[currentPetId] || {}),
                    custom_name: data.pet.custom_name || data.pet.name || pet.name
                };
                updatePetView();
                
                // Закрываем стартовое модальное окно
                modal.style.display = 'none';

                if (tg?.HapticFeedback) {
                    tg.HapticFeedback.notificationOccurred('success');
                }
            } catch (error) {
                console.error('Не удалось выбрать стартового питомца:', error);
                tg?.showAlert?.('Не удалось выбрать питомца. Попробуй ещё раз.');
            }
        };

        grid.appendChild(card);
    });
}