import telebot
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import json
import base64
import os
import threading
import jdatetime
from flask import Flask, request
import telegram
#----------------------------------------------------------------------------------------------
app = Flask(__name__)
DATA_FILE = "notes.json"
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
bot=telebot.TeleBot(TOKEN)
#---------------------------------------------------------------------------------------------
class Task:
    def __init__(self, component, name, description, situation, deaddate, setdate):
        self.component = component
        self.name = name
        self.description = description
        self.situation = situation
        self.setdate = setdate
        self.deaddate=deaddate
        self.done_time = None  # زمان انجام شدن
        if deaddate != "امشب ساعت 24:00":
            if deaddate.strip().startswith("14"):
                # 👇 فرض می‌کنیم فرمت ورودی شمسیه: YYYY/MM/DD HH:MM
                jalali_dt = jdatetime.datetime.strptime(deaddate, "%Y/%m/%d %H:%M")
                self.deaddate = jalali_dt.strftime("%Y/%m/%d %H:%M")  # بدون تبدیل
            if deaddate.strip().startswith("20"):
                # 👇 فرض بر اینکه فرمت میلادیه: YYYY-MM-DD HH:MM
                gregorian_dt = datetime.strptime(deaddate, "%Y/%m/%d %H:%M")
                gregorian_dt = gregorian_dt.replace(tzinfo=ZoneInfo("Asia/Tehran"))
                jalali_dt = jdatetime.datetime.fromgregorian(datetime=gregorian_dt)
                self.deaddate = jalali_dt.strftime("%Y/%m/%d %H:%M")
            else: 
                if "موعد تویحل وارده صحیح نبوده" in deaddate:
                    self.deaddate = deaddate
                else:
                    self.deaddate=deaddate +"    "+ ":فرمت موعد تویحل وارده صحیح نبوده و با فرمت معمولی ذخیره شده فرمت درست\n YYYY/MM/DD HH:MM میباشد"
    
    def to_dict(self):
        return {
            "component": self.component,
            "name": self.name,
            "description": self.description,
            "situation": self.situation,
            "deaddate": self.deaddate,
            "setdate": self.setdate,
            "done_time": self.done_time  # ذخیره حتی اگر None باشه
    }


    def __str__(self):
        base = f"📌 نام تسک: {self.name}\n | بخش: {self.component}\n | توضیحات: {self.description}\n |وضعیت: {self.situation}\n |  موعد تحویل: {self.deaddate}\n | تاریخ ثبت: {self.setdate}"
        if hasattr(self, "done_time") and self.done_time:
            base += f"\n ✅ زمان انجام: {self.done_time}"
        return base + "\n -------------------------------------------------"

class Daily(Task):
    def __init__(self, component, name, description, situation=None, deaddate=None, setdate=None):
        # مقداردهی پیش‌فرض اگر چیزی نرسیده بود
        if setdate is None:
            setdate = "امروز ساعت 00:00"
        if deaddate is None:
            deaddate = "امشب ساعت 24:00"
        if situation is None:
            situation="انجام نشده"
        super().__init__(component,name,description,situation,deaddate,setdate)
    def __str__(self):
        return super().__str__()

#----------------------------------------------------------------------------------------
user_tasks = {}
user_daily={}
pending_deletions={}
user_reminders={}
last_sent_minute = {}

