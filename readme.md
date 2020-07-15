# Usage
Use inline in telegram at [@mtg_card_bot <search_term>](https://telegram.me/mtg_card_bot).

We use [scryfall's API](scryfall.com/) so you can use their search syntax.

# Deploy
install requirements with `pip install -r requirements.txt -t vendored`

install serverless with

export ENV Variables:
`export AWS_ACCESS_KEY_ID=XXXX`
`export AWS_SECRET_ACCESS_KEY=YYYY`

`export TELEGRAM_TOKEN=ZZZZ`

deploy with

`serverless deploy`
