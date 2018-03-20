from src import scryfall

msg = {'id': '535717811308309727',
       'from': {'id': 124731522, 'is_bot': False, 'first_name': 'Jonas', 'username': 'mrgreentea',
                'language_code': 'en-US'}, 'query': 'Huatli', 'offset': ''}

scryfall.compute_answer(scryfall.glance_msg(msg))
