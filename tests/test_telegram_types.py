from src import scryfall


def test_inline_card():
    card = {
        'name': 'name',
        'id': 'id',
        'scryfall_uri': 'scryfall_uri'
            }
    inline_card = scryfall.inline_card(card, 0, 0, 'photo_url', 'thumb_url')
    assert inline_card['type'] == 'photo'
    assert inline_card['photo_width'] == 0
    assert inline_card['photo_height'] == 0
    assert inline_card['photo_url'] == 'photo_url'
    assert inline_card['thumb_url'] == 'thumb_url'
    assert inline_card['id']
