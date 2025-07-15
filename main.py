import requests
import smtplib, ssl
from datetime import datetime, timezone
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

USER_ID = "default_user"

class PureGym:
    def __init__(self):
        self.access_token = None
        self.authed = False
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("WARNING: Telegram bot token or chat ID not found. Notifications will not be sent.")

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
                return people
            else:
                print(f"Failed to get attendance from API. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            print(f"Network error or API request failed: {e}")
            return None
        except Exception as e:
            print(f"An unexpected error occurred during attendance logging: {e}")
            return None

    def send_telegram_message(self, message):
        if not self.telegram_bot_token or not self.telegram_chat_id:
            print("Telegram bot token or chat ID not configured. Cannot send message.")
            return

        telegram_api_url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        try:
            response = requests.post(telegram_api_url, json=payload)
            response.raise_for_status()
            print("Telegram message sent successfully.")
        except requests.exceptions.RequestException as e:
            print(f"Failed to send Telegram message: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Telegram API response error: {e.response.text}")

    def get_notification_tracker(self):
        if not db:
            return {}
        tracker_ref = db.collection('user_settings').document(USER_ID)
        try:
            tracker_doc = tracker_ref.get()
            return tracker_doc.to_dict() if tracker_doc.exists else {}
        except Exception as e:
            print(f"Error getting notification tracker: {e}")
            return {}

    def update_notification_tracker(self, data):
        if not db:
            return
        tracker_ref = db.collection('user_settings').document(USER_ID)
        try:
            tracker_ref.set(data, merge=True)
        except Exception as e:
            print(f"Error updating notification tracker: {e}")

    def check_and_send_notification(self, current_people_count):
        if not db:
            print("Firestore not initialized. Cannot check for notifications.")
            return

        current_utc_time = datetime.now(timezone.utc)
        current_hour_utc = current_utc_time.hour
        current_date_utc = current_utc_time.date()

        # Notification parameters
        NOTIFICATION_THRESHOLD = 80
        NOTIFICATION_START_HOUR_UTC = 17  # 5 PM UTC
        NOTIFICATION_END_HOUR_UTC = 23  # 11 PM UTC

        if current_people_count is not None and current_people_count < NOTIFICATION_THRESHOLD:
            print(f"Current people count ({current_people_count}) is below threshold ({NOTIFICATION_THRESHOLD}).")

            if NOTIFICATION_START_HOUR_UTC <= current_hour_utc <= NOTIFICATION_END_HOUR_UTC:
                print(f"Current time ({current_hour_utc}:00 UTC) is within the 5 PM - 11 PM UTC window.")

                tracker_data = self.get_notification_tracker()
                last_notification_timestamp = tracker_data.get('last_notification_timestamp')

                notified_today = False
                if last_notification_timestamp:
                    # Convert Firestore Timestamp to datetime object and then to date
                    last_notification_date_utc = last_notification_timestamp.date()
                    if last_notification_date_utc == current_date_utc:
                        notified_today = True
                        print(f"Notification already sent today ({last_notification_date_utc}). Skipping.")

                if not notified_today:
                    notification_message = (
                        f"🚨 *PureGym Alert!* 🚨\n"
                        f"Attendance dropped to *{current_people_count}* people "
                        f"at {current_utc_time.strftime('%H:%M')} UTC.\n"
                        f"Perfect time to hit the gym!"
                    )
                    self.send_telegram_message(notification_message)

                    self.update_notification_tracker({
                        'last_notification_timestamp': datetime.now() ,
                        'last_notified_people_count': current_people_count
                    })
                    print("Notification status updated in Firestore.")
                else:
                    print("Conditions met, but notification already sent today.")
            else:
                print(
                    f"Current time ({current_hour_utc}:00 UTC) is outside the {NOTIFICATION_START_HOUR_UTC} PM - {NOTIFICATION_END_HOUR_UTC} PM UTC window.")
        else:
            print(
                f"Current people count ({current_people_count}) is not below {NOTIFICATION_THRESHOLD} or is None. No notification triggered.")


if __name__ == '__main__':
    load_dotenv()
    email = os.environ.get("PUREGYM_EMAIL")
    password = os.environ.get("PUREGYM_PASS")
    smtp_email = os.environ.get("SMTP_EMAIL")
    smtp_pass = os.environ.get("SMTP_PASS")

    puregym = PureGym()
    puregym.login(email,password)

    # Simplified to only perform logging and notification check
    if puregym.authed:
        people_in_gym = puregym.get_attendance()
        if people_in_gym is not None:
            puregym.check_and_send_notification(people_in_gym)
        else:
            print("Could not retrieve attendance, skipping notification check.")
    else:
        print("Login failed, skipping action.")


