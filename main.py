#main.py
from flask import Flask, jsonify, request
import requests
import time
from firebase_db import get_ticker_info, get_recently_updated_tickers, db

app = Flask(__name__)
ticker_search_counts = {}
CACHE_EXPIRY_TIME = 10 * 60  # 10 minutes in seconds
locally_cached_tickers = {}
locally_cached_trending = {}

@app.route('/')
def home():
  return jsonify({
    "service": "web-facing",
  })


@app.route('/get_trending')
def get_trending():
  start_time = time.time()
  limit = request.args.get("limit")
  if limit is None:
    limit = 6
  else:
    limit = int(limit)
  permitted_metrics = ["AHI", "SGP", "RHI", "sentiment", "tweet_mentions", "reddit_comment_mentions", "reddit_post_mentions", "stocktwits_post_mentions", "yahoo_finance_comment_mentions"]
  metric = request.args.get("metric")
  threshold_metric = request.args.get("threshold_metric")
  if threshold_metric is not None and threshold_metric not in permitted_metrics:
    return jsonify({
      "success": False,
      "error": f"unrecognized threshold metric, please choose one of {permitted_metrics}",
      "time_taken": time.time() - start_time
    })
  threshold = request.args.get("threshold")
  if threshold is not None:
    threshold = float(threshold)
  if metric is None:
    metric = 'AHI'
  elif metric not in permitted_metrics:
    return jsonify({
      "success": False,
      "error": f"unrecognized metric, please choose one of {permitted_metrics}",
      "time_taken": time.time() - start_time
    })

  trending = db().collection('trending').where('sorted_by', '==', metric).where('timestamp', '>', time.time() - 3600).get()
  if threshold and threshold_metric in permitted_metrics:
    trending = [doc for doc in trending if (doc.to_dict().get(threshold_metric) or -1) > threshold]
  tickers  = [
    {
      "ticker": doc.to_dict().get("ticker", ""),
      "rank": cnt,
      "info": doc.to_dict()
    }
    for cnt, doc in enumerate(trending[0:limit])
  ]

  return jsonify({
    "success": True,
    "quantity": len(tickers),
    "tickers": tickers,
    "time_taken": time.time() - start_time
  })


@app.route('/get_ticker_information')
def get_ticker_information():
  start_time = time.time()
  ticker = request.args.get("ticker")
  if ticker is None:
    return jsonify({
      "success": False,
      "time_taken": time.time() - start_time,
      "error": "no ticker given - please provide a ticker in the request params"
    })
  ticker_search_counts[ticker.upper()] = ticker_search_counts.get(ticker.upper(), 0) + 1

  if check_local_cache(ticker.upper()):
    return jsonify({
      "success": True,
      "type": "local_cache",
      "info": check_local_cache(ticker.upper()),
      "time_taken": time.time() - start_time
    })
  ticker_info = get_ticker_info(ticker.upper())
  if not ticker_info.exists:
    shallow_info = shallow_analysis(ticker.upper())
    update_local_cache(ticker.upper(), shallow_info)
    return jsonify({
      "success": True,
      "type": "shallow",
      "info": shallow_info,
      "time_taken": time.time() - start_time
    })
  update_local_cache(ticker, ticker_info.to_dict())
  return jsonify({
    "success": True,
    "type": "cached",
    "info": ticker_info.to_dict(),
    "time_taken": time.time() - start_time
  })


@app.route('/get_history')
def get_history():
  start_time = time.time()
  ticker = request.args.get("ticker")
  metric = request.args.get("metric")
  if not ticker:
    return jsonify({
      "success": False,
      "time_taken": time.time() - start_time,
      "error": "please provide a ticker in the 'ticker' params"
    })
  permitted_metrics = ["AHI", "SGP", "RHI", "sentiment", "tweet_sentiment", "tweet_mentions", "reddit_post_sentiment", "reddit_post_mentions", "reddit_comment_sentiment", "reddit_comment_mentions", "stocktwits_post_sentiment", "stocktwits_post_mentions", "yahoo_finance_comment_sentiment", "yahoo_finance_comment_mentions"]
  if metric not in permitted_metrics:
    return jsonify({
      "success": False,
      "time_taken": time.time() - start_time,
      "error": f"please provided a permitted metric (one of {permitted_metrics})"
    })

  history_doc = db().collection('tickers').document(ticker).collection('history').document(metric).get()
  if not history_doc.exists:
    return jsonify({
      "success": False,
      "time_taken": time.time() - start_time,
      "error": "history not found - either the ticker does not exist or the history has not been calculated yet"
    })
  history = history_doc.to_dict()["history"]

  return jsonify({
    "success": True,
    "time_taken": time.time() - start_time,
    "result": history
  })


@app.route('/get_reddit_post')
def get_reddit_post():
  start_time = time.time()
  tickers = get_recently_updated_tickers()
  ahi_hot = sorted(tickers, key=lambda x: x.to_dict()["AHI"], reverse=True)
  ahi_hot = [{
    "ticker": t.id,
    "AHI": t.to_dict()["AHI"]
  } for t in ahi_hot][0:100]
  reddit_hot = sorted(tickers, key=lambda x: x.to_dict().get("reddit_comment_mentions", 0), reverse=True)
  reddit_hot = [{
    "ticker": t.id,
    "reddit mentions": t.to_dict().get("reddit_comment_mentions")
  } for t in reddit_hot if t.to_dict().get("reddit_comment_mentions")][0:50]
  twitter_hot = sorted(tickers, key=lambda x: x.to_dict().get("tweet_mentions", 0), reverse=True)
  twitter_hot = [{
    "ticker": t.id,
    "tweets per second": t.to_dict().get("tweet_mentions")
  } for t in twitter_hot if t.to_dict().get("tweet_mentions")][0:50]
  return jsonify({
    "success": True,
    "time_taken": time.time() - start_time,
    "top_100": ahi_hot,
    "top_50_reddit": reddit_hot,
    "top_50_twitter": twitter_hot
  })


def check_local_cache(ticker):
  result = locally_cached_tickers.get(ticker, {"timestamp": 0})
  if (time.time() - result["timestamp"]) > CACHE_EXPIRY_TIME:
    return None
  else:
    return result["info"]


def update_local_cache(ticker, info):
  locally_cached_tickers[ticker] = {
    "timestamp": time.time(),
    "info": info
  }


@app.route('/get_and_refresh_ticker_search_counts')
def get_and_refresh_ticker_search_counts():
  start_time = time.time()
  counts = ticker_search_counts.copy()
  ticker_search_counts.clear()
  return jsonify({
    "success": True,
    "ticker_search_counts": counts,
    "time_taken": time.time() - start_time
  })


if __name__ == '__main__':
  app.run()