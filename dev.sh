# Load environment variables from .env.dev file
export $(grep -v '^#' .env.dev | xargs)

# Start the requested bot
python3.8 -m $1