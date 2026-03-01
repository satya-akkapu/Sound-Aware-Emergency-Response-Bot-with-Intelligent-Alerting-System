from sms_alert import send_sms

send_sms(
    "+919381966838",   # verified number
    "Test User",
    "https://www.google.com/maps?q=18.1067,83.3956"
)

print("Done")