#-------------------------------------------------------------------------------------
start_message = """
👋 خوش اومدی به بات مدیریت وظایف!
اینجا می‌تونی تسک‌هات رو ثبت، پیگیری، علامت‌گذاری، ذخیره و حذف کنی—با یه سیستم یادآور هوشمند 😍
اینجا تسک ها دو دسته اند دسته اول تسک ها و دسته دوم تسک های روزانه
  تسک ها برای خودشون تاریخ ثبت و موعد انجام دارند اما تسک های روزانه وقتی ثبت میشوند هر روز ساعت 12 شب دوباره تولید میشوند، چه انجام شده باشند چه نشده باشند
---
افزودن تسک:
📥 /addtask
➕ افزودن تسک جدید با فرمت:
`/addtask موعد انجام,وضعیت,توضیحات،نام،بخش`

☀️ /adddaily
➕ افزودن تسک روزانه با فرمت:
`/adddaily موعد انجام,وضعیت,توضیحات،نام،بخش`
---
نمایش تسک:
📋 /showtasks
📌 نمایش همه‌ی تسک‌های کلی ثبت‌شده

📋 /showdaily
📌 نمایش لیست تسک‌های روزانه

📋 /showall
📌 نمایش لیست همه تسک‌ها
---
برای تیک زدن و تغییر وضعیت تسک ها به حالت انجام شده باید از دستور /donetask و /donedaily استفاده کنید.
✅ /donetask
🎉 علامت‌گذاری یک تسک کلی به‌عنوان انجام‌شده
مثال: `/done 2`
✅ /donedaily
🎉 علامت‌گذاری یک تسک روزانه به‌عنوان انجام‌شده
مثال: `/donedaily 1`
---
🗑️ /deletetask
🗑️ /deletetask n
🗑️ /deletedaily
🗑️ /deletedaily n
حذف یک تسک مشخص یا همه تسک‌ها
مثال‌ها: `/delete 3` یا فقط `/delete`
---
⏰ /reminder
تنظیم یادآور روزانه:
- `/reminder on` → فعال‌سازی یادآور (بعدش ساعت رو وارد کن)
- `/reminder 04:30` → فعال‌سازی با زمان مشخص
- `/reminder off` → غیرفعال‌سازی یادآور
---
با دستور /save میتوانید همه اطلاعات را ذخیره کنید تا با در صورت ایجاد اختلال اطلاعات ذخیر شده باشد
*** حتما بعد از پایان تغییرات /save را وارد کنید
*** اگر اطلاعات در دسترس نیستند با وارد کردن دستور /load میتوانید اطلاعات را بارگذاری کنین
💾 /save
📦 ذخیره‌سازی همه‌ی داده‌ها (تسک‌ها، دیلی‌ها، یادآورها)
📥 /load
📤 بارگذاری داده‌ها از فایل ذخیره‌شده
"""

#----------------------------------------------------------------
@bot.message_handler(commands=["start"])
def start(message):
    sent = bot.send_message(message.chat.id, start_message)
    try:
        bot.pin_chat_message(message.chat.id, sent.message_id)
    except Exception as e:
        print(f"❌ خطا در پین کردن پیام راهنما: {e}")

#-------------------------------------------------------------------------------------------
@bot.message_handler(commands=["reminder"])
def set_reminder(message):
    user_id = str(message.from_user.id)
    text = message.text.replace("/reminder", "").strip()

    if text.lower() == "off":
        user_reminders.pop(user_id, None)
        bot.reply_to(message, "🔕 یادآور غیرفعال شد.")
        return

    if text.lower() == "on":
        bot.reply_to(message, "⌚ لطفاً ساعت رو بنویس (مثلاً: /reminder 14:30)")
        return

    if ":" not in text:
        bot.reply_to(message, "❌ فرمت ساعت درست نیست. مثل: 09:00 یا 21:15")
        return

    user_reminders[user_id] = text
    bot.reply_to(message, f"✅ یادآور فعال شد برای ساعت {text} هر روز.")

#-----------------------------------------------------------------------------------------
@bot.message_handler(commands=["addtask"])
def addtask(message):
    user_id = str(message.from_user.id)
    parts = message.text.replace("/addtask", "").strip().split(",")
    if len(parts)!=5:
        bot.reply_to(message, "❌ لطفاً فرمت درست رو رعایت کن:\n/addtask موعد انجام, وضعیت , توضیحات , اسم , بخش")
        return
    timestamp=message.date
    readabletime = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    component,name,description,situation,deadtime = [p.strip() for p in parts]
    new_task=Task(component,name,description,situation,deadtime,readabletime)
    user_tasks.setdefault(user_id, []).append(new_task)
    bot.reply_to(message, f"✅ یادداشت ذخیره شد:\n {new_task}")

@bot.message_handler(commands=["adddaily"])
def adddaily(message):
    user_id = str(message.from_user.id)
    parts = message.text.replace("/adddaily", "").strip().split(",")
    if len(parts)!=3:
        bot.reply_to(message, "❌ لطفاً فرمت درست رو رعایت کن:\n/addtdaily   توضیحات , اسم , بخش")
        return
    component,name,description = [p.strip() for p in parts]
    new_daily=Daily(component,name,description)
    user_daily.setdefault(user_id, []).append(new_daily)
    bot.reply_to(message, f"✅ تسک روزانه ذخیره شد:\n {new_daily}")


