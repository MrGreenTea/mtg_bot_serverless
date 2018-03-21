"""AWS lambda handler for a telegram bot that searches for you on scryfall."""
import functools
import json
import logging
import os
import sys
import uuid
from itertools import zip_longest
from urllib import parse


def get_config(name: str, default=None) -> str:
    """
    Returns the environment variable with name or default if it's not set.

    Will raise an KeyError if default is None and name is not set.
    """
    if default is None:
        return os.environ[name]

    return os.environ.get(name, default)


BASE_DIR = os.path.dirname(os.path.realpath(__file__))
# add vendored packages for import.
sys.path.append(get_config('VENDORED_PATH', os.path.join(BASE_DIR, 'vendored')))

import requests  # pylint: disable=wrong-import-position

TOKEN = get_config('TELEGRAM_TOKEN')
TELEGRAM_API_URL = get_config('TELEGRAM_API_URL', 'https://api.telegram.org/bot{}/').format(TOKEN)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)  # only set logging level when running as main

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(os.environ.get('LOGGING_LEVEL', logging.DEBUG))

SCRYFALL_API_URL = get_config('SCRYFALL_API_URL', 'https://api.scryfall.com/cards/search?{}')
RESULTS_AT_ONCE = os.environ.get('RESULTS_AT_ONCE', 24)


class Results(list):
    """Iterates over scryfall results in chunks."""
    session = requests.Session()

    def __init__(self, query, chunk_size):
        super(Results, self).__init__()
        self.query = query
        data = parse.urlencode({'order': 'edhrec', 'q': query})
        self.search_url = SCRYFALL_API_URL.format(data)
        self.next_url = self.search_url
        self.chunk_size = chunk_size

    def get_url(self, url):
        """Return json result for url."""
        req = self.session.get(url)
        req.raise_for_status()
        return req.json()

    def __getitem__(self, item):
        # This is quite unoptimized an might take a long while when trying to get the last page for example.
        while item >= len(self):  # as long as we don't have the page cached, we have to get the next one.
            if self.next_url is not None:
                results_json = self.get_url(self.next_url)
                self.extend(list(p) for p in paginate_iterator(results_json['data'], self.chunk_size))
                self.next_url = results_json.get('next_page', None)
            else:
                raise IndexError(f'{self!r} has no page {item} for chunk_size={self.chunk_size}')

        return super(Results, self).__getitem__(item)

    def __repr__(self):
        return f'{__name__}.{self.__class__.__name__}({self.query!r}, {self.chunk_size!r})'


def paginate_iterator(iterable, chunk_size):
    """
    Paginates the given iterable into chunks of chunk_size

    >>> [list(p) for p in paginate_iterator(range(4), 2)]
    [[0, 1], [2, 3]]
    """
    _fill_value = object()
    iters = [iter(iterable)] * chunk_size
    for chunk in zip_longest(*iters, fillvalue=_fill_value):
        yield (i for i in chunk if i is not _fill_value)


def inline_button(card_name, url):
    """
    Creates an InlineKeyboardMarkup for the given card_name and url.

    >>> inline_button('name', 'http://url.com')
    {'inline_keyboard': [[{'text': 'name', 'url': 'http://url.com'}]]}
    """
    return dict(inline_keyboard=[[  # InlineKeyboardMarkup
        dict(text=card_name, url=url)  # InlineKeyboardButton
    ]])


def inline_card(card, photo_width, photo_height, photo_url, thumb_url):
    """
    Create an InlineQueryResultPhoto for the given card.
    """
    name, scryfall_uri = card['name'], card['scryfall_uri']
    reply_markup = inline_button(name, scryfall_uri)

    return {
        'type': 'photo',
        'id': str(uuid.uuid4()),
        'photo_url': photo_url,
        'thumb_url': thumb_url,
        'photo_width': photo_width,
        'photo_height': photo_height,
        'reply_markup': reply_markup
    }


def inline_photo_from_card(card):
    """
    Build InlineQueryResultPhotos from the given card dict.

    Works even for double faced cards.
    """

    # if there are multiple faces (DFC), iterate over them. Else use the card itself.
    for face in card.get('card_faces', [card]):
        args = dict(card=card, photo_width=672, photo_height=936,
                    photo_url=face['image_uris']['png'], thumb_url=face['image_uris']['small'])
        yield inline_card(**args)


def get_photos_from_scryfall(query_string: str, offset: int = 0):
    """Get results for query_string from scryfall and return as InlineResult."""
    cards = paginated_results(query_string)
    results = []
    try:
        for card in cards[offset]:
            results.extend(inline_photo_from_card(card))
    except (requests.HTTPError, IndexError):  # we silently ignore 404 and other errors
        return dict(results=results)

    return dict(results=results, next_offset=str(offset + 1))


@functools.lru_cache(get_config("LRU_CACHE_MAXSIZE", 128))
def paginated_results(query_string):
    """Simply returns Results(query_string), but caches it for possible reuse."""
    return Results(query_string, chunk_size=RESULTS_AT_ONCE)


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

    _off = int(offset) if offset else 0

    response.update(get_photos_from_scryfall(query_string, _off))

    LOGGER.info(f'next offset: {response.get("next_offset", -1)}')

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
    post_request.raise_for_status()
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
            "message": "not imlemented"
        }


if __name__ == '__main__':
    import doctest

    doctest.testmod()
