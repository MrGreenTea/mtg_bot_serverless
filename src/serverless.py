"""AWS lambda handler for a telegram bot that searches for you on scryfall."""
import json
import logging
import sys
from pathlib import Path
from urllib import parse

from elastic import connect_elastic, ensure_index

sys.path.append(Path(__file__).with_name('vendored'))  # add vendored directory to PythonPath

# pylint: disable=wrong-import-position
import requests

import scryfall
import utils

# pylint: enable=wrong-import-position


LOGGER = logging.getLogger(__name__)

TOKEN = utils.get_config('TELEGRAM_TOKEN')
TELEGRAM_API_URL = utils.get_config('TELEGRAM_API_URL', 'https://api.telegram.org/bot{}/').format(TOKEN)

ELASTIC_CLIENT = connect_elastic(utils.get_config('ELASTIC_ENDPOINT'))


def compute_answer(query_id, query_string, user_from, offset):
    """Compute the answer for the given message as a inline answer."""
    username, first_name = user_from.get('username', ''), user_from['first_name']

    LOGGER.info('%s: Query %s from %r (%s) with offset: %r',
                query_id, query_string, first_name, username, offset)

    response = {
        'inline_query_id': query_id,
        'cache_time': 3600
    }

    if len(query_string) < 3:
        LOGGER.info("Query to short, not responding")
        response['results'] = []
        return response

    response.update(scryfall.get_photos_from_scryfall(query_string, int(offset) if offset else 0))

    LOGGER.info('next offset: %s', response.get("next_offset"))

    return response


def glance_msg(msg):
    """
    Glance info about the msg to a dictionary.

    >>> glance_msg({'from': 'from', 'id':'id', 'query': 'query', 'offset': 'offset'})
    {'user_from': 'from', 'query_id': 'id', 'query_string': 'query', 'offset': 'offset'}
    """
    return {
        'user_from': msg['from'],
        'query_id': msg['id'],
        'query_string': msg['query'],
        'offset': msg['offset']
    }


def answer_inline_query(msg):
    """answer the inline query at msg."""

    try:
        response_data = compute_answer(**glance_msg(msg))
    except Exception as error:  # pylint: disable=broad-except
        LOGGER.critical("An error occurred when trying to compute answer", exc_info=error)
        return {"statusCode": 502}

    response_data['results'] = json.dumps(response_data['results'])

    LOGGER.debug('sending %s', response_data)
    post_request = requests.post(url=parse.urljoin(TELEGRAM_API_URL, 'answerInlineQuery'),
                                 data=response_data)
    LOGGER.debug(post_request.text)
    try:
        post_request.raise_for_status()
    except requests.HTTPError:
        return {"statusCode": 502}
    return {"statusCode": 200}


ensure_index(ELASTIC_CLIENT, 'inline_queries')


def search(event, _):
    """Answer the event. The second parameter is the AWS context and ignored for now."""
    try:
        data = json.loads(event["body"])
    except (KeyError, json.JSONDecodeError):
        return {
            "statusCode": 400,
            "message": "body is not valid json or missing"
        }
    LOGGER.debug(data)

    if 'inline_query' in data:
        message = data['inline_query']
        try:
            return answer_inline_query(message)
        except Exception as error:  # pylint: disable=broad-except
            LOGGER.error("Error while trying to answer", exc_info=error)
            return {"statusCode": 500}
    elif 'message' in data:
        return {"statusCode": 200}
    else:
        return {
            "statusCode": 400,
            "message": "unknown message type. Expected inline_query or message in data."
        }
