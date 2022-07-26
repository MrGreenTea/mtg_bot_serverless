"""AWS lambda handler for a telegram bot that searches for you on scryfall."""
from .vendored import structlog
structlog.configure(processors=[structlog.processors.JSONRenderer()])

import json
from urllib import parse

from .vendored import requests

from . import scryfall
from . import utils


LOG = structlog.get_logger()

TOKEN = utils.get_config('TELEGRAM_TOKEN')
TELEGRAM_API_URL = utils.get_config('TELEGRAM_API_URL', 'https://api.telegram.org/bot{}/').format(TOKEN)

_CACHE = {}


def compute_answer(query_id, query_string, user_from, offset):
    """Compute the answer for the given message as a inline answer."""
    user_id, username = user_from['id'], user_from.get('username')
    user_full_name = ' '.join(n for n in (user_from.get('first_name'), user_from.get('last_name')) if n)

    LOG.msg("Received query",
                query_id=query_id, query_string=query_string, user_full_name=user_full_name, username=username, offset=offset)

    response = {'inline_query_id': query_id}

    if not query_string:
        response['cache_time'] = 1
        if user_id in _CACHE:
            query_string = _CACHE[user_id]
            LOG.msg("No query given, using cached query", user_id=user_id, query_string=query_string)
        else:
            response['results'] = []
            return response
    else:
        response['cache_time'] = 3600  # cache for up to an hour for the same query

    scryfall_results = scryfall.get_photos_from_scryfall(query_string, int(offset) if offset else 0)

    if scryfall_results['results']:  # cache last results for current User
        LOG.msg("Caching query", query_string=query_string, user_id=user_id)
        _CACHE[user_id] = query_string

    response.update(scryfall_results)

    LOG.msg("Finishing", next_offset=response.get("next_offset"))

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
        LOG.msg("An error occurred when trying to compute answer", exc_info=error)
        raise

    response_data['results'] = json.dumps(response_data['results'])

    LOG.msg('sending', response_data=response_data)
    post_request = requests.post(url=parse.urljoin(TELEGRAM_API_URL, 'answerInlineQuery'),
                                 data=response_data)

    LOG.msg("Response", post_request)
    post_request.raise_for_status()
    response = {"statusCode": 200}
    LOG.msg("Response", **response)
    return response


def search(event, _):
    """Answer the event. The second parameter is the AWS context and ignored for now."""
    LOG.msg("New event", **event)
    try:
        data = json.loads(event["body"])
    except (KeyError, json.JSONDecodeError):
        return {
            "statusCode": 400,
            "message": "body is not valid json or missing"
        }

    LOG.msg("data", data=data)

    if 'inline_query' in data:
        message = data['inline_query']
        try:
            return answer_inline_query(message)
        except Exception as error:  # pylint: disable=broad-except
            LOG.msg("Error while trying to answer", exc_info=error)
            raise

    elif 'message' in data:
        response = {"statusCode": 200, "message": "not implemented"}
        LOG.msg("Response", **response)
        return response
    else:
        response = {
            "statusCode": 400,
            "message": "unknown message type. Expected inline_query or message in data."
        }
        LOG.msg("Response", **response)
        return response
