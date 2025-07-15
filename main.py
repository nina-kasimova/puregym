import requests
import smtplib, ssl
from datetime import datetime
from dotenv import load_dotenv
import os
import csv
import schedule
import time
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import json


try:
    # Attempt to load from environment variable first (for CI/CD)
    service_account_info = os.environ.get("FIREBASE_SERVICE_ACCOUNT_KEY")
    if service_account_info:
        cred = credentials.Certificate(json.loads(service_account_info))
    else:
        # fallback for local development
        cred = credentials.Certificate(
            "puregym-b4080-firebase-adminsdk-fbsvc-3d75c56029.json")

    firebase_admin.initialize_app(cred)
    db = firestore.client()
    print("Firestore initialised successfully.")
except Exception as e:
    print(f"Error initialising Firestore: {e}")
    db = None  # Set db to None if initialization fails


class PureGym:
    def __init__(self):
        self.access_token = None
        self.authed = False

    def login(self, email, pin):
        headers = {'Content-Type': 'application/x-www-form-urlencoded',
                   'User-Agent': 'PureGym/6455 CFNetwork/3826.500.131 Darwin/24.5.0'}
        data = {
            'grant_type': 'password',
            'username': email,
            'password': pin,
            'scope': 'pgcapi',
            'client_id': 'ro.client'
        }
        auth_url = "https://auth.puregym.com/connect/token"

        response = requests.post(auth_url, headers=headers, data=data)

        if response.status_code == 200:
            self.access_token = f"Bearer " + response.json()["access_token"]
            self.authed = True

    def get_attendance(self, file_name="gym_log.csv"):
        if not db:
            print("Firestore not initialized. Cannot log attendance.")
            return
        url = "https://capi.puregym.com/api/v2/gymSessions/gym?gymId=75"

        headers = {
            "Authorization": self.access_token,
            "accept": "application/json",
            "user-agent": "PureGym/6455 CFNetwork/3826.500.131 Darwin/24.5.0",
            "x-purebrand": "PGUK"
        }

        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                data = response.json()
                now = datetime.now()  # Get datetime object
                people = data['TotalPeopleInGym']

                # Add data to a Firestore collection
                doc_ref = db.collection('gym_attendance').add({
                    'timestamp': now,  # Firestore can store datetime objects
                    'people_in_gym': people
                })
                print(
                    f"Logged to Firestore: {now.strftime('%Y-%m-%d %H:%M:%S')} → {people} people. Document ID: {doc_ref[1].id}")
            else:
                print(f"Failed to get attendance from API. Status code: {response.status_code}")
                print(f"Response: {response.text}")
        except requests.exceptions.RequestException as e:
            print(f"Network error or API request failed: {e}")
        except Exception as e:
            print(f"An unexpected error occurred during attendance logging: {e}")

    def sendEmailNotif(self, email, password):
        port = 465  # For SSL
        smtp_server = "smtp.gmail.com"
        sender_email = email  # Enter your address
        password = password
        receiver_email = "nina.kasimova@gmail.com"  # Enter receiver address
        message = f"There are {self.get_attendance()} people at the gym "

        # Create a secure SSL context
        context = ssl.create_default_context()

        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
            server.login(sender_email, password)
            server.sendmail(sender_email, receiver_email, message)
            print("email sent")


if __name__ == '__main__':
    load_dotenv()
    email = os.environ.get("PUREGYM_EMAIL")
    password = os.environ.get("PUREGYM_PASS")
    smtp_email = os.environ.get("SMTP_EMAIL")
    smtp_pass = os.environ.get("SMTP_PASS")

    puregym = PureGym()
    puregym.login(email,password)

    if puregym.authed:
        puregym.get_attendance()

    else:
        print("Login failed, attendance logging skipped.")


