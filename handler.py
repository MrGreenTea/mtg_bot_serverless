"""AWS lambda handler for a telegram bot that searches for you on scryfall."""
import json
import logging
import os
import sys
from itertools import zip_longest
from urllib import parse

BASE_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(BASE_DIR, "vendored"))

import requests  # pylint: disable=wrong-import-position

if os.environ.get('TELEGRAM_TOKEN'):
    TOKEN = os.environ['TELEGRAM_TOKEN']
    BASE_URL = "https://api.telegram.org/bot{}".format(TOKEN)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)  # only set logging level when running as main

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)

RESULTS_AT_ONCE = os.environ.get('RESULTS_AT_ONCE', 25)


class Results(list):
    """Iterates over scryfall results in chunks."""
    session = requests.Session()

    def __init__(self, query, chunk_size):
        super(Results, self).__init__()
        self.query = query
        data = parse.urlencode({'order': 'edhrec', 'q': parse.quote(query, safe=':/')})
        self.search_url = 'https://api.scryfall.com/cards/search?{}'.format(data)
        self.next_url = self.search_url
        self.chunk_size = chunk_size

    def get_url(self, url):
        """Return json result for url."""
        req = self.session.get(url)
        req.raise_for_status()
        return req.json()

    def __getitem__(self, item):
        if item >= len(self):
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
    card_id = ''.join(c for c in f"{card['id']}{name}" if c.isalnum())  # remove non alpha numeric from id
    reply_markup = inline_button(name, scryfall_uri)

    return {
        'type': 'photo',
        'id': card_id,
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

    faces = card.get('card_faces',
                     [card])  # if there are multiple faces, iterate over them. Else use the card directly.

    for face in faces:
        args = dict(card=card, photo_width=672, photo_height=936,
                    photo_url=face['image_uris']['png'], thumb_url=face['image_uris']['small'])
        yield inline_card(**args)


def get_photos_from_scryfall(query_string: str, offset: int = 0):
    """Get results for query_string from scryfall and return as InlineResult."""
    try:
        cards = Results(query_string, chunk_size=RESULTS_AT_ONCE)
        results = []
        for card in cards[offset]:
            results.extend(inline_photo_from_card(card))
        next_offset = offset + 1
    except (requests.HTTPError, IndexError):  # we silently ignore 404 and other errors
        next_offset = ''
        results = []

    return dict(results=results, next_offset=next_offset)


def compute_answer(query_id, query_string, user_from, offset):
    """Compute the answer for the given message as a inline answer."""

    username, first_name = user_from['username'], user_from['first_name']

    LOGGER.info('%s: Query %s from %r (%s) with offset: %s',
                query_id, query_string, first_name, username, offset)

    _off = int(offset) if offset else 0

    response = {
        'inline_query_id': query_id,
        'cache_time': 3600,
        **get_photos_from_scryfall(query_string, _off)
    }

    LOGGER.info(f'next offset: {response.get("next_offset", -1)}')

    return response


def glance_msg(msg):
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

    LOGGER.debug('sending %s', response_data)
    requests.post(url=parse.urljoin(BASE_URL, 'answerInlineQuery'),
                  data=response_data)
    return {"statusCode": 200}


def hello(event, _):
    """Answer the event. The second parameter is the AWS context and ignored for now."""
    data = json.loads(event["body"])
    LOGGER.debug(data)
    try:
        if 'inline_query' in data:
            message = data['inline_query']
            return answer_inline_query(message)
        elif 'message' in data:
            return {
                "statusCode": 200,
                "message": "not imlemented"
            }
        else:
            raise Exception(f'unknown event type for {data}')

    except Exception as error:  # pylint: disable=broad-except
        LOGGER.error("Error while trying to answer", exc_info=error)
        return {"statusCode": 500}


if __name__ == '__main__':
    import doctest
    doctest.testmod()