#---------------------------------------------------------------------------------------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
REPO = "JavadADB/tasks-notes"  # مثلاً jjdev/task-storage
FILE_PATH = "notes.json"
BRANCH = "main"

def upload_to_github(content_json):
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    
    # بررسی وجود فایل برای گرفتن SHA
    response = requests.get(url, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}"
    })
    
    sha = None
    if response.status_code == 200:
        sha = response.json()["sha"]
    
    encoded_content = base64.b64encode(content_json.encode()).decode()
    
    payload = {
        "message": "update notes.json",
        "content": encoded_content,
        "branch": BRANCH
    }
    if sha:
        payload["sha"] = sha

    r = requests.put(url, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}"
    }, json=payload)

    return r.status_code in [200, 201]


@bot.message_handler(commands=["save"])
def save_all(message):
    serializable_data = {
        "tasks": {
            user_id: [task.to_dict() for task_list in user_tasks.values() for task in task_list]
            for user_id in user_tasks
        },
        "daily": {
            user_id: [daily.to_dict() for daily in user_daily.get(user_id, [])]
            for user_id in user_daily
        },
        "reminders": user_reminders,
        "last_sent": last_sent_minute
    }

    json_str = json.dumps(serializable_data, ensure_ascii=False, indent=2)
    success = upload_to_github(json_str)

    if success:
        bot.reply_to(message, "✅ داده‌ها با موفقیت در GitHub ذخیره شدند.")
    else:
        bot.reply_to(message, "❌ خطا در ذخیره‌سازی در GitHub.")


def download_from_github():
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    
    r = requests.get(url, headers={
        "Authorization": f"Bearer {GITHUB_TOKEN}"
    })
    
    if r.status_code == 200:
        content = r.json()["content"]
        decoded = base64.b64decode(content).decode()
        return json.loads(decoded)
    else:
        return None


@bot.message_handler(commands=["load"])
def load_all(message):
    global user_tasks, user_daily, user_reminders, last_sent_minute

    raw = download_from_github()
    if raw is None:
        bot.reply_to(message, "❌ فایل notes.json در GitHub پیدا نشد.")
        return

    user_tasks = {
        user_id: [Task(**{k: v for k, v in task_dict.items() if k != "done_time"}) for task_dict in task_list]
        for user_id, task_list in raw.get("tasks", {}).items()
    }

    user_daily = {}
    for user_id, daily_list in raw.get("daily", {}).items():
        cleaned_list = []
        for daily_dict in daily_list:
            daily_dict.pop("done_time", None)
            cleaned_list.append(Daily(**daily_dict))
        user_daily[user_id] = cleaned_list

    user_reminders = raw.get("reminders", {})
    last_sent_minute = raw.get("last_sent", {})

    bot.reply_to(message, "📥 داده‌ها با موفقیت از GitHub بارگذاری شدند.")

#-------------------------------------------------------------------------------------------------------
@bot.message_handler(commands=["showtasks"])
def showtasks(message):
    user_id=str(message.from_user.id)
    tasks=user_tasks.get(user_id,[])
    if not tasks:
        bot.reply_to(message,"هیج تسکی ثبت نشده است")
    else:
        response = "🗂️ لیست کارهات:\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(tasks)])
        bot.reply_to(message, response)

@bot.message_handler(commands=["showall"])
def show_all(message):
    user_id=str(message.from_user.id)
    tasks = user_tasks.get(user_id, [])
    dailys = user_daily.get(user_id, [])

    response = "⏰ همه تسک های شما:\n\n"

    if tasks:
        response += "📋 تسک‌های کلی:\n"
        for i, task in enumerate(tasks):
            response += f"{i+1}. {task}\n"
            response += "\n"

    if dailys:
        response += "☀️ تسک‌های روزانه:\n"
        for i, d in enumerate(dailys):
            response += f"{i+1}. {d}\n"

    if not tasks and not dailys:
        response = "📭 هیچ تسکی ثبت نشده است."

    bot.send_message(int(user_id), response)

