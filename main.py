import re
import requests
import time
import threading
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import telebot
from telebot import types

# Вставьте сюда свои токены
TELEGRAM_TOKEN = 'YOUR_TELEGRAM_TOKEN'
VK_ACCESS_TOKEN = 'YOUR_VK_ACCESS_TOKEN'

VERSION = "5.131"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Глобальные словари для хранения состояний пользователей и списка сообществ для каждого чата
user_states = {}         # chat_id -> состояние (например, "waiting_for_group_id")
monitored_groups = {}    # chat_id -> список owner_id для отслеживания

# Загрузка модели (при необходимости используйте cache_dir для ускорения загрузки)
model_name = "cointegrated/rubert-tiny2-cedr-emotion-detection"
tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir="./model_cache")
model = AutoModelForSequenceClassification.from_pretrained(model_name, cache_dir="./model_cache")

def get_posts(owner_id):
    url = f"https://api.vk.com/method/wall.get?owner_id={owner_id}&count=10&access_token={VK_ACCESS_TOKEN}&v={VERSION}"
    response = requests.get(url).json()
    if "response" not in response:
        return []
    return [post['id'] for post in response['response']['items']]

def get_comments(owner_id, post_id, last_comment_id=None):
    """
    Возвращает список кортежей: (comment_id, cleaned_text, from_id)
    """
    comments_list = []
    offset = 0
    while True:
        url = (f"https://api.vk.com/method/wall.getComments?owner_id={owner_id}"
               f"&post_id={post_id}&count=100&offset={offset}&access_token={VK_ACCESS_TOKEN}&v={VERSION}")
        response = requests.get(url).json()
        if "response" not in response:
            break
        comments = response["response"]["items"]
        if not comments:
            break
        for comment in comments:
            comment_id = comment['id']
            # Игнорируем комментарии с ID меньше или равным последнему обработанному
            if last_comment_id is not None and comment_id <= last_comment_id:
                continue
            text = comment.get("text", "")
            cleaned_text = re.sub(r'[^\w\s]', '', text)
            cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
            if cleaned_text:
                from_id = comment.get("from_id", 0)
                comments_list.append((comment_id, cleaned_text, from_id))
        offset += 100
    return comments_list

def analyze_emotions(comments_list):
    """
    Принимает список кортежей (comment_id, text, from_id) и возвращает список
    кортежей (comment_id, emotion, from_id), где emotion определяется моделью.
    """
    if not comments_list:
        return []
    texts = [text for (_, text, _) in comments_list]
    inputs = tokenizer(texts, padding=True, truncation=True, return_tensors="pt")
    with torch.no_grad():
        outputs = model(**inputs)
        logits = outputs.logits
        predictions = torch.argmax(logits, dim=1)
    emotion_labels = ["no_emotion", "joy", "sadness", "surprise", "fear", "anger"]
    return [(cid, emotion_labels[pred], uid) for (cid, _, uid), pred in zip(comments_list, predictions)]

def monitor_group(owner_id, chat_id):
    bot.send_message(chat_id, f'Начинаю мониторинг новых комментариев в группе {owner_id}...')
    post_ids = get_posts(owner_id)

    # Локальные словари для хранения последнего ID комментария и накопленных негативных комментариев для каждого поста
    group_last_comment_ids = {}
    accumulated_negatives = {}

    # Инициализация: для каждого поста запоминаем максимальный ID комментария
    for post_id in post_ids:
        comments = get_comments(owner_id, post_id)
        if comments:
            group_last_comment_ids[post_id] = max(comment[0] for comment in comments)
        else:
            group_last_comment_ids[post_id] = None
        accumulated_negatives[post_id] = []

    # Основной цикл мониторинга
    while True:
        for post_id in post_ids:
            new_comments = get_comments(owner_id, post_id, group_last_comment_ids.get(post_id))
            if not new_comments:
                continue
            analyzed_comments = analyze_emotions(new_comments)
            # Если комментарий имеет негативную эмоцию, добавляем его в аккумулятор
            for cid, text, uid in new_comments:
                for c, emotion, user_id in analyzed_comments:
                    if c == cid and emotion in ["sadness", "fear", "anger"]:
                        accumulated_negatives[post_id].append((cid, text, uid))
                        break
            # Если накопилось 3 или более негативных комментария, отправляем уведомление
            if len(accumulated_negatives[post_id]) >= 3:
                post_link = f"https://vk.com/wall{owner_id}_{post_id}"
                message_text = f"Под постом {post_link} обнаружено {len(accumulated_negatives[post_id])} негативных комментариев:\n\n"
                for cid, text, uid in accumulated_negatives[post_id]:
                    if uid < 0:
                        user_link = f"https://vk.com/club{abs(uid)}"
                    else:
                        user_link = f"https://vk.com/id{uid}"
                    message_text += f"Комментарий: \"{text}\"\nАвтор: {user_link}\n\n"
                bot.send_message(chat_id, message_text)
                # После отправки очищаем аккумулятор для данного поста
                accumulated_negatives[post_id] = []
            # Обновляем последний обработанный ID для поста
            if new_comments:
                group_last_comment_ids[post_id] = new_comments[-1][0]
        time.sleep(1)  # Проверяем каждые 60 секунд

