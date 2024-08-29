# Load environment variables from .env.dev file
export $(grep -v '^#' .env.dev | xargs)

# Configure dry run (test transactions)
# Provide comma separated hashes, or "all" to run through the whole collection
if [ -n "$2" ]; then
  export DRY_RUN="$2"
fi

# Start the requested bot
python3.8 -m $1