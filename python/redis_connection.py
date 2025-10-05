import os
import redis
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

redis_connection_options = {
    "host": os.getenv('REDIS_HOST', 'localhost'),
    "port": int(os.getenv('REDIS_PORT', 6379)),
    "db": int(os.getenv('REDIS_DB', 0)),
    "password": os.getenv('REDIS_PASSWORD', None)
}
print(f"Connecting to Redis at {redis_connection_options}")
redis_conn = redis.Redis(**redis_connection_options)
test_redis = redis_conn.ping()
if not test_redis:
    raise Exception("Could not connect to Redis. Please ensure Redis server is running.")
