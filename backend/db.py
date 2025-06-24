from pymongo import MongoClient
import redis
import json
from datetime import datetime
# MongoDB setup
mongo_client = MongoClient("mongo", 27017)
db = mongo_client["product_reviews"]
review_collection = db["reviews"]

# Redis setup
redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

def serialize_mongo_result(data):
    """Chuyển datetime thành string để JSON hóa"""
    def convert(doc):
        for k, v in doc.items():
            if isinstance(v, datetime):
                doc[k] = v.isoformat()   
        return doc

    if isinstance(data, list):
        return [convert(d) for d in data]
    return convert(data)

def cache_get_reviews(product_id):
    key = f"reviews:{product_id}"
    cached = redis_client.get(key)
    if cached:
        return json.loads(cached)
    return None

def cache_set_reviews(product_id, data):
    key = f"reviews:{product_id}"
    redis_client.set(key, json.dumps(serialize_mongo_result(data)), ex=60) 

def cache_clear_reviews(product_id):
    key = f"reviews:{product_id}"
    redis_client.delete(key)