@bot.message_handler(commands=["showdaily"])
def showdaily(message):
    user_id=str(message.from_user.id)
    dailys=user_daily.get(user_id,[])
    if not dailys:
        bot.reply_to(message,"هیج تسک روزانه ای ثبت نشده است")
    else:
        response = "🗂️ لیست تسک های روزانه:\n" + "\n".join([f"{i+1}. {t}" for i, t in enumerate(dailys)])
        bot.reply_to(message, response)

#-----------------------------------------------------------------------------------------------------------------
@bot.message_handler(commands=["deletetask"])
def delete(message):
    user_id = str(message.from_user.id)
    tasks = user_tasks.get(user_id, [])
    parts = message.text.replace("/deletetask", "").strip()

    # حذف همه
    if parts == "":
        if not tasks:
            bot.reply_to(message, "📭 هیچ تسکی برای حذف وجود نداره.")
            return

        pending_deletions[user_id] = None
        bot.reply_to(message, "❗ آیا مطمئنی که همه‌ی تسک‌ها حذف بشن؟ /yestask بزن اگه مطمئنی.")

    # حذف تکی
    elif parts.isdigit():
        index = int(parts) - 1
        if index < 0 or index >= len(tasks):
            bot.reply_to(message, "❌ شماره تسک معتبر نیست.")
            return

        pending_deletions[user_id] = index
        bot.reply_to(message, f"❗ آیا مطمئنی که تسک شماره {index+1} حذف بشه؟ /yestask بزن اگه مطمئنی.")

    else:
        bot.reply_to(message, "⚠️ لطفاً یا فقط بنویس `/deletetask` یا یه عدد مثل `/deletetask 2`")

@bot.message_handler(commands=["yestask"])
def confirm_deletion(message):
    user_id = str(message.from_user.id)
    request = pending_deletions.get(user_id)

    if request is None:
        # بررسی کنیم آیا واقعاً منظور حذف همه بوده
        if message.text.strip() == "/yestask all":
            user_tasks[user_id] = []
            bot.reply_to(message, "🗑️ همه‌ی تسک‌ها پاک شدند.")
        else:
            bot.reply_to(message, "❗ برای حذف همه، باید بنویسی: /yestask all")
        return
    elif isinstance(request, int):
        # حذف تکی
        tasks = user_tasks.get(user_id, [])
        if request >= len(tasks):
            bot.reply_to(message, "❌ تسک مورد نظر دیگه وجود نداره.")
        else:
            removed = tasks.pop(request)
            bot.reply_to(message, f"🗑️ تسک حذف شد:\n{removed}")
    else:
        bot.reply_to(message, "❌ هیچ درخواست حذف معتبری ثبت نشده.")

    pending_deletions.pop(user_id, None)  # پاک کردن درخواست

@bot.message_handler(commands=["deletedaily"])
def delete(message):
    user_id = str(message.from_user.id)
    dailys = user_daily.get(user_id, [])
    parts = message.text.replace("/deletedaily", "").strip()

    # حذف همه
    if parts == "":
        if not dailys:
            bot.reply_to(message, "📭 هیچ تسک روزانه ای برای حذف وجود نداره.")
            return

        pending_deletions[user_id] = None
        bot.reply_to(message, "❗ آیا مطمئنی که همه‌ی تسک‌های روزانه حذف بشن؟ /yesdaily بزن اگه مطمئنی.")

    # حذف تکی
    elif parts.isdigit():
        index = int(parts) - 1
        if index < 0 or index >= len(dailys):
            bot.reply_to(message, "❌ شماره تسک روزانه معتبر نیست.")
            return

        pending_deletions[user_id] = index
        bot.reply_to(message, f"❗ آیا مطمئنی که تسک روزانه شماره {index+1} حذف بشه؟ /yesdaily بزن اگه مطمئنی.")

    else:
        bot.reply_to(message, "⚠️ لطفاً یا فقط بنویس `/deletedaily` یا یه عدد مثل `/deletedayli 2`")

