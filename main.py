import requests
import smtplib, ssl
from datetime import datetime
from dotenv import load_dotenv
import os
import csv
import schedule
import time


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
        print("response ", response)

    def get_attendance(self, file_name="gym_log.csv"):
        url = "https://capi.puregym.com/api/v2/gymSessions/gym?gymId=75"

        headers = {
            "Authorization": self.access_token,
            "accept": "application/json",
            "user-agent": "PureGym/6455 CFNetwork/3826.500.131 Darwin/24.5.0",
            "x-purebrand": "PGUK"
        }

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            people = data['TotalPeopleInGym']

            with open(file_name, mode='a', newline='') as file:
                writer = csv.writer(file)
                if os.stat(file_name).st_size == 0:
                    writer.writerow(["timestamp", "people_in_gym"])
                writer.writerow([now, people])
            print(f"Logged: {now} → {people} people")
        else:
            print("Failed to log attendance")

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

    # only start if login was successful
    if puregym.authed:

        def job():
            puregym.get_attendance()


        schedule.every(30).minutes.do(job)

        while True:
            schedule.run_pending()
            time.sleep(1)