def send_main_menu(chat_id):
    markup = types.InlineKeyboardMarkup()
    add_btn = types.InlineKeyboardButton("Добавить сообщество", callback_data="add_group")
    list_btn = types.InlineKeyboardButton("Список сообществ", callback_data="list_groups")
    delete_btn = types.InlineKeyboardButton("Удалить сообщество", callback_data="delete_menu")
    markup.add(add_btn, list_btn, delete_btn)
    bot.send_message(chat_id, "Выберите действие:", reply_markup=markup)

def send_delete_menu(chat_id):
    groups = monitored_groups.get(chat_id, [])
    if not groups:
        bot.send_message(chat_id, "Нет отслеживаемых сообществ для удаления.")
        send_main_menu(chat_id)
        return
    markup = types.InlineKeyboardMarkup()
    for group in groups:
        btn = types.InlineKeyboardButton(f"Удалить {group}", callback_data=f"delete_{group}")
        markup.add(btn)
    bot.send_message(chat_id, "Выберите сообщество для удаления:", reply_markup=markup)

@bot.message_handler(commands=['start'])
def start(message):
    chat_id = message.chat.id
    bot.send_message(chat_id,
                     "Привет! Добро пожаловать в бот для мониторинга негативных комментариев.\n\n"
                     "Используйте кнопки ниже для управления отслеживаемыми сообществами.")
    send_main_menu(chat_id)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    data = call.data

    if data == "add_group":
        bot.send_message(chat_id, "Пожалуйста, введите ID сообщества (отрицательное число, например, -71474813):")
        user_states[chat_id] = "waiting_for_group_id"
    elif data == "list_groups":
        groups = monitored_groups.get(chat_id, [])
        if groups:
            text = "Сейчас отслеживаются следующие сообщества:\n" + "\n".join(str(g) for g in groups)
        else:
            text = "Нет отслеживаемых сообществ."
        bot.send_message(chat_id, text)
        send_main_menu(chat_id)
    elif data == "delete_menu":
        send_delete_menu(chat_id)
    elif data.startswith("delete_"):
        try:
            group_to_delete = int(data.split("_")[1])
        except ValueError:
            bot.send_message(chat_id, "Ошибка в данных. Попробуйте ещё раз.")
            return
        groups = monitored_groups.get(chat_id, [])
        if group_to_delete in groups:
            groups.remove(group_to_delete)
            bot.send_message(chat_id, f"Сообщество {group_to_delete} удалено из отслеживания.")
        else:
            bot.send_message(chat_id, "Такого сообщества нет в списке отслеживания.")
        send_main_menu(chat_id)

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    chat_id = message.chat.id
    # Если ожидается ввод ID сообщества
    if user_states.get(chat_id) == "waiting_for_group_id":
        owner_id_str = message.text.strip()
        if not owner_id_str.lstrip('-').isdigit():
            bot.send_message(chat_id, 'Пожалуйста, отправьте корректный ID сообщества (отрицательное число).')
            return
        owner_id = int(owner_id_str)
        if chat_id not in monitored_groups:
            monitored_groups[chat_id] = []
        if owner_id in monitored_groups[chat_id]:
            bot.send_message(chat_id, f"Сообщество {owner_id} уже добавлено для отслеживания.")
        else:
            monitored_groups[chat_id].append(owner_id)
            bot.send_message(chat_id, f"Сообщество {owner_id} успешно добавлено для отслеживания.")
            # Запускаем мониторинг в отдельном потоке для данного сообщества
            thread = threading.Thread(target=monitor_group, args=(owner_id, chat_id), daemon=True)
            thread.start()
        user_states.pop(chat_id, None)
        send_main_menu(chat_id)
    else:
        # Если сообщение не связано с добавлением, выводим главное меню
        send_main_menu(chat_id)

if __name__ == '__main__':
    bot.polling(none_stop=True)
