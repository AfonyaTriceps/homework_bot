import logging
import os
import sys
import time
from http import HTTPStatus
from typing import Dict, List, Union

import requests
import telegram
from dotenv import load_dotenv
from requests.exceptions import RequestException

from exception import PracticumException

logging.basicConfig(
    level=logging.INFO,
    filename='program.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s - %(funcName)s',
)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(stream=sys.stdout))

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600  # 60 sec * 10
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.',
}


def check_tokens() -> None:
    """Проверяет доступность переменных окружения.

    Raises:
        KeyError: Если отсутствует переменная окружения.
    """
    tokens = ['PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID']
    for token in tokens:
        if globals()[token] is None:
            logger.critical(f'Отсутствует обязательная переменная {token}')
            raise KeyError(f'Отсутствует переменная окружения {token}')


def send_message(bot, message: str) -> None:
    """Отправляет сообщение в Telegram чат.

    Args:
        bot: Бот-аккаунт
        message (str): Сообщение для отправки.
    """
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug(
            f'Сообщение в Telegram отправлено: {message}',
        )
    except telegram.TelegramError as telegram_error:
        logger.error(
            f'Сообщение в Telegram не отправлено: {telegram_error}',
        )


def get_api_answer(timestamp: int) -> Dict[str, Union[List, int]]:
    """Делает запрос к эндпоинту API-сервиса.

    Args:
        timestamp (int): Период, от которого работы попадают в список.

    Returns:
        response_json (dict): ответ API в формате json.

    Raises:
        PracticumException: Если присутствует ошибка при запросе к API.
    """
    logger.info('Получение ответа от сервера')
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={
                'from_date': timestamp,
            },
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


def check_response(
    response: Dict[str, Union[List, int]],
) -> List[Dict[str, Union[str, int]]]:
    """Проверяет ответ API на корректность.

    Args:
        response (dict): Ответ API в формате json.

    Returns:
        list: Список, содержащий информацию о домашних работах.

    Raises:
        KeyError: Если отсутствует ключ homeworks,
        TypeError: Если неверный тип данных у элемента.
    """
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


def parse_status(homework: Dict[str, Union[str, int]]) -> str:
    """Извлекает статус домашней работы.

    Args:
        homework (dict): Словарь, содержащий информацию о домашней работе.

    Returns:
        str: Строка, содержащая наименование и статус домашней работы.

    Raises:
        PracticumException: Если отсутствует ключ в ответе API или
            найден неизвестный статус работы.
    """
    logger.info(
        'Извлекаем информацию о статусе ДЗ',
    )
    try:
        name, status = homework['homework_name'], homework['status']
    except KeyError:
        raise PracticumException(
            'Отсутствует ключ в ответе API',
        )

    try:
        verdict = HOMEWORK_VERDICTS[status]
    except KeyError:
        raise PracticumException(
            f'Неизвестный статус работы: {status}',
        )

    logger.debug(
        'Информация о статусе ДЗ извлечена',
    )
    return f'Изменился статус проверки работы "{name}". {verdict}'


def main() -> None:
    """Основная логика работы бота."""
    check_tokens()

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
            if homework:
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
