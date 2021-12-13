
# Bots
## Running locally
To run the bots locally you will need to set several environment variables with your own keys.
Environment variables necessary:
- `ETH_CHAIN_API_KEY`
- `SUBGRAPH_API_KEY`
- `DISCORD_BOT_TOKEN` (`DISCORD_BOT_TOKEN_PROD` for prod application)
- `TELE_BOT_KEY` (`TELEGRAM_BOT_TOKEN_PROD` for prod application)

## Bot Hosting
Bots instances are hosted on the `bots-host-instance` GCP instance and configured under the `ubuntu` user. Access to the Beanstalk GCP account can be granted by @funderberker or @FRAG. Additional documentation of the GCP config can be found on the instance.

### Restarting Bots
Bots will automatically start on boot of the GCP instance. If the bots get into a bad state the quickest way to get them running again is by restarting the GCP instance (either through the online console GUI or via the GCP CLI). Logs of the bots can be found on the instance.

### Updating Bots
SSH into the GCP host instance and navigate to `/home/` for details on how to update through git.
