# VK Comment Monitoring Bot

Этот проект представляет собой Telegram-бота для мониторинга комментариев в сообществах VK. Бот отслеживает комментарии и анализирует их эмоциональную окраску с использованием модели `cointegrated/rubert-tiny2-cedr-emotion-detection`.

## Функциональность

- Мониторинг комментариев в постах VK-сообществ
- Анализ эмоциональной окраски комментариев
- Уведомление в Telegram о негативных комментариях
- Управление отслеживаемыми сообществами через Telegram-бота

## Используемые технологии

- Python
- VK API
- Transformers (Hugging Face)
- PyTorch
- Telebot (Telegram API)

## Установка

1. Клонируйте репозиторий:
   ```sh
   git clone https://github.com/yourusername/vk-comment-monitor-bot.git
   cd vk-comment-monitor-bot
   ```
2. Установите зависимости:
   ```sh
   pip install -r requirements.txt
   ```
3. Укажите ваши токены:
   ```sh
   TELEGRAM_TOKEN=your_telegram_token
   VK_ACCESS_TOKEN=your_vk_access_token
   ```

## Запуск

Запустите бота командой:
```sh
python bot.py
```

## Структура проекта
```
vk-comment-monitor-bot/
│── bot.py                 # Основной файл с кодом бота
│── requirements.txt        # Зависимости проекта
│── README.md               # Документация проекта
```
