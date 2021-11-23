Beanstalk Protocol off-chain tooling

# Heroku Config
Bots instances are hosted on Heroku Applications. Access to the applications is done through the Beanstalk Heroku account (beanstalkfarmslab@gmail.com).


The remotes used for code hosting, staging, and production:
origin	https://github.com/BeanstalkFarms/Beanstalk-Tooling.git
prod	https://git.heroku.com/beanstalk-bots-prod.git
staging	https://git.heroku.com/beanstalk-bots-staging.git

Updates to the code can be pushed to the Heroku app using `git push [remote_name] [local_dev_branch]:main`

Environment variables need to be set in each Heroku application
- `PYTHONPATH=/app/Beanstalk-Tooling/python`
- `DISCORD_BOT_TOKEN` (`DISCORD_BOT_TOKEN_PROD` for prod application)
- `TELE_BOT_KEY` (`TELEGRAM_BOT_TOKEN_PROD` for prod application)
- `ETH_CHAIN_API_KEY`