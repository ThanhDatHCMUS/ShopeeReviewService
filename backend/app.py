from flask import Flask, request, jsonify
from flask_cors import CORS
from bson import ObjectId
from datetime import datetime
from db import review_collection, cache_get_reviews, cache_set_reviews, cache_clear_reviews

app = Flask(__name__)
CORS(app)

def review_to_json(doc):
    doc["_id"] = str(doc["_id"])
    return doc

@app.route("/reviews/<product_id>", methods=["GET"])
def get_reviews(product_id):
    cached = cache_get_reviews(product_id)
    if cached:
        return jsonify({"cached": True, "reviews": cached})
    
    reviews = list(review_collection.find({
        "ProductID": product_id,
        "isDeleted": False
    }))
    reviews = [review_to_json(r) for r in reviews]
    
    cache_set_reviews(product_id, reviews)
    return jsonify({"cached": False, "reviews": reviews})

@app.route("/reviews/product/<product_id>", methods=["GET"])
def get_reviews_by_rating(product_id):
    rating = request.args.get("rating", type=int)

    cached = cache_get_reviews(product_id)
    if cached:
        cached = [r for r in cached if r.get("Rating") == rating] if rating else cached
        return jsonify({"cached": True, "reviews": cached})

    query = {
        "ProductID": product_id,
        "isDeleted": False
    }
    if rating:
        query["Rating"] = rating

    reviews = list(review_collection.find(query))
    for r in reviews:
        r["_id"] = str(r["_id"])
        if isinstance(r["CreatedAt"], datetime):
            r["CreatedAt"] = r["CreatedAt"].isoformat()
    
    return jsonify(reviews)

@app.route("/reviews/product/<product_id>/average", methods=["GET"])
def get_average_rating(product_id):
    pipeline = [
        {"$match": {"ProductID": product_id, "isDeleted": False}},
        {"$group": {"_id": None, "avgRating": {"$avg": "$Rating"}}}
    ]
    result = list(review_collection.aggregate(pipeline))
    avg = result[0]["avgRating"] if result else 0
    return jsonify({"product_id": product_id, "average_rating": round(avg, 2)})

@app.route("/reviews/product/<product_id>/stats", methods=["GET"])
def get_rating_distribution(product_id):
    pipeline = [
        {"$match": {"ProductID": product_id, "isDeleted": False}},
        {"$group": {"_id": "$Rating", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}}
    ]
    result = list(review_collection.aggregate(pipeline))
    
    total = sum(r["count"] for r in result)
    stats = {
        "total_reviews": total,
        "distribution": []
    }

    for i in range(1, 6): 
        entry = next((r for r in result if r["_id"] == i), None)
        count = entry["count"] if entry else 0
        percent = round((count / total) * 100, 2) if total > 0 else 0
        stats["distribution"].append({
            "rating": i,
            "count": count,
            "percent": percent
        })

    return jsonify(stats)

@app.route("/reviews", methods=["POST"])
def create_review():
    data = request.json
    data["isDeleted"] = False
    data["likeViews"] = 0
    data["DislikeView"] = 0
    data["CreatedAt"] = datetime.utcnow()
    data["likeUsers"] = []
    data["dislikedUsers"] = []
    result = review_collection.insert_one(data)
    cache_clear_reviews(data["ProductID"]) 
    return jsonify({"message": "Review created", "id": str(result.inserted_id)})

@app.route("/reviews/<review_id>/like", methods=["POST"])
def like_review(review_id):
    user_id = request.json.get("UserID")
    review = review_collection.find_one({"_id": ObjectId(review_id)})
    if not review:
        return jsonify({"error": "Review not found"}), 404

    if user_id in review.get("likedUsers", []):
        return jsonify({"message": "Already liked"}), 400

    if user_id in review.get("dislikedUsers", []):
        review_collection.update_one(
            {"_id": ObjectId(review_id)},
            {
                "$pull": {"dislikedUsers": user_id},
                "$inc": {"DislikeView": -1}
            }
        )

    review_collection.update_one(
        {"_id": ObjectId(review_id)},
        {
            "$addToSet": {"likedUsers": user_id},
            "$inc": {"likeViews": 1}
        }
    )
    cache_clear_reviews(review["ProductID"])
    return jsonify({"message": "Liked"})


@app.route("/reviews/<review_id>/dislike", methods=["POST"])
def dislike_review(review_id):
    user_id = request.json.get("UserID")
    review = review_collection.find_one({"_id": ObjectId(review_id)})
    if not review:
        return jsonify({"error": "Review not found"}), 404

    if user_id in review.get("dislikedUsers", []):
        return jsonify({"message": "Already disliked"}), 400

    if user_id in review.get("likedUsers", []):
        review_collection.update_one(
            {"_id": ObjectId(review_id)},
            {
                "$pull": {"likedUsers": user_id},
                "$inc": {"likeViews": -1}
            }
        )

    review_collection.update_one(
        {"_id": ObjectId(review_id)},
        {
            "$addToSet": {"dislikedUsers": user_id},
            "$inc": {"DislikeView": 1}
        }
    )
    cache_clear_reviews(review["ProductID"])
    return jsonify({"message": "Disliked"})

@app.route("/reviews/<review_id>/unlike", methods=["POST"])
def unlike_review(review_id):
    user_id = request.json.get("UserID")
    review = review_collection.find_one({"_id": ObjectId(review_id)})
    if not review or user_id not in review.get("likedUsers", []):
        return jsonify({"error": "Not liked yet"}), 400

    review_collection.update_one(
        {"_id": ObjectId(review_id)},
        {
            "$pull": {"likedUsers": user_id},
            "$inc": {"likeViews": -1}
        }
    )
    cache_clear_reviews(review["ProductID"])
    return jsonify({"message": "Unliked"})


@app.route("/reviews/<review_id>/undislike", methods=["POST"])
def undislike_review(review_id):
    user_id = request.json.get("UserID")
    review = review_collection.find_one({"_id": ObjectId(review_id)})
    if not review or user_id not in review.get("dislikedUsers", []):
        return jsonify({"error": "Not disliked yet"}), 400

    review_collection.update_one(
        {"_id": ObjectId(review_id)},
        {
            "$pull": {"dislikedUsers": user_id},
            "$inc": {"DislikeView": -1}
        }
    )
    cache_clear_reviews(review["ProductID"])
    return jsonify({"message": "Undisliked"})

@app.route("/reviews/<review_id>", methods=["DELETE"])
def delete_review(review_id):
    review = review_collection.find_one({"_id": ObjectId(review_id)})
    if not review:
        return jsonify({"error": "Review not found"}), 404

    review_collection.update_one(
        {"_id": ObjectId(review_id)},
        {"$set": {"isDeleted": True}}
    )
    cache_clear_reviews(review["ProductID"])
    return jsonify({"message": "Deleted (soft)"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
