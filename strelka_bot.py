#!/usr/bin/python
# -*- coding: UTF-8 -*-

from telegram.ext import Updater
import logging
import os
from storer import Storer
from utils import CardInfo, UserInfo, ThresholdExceedListener

STORED_FILE = os.getenv('STRELKA_STORED_FILE', 'strelka_bot_shelve.db')
TOKEN_FILENAME = 'token.lst'
UPDATE_TIMEOUT = 10. * 60 * 1000 #10 min
BALANCE_CHECK_INTERVAL_SEC = 3600 # 1 hour

users = {}
storer = Storer(STORED_FILE)
job_queue = None

# Enable Logging
logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO)

logger = logging.getLogger(__name__)

def get_description():
    return """/help - Показать помощь (список команд)
/getcardbalance [номер карты] - Показать баланс указанной карта
/addcard [номер карты] - Зарегестрировать(добавить) указанную карту
/removecard [номер карты] - Удалить указанную карту
/getcards - Показывает баланс зарегестированных карт
/setthreshold [минимальный остаток] - Установить минимальную сумму для оповещений по картам"""

def start(bot, update):
    bot.sendMessage(update.message.chat_id, text='Привет!:\n%s'%(get_description()))

def help(bot, update):
    bot.sendMessage(update.message.chat_id
        , text="Поддерживаемые команды:\n%s"%(get_description()))

def get_cards(bot, update):
    logger.info("New get_cards message\nFrom: %s\nchat_id: %d\nText: %s" %
                (update.message.from_user,
                 update.message.chat_id,
                 update.message.text))
    telegram_user = update.message.from_user
    if not users.has_key(telegram_user.id) or len(users[telegram_user.id].cards) == 0:
        bot.sendMessage(update.message.chat_id
        , text="Нет зарегестированных карт /addcard [номер карты]")
        return

    user = users[telegram_user.id]
    cards = user.cards
    response = ""
    for card in cards.values():
        card.update()
        if len(response) != 0: response += '\n'
        response += "Баланс карты %s: %.2f" % (card.card_number, card.balance)

    bot.sendMessage(update.message.chat_id
        , text=response)

def add_card(bot, update, args):
    logger.info("New add_card message\nFrom: %s\nchat_id: %d\nText: %s" %
                (update.message.from_user,
                 update.message.chat_id,
                 update.message.text))

    if len(args) != 1:
        bot.sendMessage(update.message.chat_id, text="Использование:\n/addcard 1234567890")
        return

    card_number = args[0].encode('utf8')

    telegram_user = update.message.from_user
    if not users.has_key(telegram_user.id):
        users[telegram_user.id] = UserInfo(telegram_user)

    user = users[telegram_user.id]
    if not user.cards.has_key(card_number):
        is_card_added = user.add_card(card_number)
        if not is_card_added:
            bot.sendMessage(update.message.chat_id, text="Карта %s заблокирована и не может быть добавлена" % (card_number))
            return
        storer.store('users', users)
        bot.sendMessage(update.message.chat_id, text="Карта %s была успешно добавлена" % (card_number))
    else:
        bot.sendMessage(update.message.chat_id, text="Карта %s уже добавлена" % (card_number))

def remove_card(bot, update, args):
    logger.info("New remove_card message\nFrom: %s\nchat_id: %d\nText: %s" %
                (update.message.from_user,
                 update.message.chat_id,
                 update.message.text))
    if len(args) != 1:
        bot.sendMessage(update.message.chat_id, text="Использование:\n/removecard 1234567890")
        return
    card_number = args[0]
    telegram_user = update.message.from_user
    if not users.has_key(telegram_user.id):
        bot.sendMessage(update.message.chat_id, text="There are no cards registered for you")
        return
    user = users[telegram_user.id]
    if user.cards.has_key(card_number):
        user.cards.pop(card_number)
        storer.store('users', users)
        bot.sendMessage(update.message.chat_id, text="Card %s has been successfully removed" % (card_number))
    else:
        bot.sendMessage(update.message.chat_id, text="Card %s has not been added. Do nothing" % (card_number))

def set_threshold(bot, update, args):
    logger.info("New set_threshold message\nFrom: %s\nchat_id: %d\nText: %s" %
                (update.message.from_user,
                 update.message.chat_id,
                 update.message.text))
    if len(args) == 0:
        bot.sendMessage(update.message.chat_id, text="Использование:\n/setthreshold threshold [card_number ...]")
        return
    threshold = args[0]
    card_numbers = args[1:]
    telegram_user = update.message.from_user
    if not users.has_key(telegram_user.id) or len(users[telegram_user.id].cards) == 0:
        bot.sendMessage(update.message.chat_id, text="There are no cards registered for you")
        return
    user = users[telegram_user.id]
    if len(card_numbers) == 0:
        card_numbers = user.cards.keys()
    for card_number in card_numbers:
        if not user.cards.has_key(card_number):
            add_card(bot, update, card_number)
        card = user.cards[card_number]
        card.set_threshold(threshold)
        listener = ThresholdExceedListener(bot=bot, chat_id=update.message.chat_id)

        card.set_value_changed_listener(listener)

        storer.store('users', users)
        
        threshold_status = "ok" if card.check_threshold_valid() else "violated"
        bot.sendMessage(update.message.chat_id, text="Threshold %s specified for card %s. Current status: %s"
            % (threshold, card_number, threshold_status))

def get_card_balance(bot, update, args):
    logger.info("New get_card_balance message\nFrom: %s\nchat_id: %d\nText: %s" %
                (update.message.from_user,
                 update.message.chat_id,
                 update.message.text))

    if len(args) != 1:
        bot.sendMessage(update.message.chat_id, text="Использование:\n/getcardbalance 1234567890")
        return

    card_number = args[0]
    try:
        card = CardInfo(card_number)
        bot.sendMessage(update.message.chat_id
            , text="Card balance for %s: %.2f"%(card_number, card.balance))
    except ValueError as err:
        logger.error(err)
        bot.sendMessage(update.message.chat_id
            , text="Can't process card %s" % card_number)

def read_token():
    f = open(TOKEN_FILENAME)
    token = f.readline().strip()
    f.close()
    return token

def check_thresholds(bot):
    for user in users.values():
        for card in user.cards.values():
            card.update()

def main():
    global users
    users = storer.restore('users')
    if users is None: users = {}

    global job_queue
    # Create the EventHandler and pass it your bot's token.

    token = read_token()
    updater = Updater(token)
    job_queue = updater.job_queue
    job_queue.put(check_thresholds, BALANCE_CHECK_INTERVAL_SEC, repeat=True)
    # Get the dispatcher to register handlers
    dp = updater.dispatcher

    # This is how we add handlers for Telegram messages
    dp.addTelegramCommandHandler("help", help)
    dp.addTelegramCommandHandler("start", start)
    dp.addTelegramCommandHandler("getcardbalance", get_card_balance)
    dp.addTelegramCommandHandler("addcard", add_card)
    dp.addTelegramCommandHandler("removecard", remove_card)
    dp.addTelegramCommandHandler("getcards", get_cards)
    dp.addTelegramCommandHandler("setthreshold", set_threshold)


    updater.start_polling()

    updater.idle()

if __name__ == '__main__':
    main()
