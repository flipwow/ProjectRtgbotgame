// Инициализация Telegram WebApp
const tg = window.Telegram.WebApp;

// Расширяем на весь экран, если поддерживается
tg.expand();

// Обработка кнопки закрытия
const closeBtn = document.getElementById('closeBtn');
if (closeBtn) {
    closeBtn.addEventListener('click', () => {
        tg.close();
    });
}