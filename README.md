# Beanstalk Python Tooling

## Bots
Included in this repo is a set of bots that disseminate information to Beanstalk Telegram and Discord channels.
- **Peg Cross Bot** - sends a message every time the peg is crossed
- **Seasons Bot** - sends a message when the sunrise function is successfully called with stats on the completed season
- **Exchange Bot** - sends a message detailing each interaction with the Uniswap V2 ETH:BEAN pool contract
- **Contract Bot** - sends a message detailing each interaction with the Beanstalk contact

### Running locally
First, install the necessary requirements using `pip3.8 install -r requirements.txt`.

To run the bots locally you will need to set several environment variables with your own keys.
Environment variables necessary:
- `ALCHEMY_ETH_API_KEY`
- `DISCORD_BOT_TOKEN` (`DISCORD_BOT_TOKEN_PROD` for prod application)
- `DISCORD_BASIN_BOT_TOKEN` (`DISCORD_BASIN_BOT_TOKEN_PROD` for prod application)
- (`TELEGRAM_BOT_TOKEN_PROD` for prod application)

Create an `.env.dev` file using the provided example and place your varaibles there. Then, execute `./dev.sh <module>`. For example, to run the main set of bots, execute `./dev.sh bots.discord_bot`.

To test a specific transaction, use `./dev.sh bots.discord_bot <txn hashes here>` with a list of comma separated hashes.