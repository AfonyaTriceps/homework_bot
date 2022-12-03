import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv
from requests.exceptions import RequestException

from exception import PracticumException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s - %(name)s',
)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(stream=sys.stdout))

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def check_tokens() -> bool:
    """Проверяет доступность переменных окружения."""
    if all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]):
        return True


def send_message(bot, message: str) -> None:
    """Отправляет сообщение в Telegram чат."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(
            f'Сообщение в Telegram отправлено: {message}',
        )
    except telegram.TelegramError as telegram_error:
        logger.error(
            f'Сообщение в Telegram не отправлено: {telegram_error}',
        )


def get_api_answer(timestamp: int) -> dict:
    """Делает запрос к эндпоинту API-сервиса."""
    logger.info('Получение ответа от сервера')
    params = {'from_date': timestamp}
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params=params,
        )
    except RequestException as error:
        raise PracticumException(
            f'Ошибка при запросе к API: {error}',
        )
    if response.status_code != HTTPStatus.OK:
        raise PracticumException(
            f'Ошибка {response.status_code}',
        )

    try:
        response_json = response.json()
    except ValueError:
        raise PracticumException(
            'Ошибка перевода json',
        )
    logger.info('Получен ответ от сервера')
    return response_json


def check_response(response: dict) -> list:
    """Проверяет ответ API на корректность."""
    logger.info(
        'Проверка ответа API соответствие документации',
    )
    if not isinstance(response, dict):
        raise TypeError(
            'Неверный тип данных элемента response',
        )
    elif response.get('homeworks') is None:
        raise KeyError(
            'Отсутствует ключ homeworks',
        )
    elif not isinstance(response['homeworks'], list):
        raise TypeError(
            'Неверный тип данных элемента homeworks',
        )
    logger.debug(
        'API соответствует документации',
    )
    return response.get('homeworks')


def parse_status(homework: dict) -> str:
    """Извлекает статус домашней работы."""
    logger.info(
        'Извлекаем информацию о статусе ДЗ',
    )
    if 'homework_name' not in homework:
        raise KeyError(
            'Отсутствует ключ homework_name в ответе API',
        )
    elif 'status' not in homework:
        raise PracticumException(
            'Отсутствует ключ status в ответе API',
        )

    homework_name = homework['homework_name']
    homework_status = homework['status']

    if homework_status not in HOMEWORK_VERDICTS:
        raise PracticumException(
            f'Неизвестный статус работы: {homework_status}',
        )

    verdict = HOMEWORK_VERDICTS[homework_status]
    logger.debug(
        'Информация о статусе ДЗ извлечена',
    )
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main() -> None:
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical(
            'Отсутствует переменная(-ные) окружения',
        )
        exit()

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    error_message = ''

    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            logger.info(
                'Список домашних работ получен',
            )
            if len(homework) > 0:
                send_message(bot, parse_status(homework[0]))
            else:
                logger.debug(
                    'Новые статусы отсутствуют',
                )
            timestamp = response.get('current_date')
            error_message = ''
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if str(error) != str(error_message):
                send_message(bot, message)
                error_message = error
            logger.error(message)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
