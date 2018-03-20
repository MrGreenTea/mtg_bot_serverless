import json
import logging
import os
import sys

here = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(here, "vendored"))

import requests

TOKEN = os.environ['TELEGRAM_TOKEN']
BASE_URL = "https://api.telegram.org/bot{}".format(TOKEN)

LOGGER = logging.getLogger(__name__)


def inline_query(query, user, id, offset):
    LOGGER.info("Inline Query from %s: %r with offset %d", user, query, offset or 0)
    return {
        "statusCode": 502
    }


def hello(event, context):
    try:
        data = json.loads(event["body"])

        if 'message' in data:
            message = str(data["message"]["text"])
        elif 'inline_query' in data:
            LOGGER.info(data)
            return inline_query(
                query=data['query'],
                user=data['from'],
                id=data['id'],
                offset=data['offset']
            )
        else:
            raise Exception('unknown event', data)

        chat_id = data["message"]["chat"]["id"]
        first_name = data["message"]["chat"]["first_name"]

        response = "Please /start, {}".format(first_name)

        if "start" in message:
            response = "Hello {}".format(first_name)

        data = {"text": response.encode("utf8"), "chat_id": chat_id}
        url = BASE_URL + "/sendMessage"
        requests.post(url, data)

    except Exception as e:
        LOGGER.error("Error while trying to answer", exc_info=e)
        return {
            "statusCode": 500,
            "message": repr(e)
        }

    return {"statusCode": 200}
