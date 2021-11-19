# Bots
Several bots will be implemented here which will collect and disseminate data through community channels (Telegram, Discord, Twitter).

Each bot will be implemented in Python. They will collect data from the Beanstalk graphs and/or the Ethereum chain and may maintain a small amount of persistent state in local storage. Each bot will be implemented in such a way that it can serve all necessary output channels.

## Communication Channels

The Python bots will disseminate information through the various text-based community channels that the Beanstalk Protocol maintains. Presently this includes Telegram (announcement only), Discord, and Twitter.

Each of these applications has their own API for handling messages. We pull third-party SDKs for each to simplify interaction with the various APIs.

### Telegram
API Documentation: https://core.telegram.org/bots/api
Python SDK Library: https://github.com/eternnoir/pyTelegramBotAPI (GPLv2 License)

### Discord
API Documentation: https://discord.com/developers/docs/intro
Python SDK Library: https://github.com/Rapptz/discord.py (MIT License)

### Twitter
API Documentation: https://developer.twitter.com/en/docs/twitter-api
Python SDK Library: https://github.com/bear/python-twitter (Apache License)

## Bot List

## Read-Only Bots
- __Peg Bot__ that sends a message every time the peg is crossed. (Discord, Telegram, Twitter)
- __LP Bot__ that sends a message on each pool interaction (buys, sells, adds, removes).
- __Sunrise Bot__ that sends a message each sunrise call with relevant stats for the current/previous season Beans minted, beans sowed, price, weather, soil.
- __Contract Bot__ that sends a message each interaction with the Beanstalk contract deposits, withdrawals, claims, sows, harvests.
- __End of Day Bot__ that sends a message each interaction with the Beanstalk contract deposits, withdrawals, claims, sows, harvests.

## Interactive Bots
__Personal Balances Bot__ - like someone to be able to send a wallet (or list of wallets) to a telegram bot and then every sunrise call get a full account update for all wallets listed. This would likely come after at least some of the items in a) are completed.