@bot.message_handler(commands=["yesdaily"])
def confirm_deletion(message):
    user_id = str(message.from_user.id)
    request = pending_deletions.get(user_id)

    if request is None:
        # بررسی کنیم آیا واقعاً منظور حذف همه بوده
        if message.text.strip() == "/yesdaily all":
            user_daily[user_id] = []
            bot.reply_to(message, "🗑️ همه‌ی تسک‌های روزانه پاک شدند.")
        else:
            bot.reply_to(message, "❗ برای حذف همه، باید بنویسی: /yesdaily all")
        return
    elif isinstance(request, int):
        # حذف تکی
        dailys = user_daily.get(user_id, [])
        if request >= len(dailys):
            bot.reply_to(message, "❌ تسک روزانه مورد نظر دیگه وجود نداره.")
        else:
            removed = dailys.pop(request)
            bot.reply_to(message, f"🗑️ تسک روزانه حذف شد:\n{removed}")
    else:
        bot.reply_to(message, "❌ هیچ درخواست حذف معتبری ثبت نشده.")

    pending_deletions.pop(user_id, None)  # پاک کردن درخواست

#----------------------------------------------------------------------------------------
@bot.message_handler(commands=["donetask"])
def mark_done(message):
    user_id = str(message.from_user.id)
    tasks = user_tasks.get(user_id, [])
    parts = message.text.replace("/donetask", "").strip()

    if not parts.isdigit():
        bot.reply_to(message, "❌ لطفاً شماره تسک رو به‌درستی وارد کن. مثل: /donetask 2")
        return

    index = int(parts) - 1
    if index < 0 or index >= len(tasks):
        bot.reply_to(message, "❌ شماره تسک معتبر نیست.")
        return

    tasks[index].situation = "✅ انجام‌شده"
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    tasks[index].done_time = now.strftime("%Y-%m-%d %H:%M:%S")
    bot.reply_to(message, f"🎉 تسک به حالت انجام‌شده تغییر یافت:\n{tasks[index]}")

@bot.message_handler(commands=["donedaily"])
def mark_daily_done(message):
    user_id = str(message.from_user.id)
    dailys = user_daily.get(user_id, [])
    parts = message.text.replace("/donedaily", "").strip()

    if not parts.isdigit():
        bot.reply_to(message, "❌ لطفاً شماره تسک روزانه رو درست وارد کن. مثل: /donedaily 1")
        return

    index = int(parts) - 1
    if index < 0 or index >= len(dailys):
        bot.reply_to(message, "❌ شماره تسک روزانه معتبر نیست.")
        return

    dailys[index].situation = "✅ انجام‌شده"
    now = datetime.now(ZoneInfo("Asia/Tehran"))
    dailys[index].done_time = now.strftime("%Y-%m-%d %H:%M:%S")
    bot.reply_to(message, f"🎉 تسک روزانه انجام شد:\n{dailys[index]}")

#--------------------------------------------------------------------------------------------------------
@bot.message_handler(commands=["until"])
def handle_pending_until(message):
    user_id = str(message.from_user.id)
    chat_id = message.chat.id

    # ⏱️ استخراج تاریخ از پیام کاربر
    date_text = message.text.replace("/until", "").strip()

    # 📅 تبدیل تاریخ ورودی کاربر
    try:
        if date_text.startswith(("13", "14")):
            jalali = jdatetime.datetime.strptime(date_text, "%Y/%m/%d %H:%M")
            limit_dt = jalali.togregorian().replace(tzinfo=ZoneInfo("Asia/Tehran"))
        else:
            limit_dt = datetime.strptime(date_text, "%Y/%m/%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Tehran"))
    except Exception as e:
        bot.send_message(user_id, f"❌ فرمت تاریخ معتبر نیست:\nمثال‌ها:\n- 1404/04/25 13:25\n- 2025-07-16 13:25")
        return

    # 🎯 فیلتر تسک‌ها
    results = []

    for task in user_tasks.get(user_id, []):
        if task.situation != "✅ انجام‌شده":
            try:
                # تبدیل تاریخ تسک به datetime
                task_dt = jdatetime.datetime.strptime(task.deaddate, "%Y/%m/%d %H:%M").togregorian().replace(tzinfo=ZoneInfo("Asia/Tehran"))
                if task_dt <= limit_dt:
                    results.append(task)
            except:
                continue

    # 📩 ارسال نتیجه
    if not results:
        bot.send_message(user_id, "✅ هیچ تسک انجام‌نشده‌ای تا اون تاریخ پیدا نشد.")
    else:
        bot.send_message(user_id, f"📌 تسک‌های انجام‌نشده تا {date_text}:")
        for idx, task in enumerate(results, 1):
            bot.send_message(user_id, f"🔹 تسک شماره {idx}:\n{task}")
