import time
from telegram_notifications import send_telegram_notification

print("Sending test notification to phone...")
send_telegram_notification("🎯 <b>Connection check!</b>\nHello! Your background notifier is working perfectly.")

time.sleep(2)
print("Done! Check your Telegram.")