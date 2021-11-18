Beanstalk Protocol off-chain tooling

# Heroku Config
Bot instances are run on a Heroku application. Updates to the code can be pushed to the Heroku app using `git push heroku python_tooling_and_bots:main`

Environment variables need to be set in each Heroku application
- PYTHONPATH=/app/
- DISCORD_BOT_TOKEN
- TELE_BOT_KEY

