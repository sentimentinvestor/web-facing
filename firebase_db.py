import firebase_admin
from firebase_admin import credentials, firestore
import time

cred = credentials.Certificate("admin_credentials/firebase-creds.json")
firebase_admin.initialize_app(cred)
firestore_db = firestore.client()


def db():
    return firestore_db


def get_ticker_info(ticker):
    return firestore_db.collection('tickers')\
            .document(ticker)\
            .get()


def get_recently_updated_tickers():
    max_age = time.time() - 3600
    return firestore_db.collection('tickers')\
        .where("AHI_timestamp", ">", max_age)\
        .get()


