"""Functionality that connects to the scryfall API."""
import functools
import logging
import uuid
from itertools import zip_longest
from urllib import parse

from vendored import requests

from utils import get_config

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)  # only set logging level when running as main

LOGGER = logging.getLogger(__name__)

SCRYFALL_API_URL = get_config('SCRYFALL_API_URL', 'https://api.scryfall.com/cards/search?{}')
RESULTS_AT_ONCE = get_config('RESULTS_AT_ONCE', 24)


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
    LOGGER.debug('Building InlineResult from %r', card)
    faces = [card] if 'image_uris' in card else card['card_faces']
    for face in faces:
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


if __name__ == '__main__':
    import doctest

    doctest.testmod()
