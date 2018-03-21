"""AWS lambda handler for a telegram bot that searches for you on scryfall."""
import datetime
import json
import logging
import uuid
from urllib import parse

import utils

from vendored import requests

import scryfall
import elastic

logging.getLogger().setLevel(utils.get_config('LOGGING_LEVEL', logging.INFO))
LOGGER = logging.getLogger(__name__)

TOKEN = utils.get_config('TELEGRAM_TOKEN')
TELEGRAM_API_URL = utils.get_config('TELEGRAM_API_URL', 'https://api.telegram.org/bot{}/').format(TOKEN)

_CACHE = {}

if utils.get_config('ELASTIC_ENDPOINT', default=False):
    ELASTIC_CLIENT = elastic.connect_elastic(utils.get_config('ELASTIC_ENDPOINT'))
    elastic.ensure_index(ELASTIC_CLIENT, utils.get_config('ELASTIC_INDEX', 'query_requests'))
else:  # else fake the ELASTIC_CLIENT
    import unittest.mock

    ELASTIC_CLIENT = unittest.mock.Mock(spec=elastic.elasticsearch.Elasticsearch)
    del unittest.mock


def compute_answer(query_id, query_string, user_from, offset):
    """Compute the answer for the given message as a inline answer."""
    user_id, username = user_from['id'], user_from.get('username')
    user_full_name = ' '.join(n for n in (user_from.get('first_name'), user_from.get('last_name')) if n)

    LOGGER.info('%s: Query %s from %r (%s) with offset: %r',
                query_id, query_string, user_full_name, username, offset)

    response = {'inline_query_id': query_id}

    if not query_string:
        response['cache_time'] = 1
        if user_id in _CACHE:
            query_string = _CACHE[user_id]
            LOGGER.info("No query given, using cached query for user ID %d: %r", user_id, query_string)
        else:
            response['results'] = []
            return response
    else:
        response['cache_time'] = 3600  # cache for up to an hour for the same query

    scryfall_results = scryfall.get_photos_from_scryfall(query_string, int(offset) if offset else 0)

    if scryfall_results['results']:  # cache last results for current User
        LOGGER.info('Caching query: %r for user with id %d', query_string, user_id)
        _CACHE[user_id] = query_string

    response.update(scryfall_results)

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

    LOGGER.info('sending %s', response_data)
    post_request = requests.post(url=parse.urljoin(TELEGRAM_API_URL, 'answerInlineQuery'),
                                 data=response_data)
    LOGGER.debug(post_request.text)
    try:
        post_request.raise_for_status()
    except requests.HTTPError:
        return {"statusCode": 502}
    return {"statusCode": 200}


def search(event, _):
    """Answer the event. The second parameter is the AWS context and ignored for now."""
    try:
        data = json.loads(event["body"])
    except (KeyError, json.JSONDecodeError):
        return {
            "statusCode": 400,
            "message": "body is not valid json or missing"
        }

    LOGGER.info('Got %s as data', data)

    if 'inline_query' in data:
        message = data['inline_query']
        ELASTIC_CLIENT.create('query_requests', 'json', event.aws_request_id,
                              body=message, timestamp=str(datetime.datetime.now()))
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
