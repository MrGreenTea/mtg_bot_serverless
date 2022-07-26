import src.serverless

msg = {'id': '535717811308309727',
       'from': {'id': 124731522, 'is_bot': False, 'first_name': 'Jonas', 'username': 'mrgreentea',
                'language_code': 'en-US'}, 'query': 'Huatli', 'offset': ''}

src.serverless.compute_answer(**src.serverless.glance_msg(msg))