#-------------------------------------------------------------------------------------------------------
def reminder_loop():
    last_sent_minute = {}

    while True:
        now = datetime.now(ZoneInfo("Asia/Tehran"))
        current_minute = now.strftime("%H:%M")

        for user_id, remind_time in user_reminders.items():
            if remind_time == current_minute and last_sent_minute.get(user_id) != current_minute:
                try:
                    tasks = user_tasks.get(user_id, [])
                    dailys = user_daily.get(user_id, [])

                    response = "⏰ یادآوری تسک‌های انجام نشده شما:\n\n"

                    if tasks:
                        response += "📋 تسک‌های کلی:\n"
                        for i, task in enumerate(tasks):
                            if task.situation != "✅ انجام‌شده":
                                response += f"{i+1}. {task}\n"
                                response += "\n"

                    if dailys:
                        response += "☀️ تسک‌های روزانه:\n"
                        for i, d in enumerate(dailys):
                            if d.situation != "✅ انجام‌شده":

                                response += f"{i+1}. {d}\n"

                    if not tasks and not dailys:
                        response = "📭 هیچ تسکی انجام نشده‌ای ثبت نشده است."

                    bot.send_message(int(user_id), response)
                    last_sent_minute[user_id] = current_minute
                except Exception as e:
                    print(f"❌ خطا در ارسال پیام یادآور: {e}")

        time.sleep(5)
reminder_thread = threading.Thread(target=reminder_loop)
reminder_thread.daemon = True
reminder_thread.start()

def daily_loop():
    last_reset_date = None  # تاریخ آخرین ریست

    while True:
        now = datetime.now(ZoneInfo("Asia/Tehran"))
        current_minute = now.strftime("%H:%M")
        today_date = now.strftime("%Y-%m-%d")
        update_hour = "00:01"  # ساعت موردنظر برای ریست

        # ترکیب تاریخ + ساعت برای کنترل اجرای روزانه
        if current_minute == update_hour:
            for user_id, dailys in user_daily.items():
                updated_list = []
                for d in dailys:
                    # ریست وضعیت یا ساخت دوباره شیء دیلی با حالت اولیه
                    reset_daily = Daily(d.component, d.name, d.description)
                    updated_list.append(reset_daily)
                user_daily[user_id] = updated_list

                try:
                    bot.send_message(int(user_id), "☀️ تسک‌های روزانه برای امروز ریست شدند.")
                except Exception as e:
                    print(f"❌ خطا در ارسال پیام برای {user_id}: {type(e).__name__} → {e}")

            last_reset_date = today_date  # ذخیره روزی که ریست شده

        time.sleep(30)
daily_thread = threading.Thread(target=daily_loop)
daily_thread.daemon = True
daily_thread.start()

@bot.message_handler(commands=["redaily"])
def reset_daily(message):
    try:
        for user_id, dailys in user_daily.items():
            updated_list = []
            for d in dailys:
                # ریست وضعیت یا ساخت دوباره شیء دیلی با حالت اولیه
                reset_daily = Daily(d.component, d.name, d.description)
                updated_list.append(reset_daily)
                user_daily[user_id] = updated_list
        bot.send_message(int(user_id), "☀️ تسک‌های روزانه برای امروز ریست شدند.")
    except Exception as e:
        print(f"❌ خطا در ریست کردن تسک های روزانه برای ")

# تغییرات اصلی در بخش اجرا:
@app.route('/' + TOKEN, methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 400

def run_flask():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

if __name__ == '__main__':
    # حذف وب‌هوک قبلی (اگر وجود داشت)
    bot.remove_webhook()
    time.sleep(1)
    
    # تنظیم وب‌هوک جدید
    WEBHOOK_URL = f'https://greentick-bot.onrender.com/{TOKEN}'
    bot.set_webhook(url=WEBHOOK_URL)
    
    # شروع threadهای کمکی
    reminder_thread = threading.Thread(target=reminder_loop)
    reminder_thread.daemon = True
    reminder_thread.start()
    
    daily_thread = threading.Thread(target=daily_loop)
    daily_thread.daemon = True
    daily_thread.start()
    
    # اجرای سرور Flask در thread اصلی
    run_flask()



