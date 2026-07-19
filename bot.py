import os
import json
import random
import asyncio
import aiohttp
from colorama import init, Fore, Style
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, MessageHandler, ContextTypes, filters
)

# --- تهيئة الألوان ---
init(autoreset=True)
BRIGHT_YELLOW = Style.BRIGHT + Fore.YELLOW
WHITE = Fore.WHITE
CYAN = Fore.CYAN
ERROR_COLOR = Style.BRIGHT + Fore.RED
SUCCESS_COLOR = Style.BRIGHT + Fore.GREEN
WARNING_COLOR = Style.BRIGHT + Fore.YELLOW
INFO_COLOR = Style.BRIGHT + Fore.BLUE
RESET = Style.RESET_ALL
SEPARATOR = BRIGHT_YELLOW + Style.BRIGHT + "=" * 80 + RESET

# --- الإعدادات ---
AUTH_URL = 'https://mobile.vodafone.com.eg/auth/realms/vf-realm/protocol/openid-connect/token'
FAMILY_API_URL = "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"
ACCEPT_INVITATION_URL = "https://mobile.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"
REMOVE_MEMBER_URL = "https://web.vodafone.com.eg/services/dxl/cg/customerGroupAPI/customerGroup"

CLIENT_ID = 'ana-vodafone-app'
CLIENT_SECRET = '95fd95fb-7489-4958-8ae6-d31a525cd20a'

USER_AGENTS_APPLE = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
]
USER_AGENT_MOBILE = 'VodafoneEG/5.5.1 (iPhone; iOS 16.6; Scale/3.00)'

# --- States للـ ConversationHandler ---
(
    OWNER_NUMBER, OWNER_PASSWORD, MEMBER_NUMBER, MEMBER_PASSWORD,
    QUOTA_SELECT, CONFIRM_ACCEPT
) = range(6)

# --- دالة المصادقة ---
async def authenticate_vodafone_async(session, username, password, is_mobile_agent=False):
    data = {
        'grant_type': 'password',
        'username': username,
        'password': password,
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Content-Type': 'application/x-www-form-urlencoded',
        'User-Agent': USER_AGENT_MOBILE if is_mobile_agent else random.choice(USER_AGENTS_APPLE)
    }
    try:
        async with session.post(AUTH_URL, data=data, headers=headers, timeout=30) as response:
            if response.status == 200:
                auth_response_json = await response.json()
                if 'access_token' in auth_response_json:
                    return auth_response_json['access_token']
    except Exception as e:
        print(f"Auth error: {e}")
    return None

# --- دالة إضافة عضو ---
async def add_family_member_async(session, access_token, owner_number, member_number, quota_value):
    payload = json.dumps({
        "name": "FlexFamily", "type": "SendInvitation", "category": [
            {"value": "523", "listHierarchyId": "PackageID"}, {"value": "47", "listHierarchyId": "TemplateID"},
            {"value": "523", "listHierarchyId": "TierID"}, {"value": "percentage", "listHierarchyId": "familybehavior"}
        ], "parts": {"member": [
            {"id": [{"value": owner_number, "schemeName": "MSISDN"}], "type": "Owner"},
            {"id": [{"value": member_number, "schemeName": "MSISDN"}], "type": "Member"}
        ], "characteristicsValue": {
            "characteristicsValue": [{"characteristicName": "quotaDist1", "value": str(quota_value), "type": "percentage"}]
        }}
    })
    headers = {
        'User-Agent': random.choice(USER_AGENTS_APPLE),
        'Accept': "application/json",
        'Content-Type': "application/json",
        'Authorization': f"Bearer {access_token}",
        'msisdn': owner_number,
        'clientId': "WebsiteConsumer",
        'Origin': "https://web.vodafone.com.eg",
        'Referer': "https://web.vodafone.com.eg/spa/familySharing",
    }
    try:
        async with session.post(FAMILY_API_URL, data=payload, headers=headers, timeout=45) as response:
            return response.status in [200, 201, 204], response.status
    except Exception as e:
        return False, 0

# --- دالة حذف عضو ---
async def remove_family_member_async(session, access_token, owner_number, member_number):
    payload = {
        "name": "FlexFamily",
        "type": "FamilyRemoveMember",
        "category": [{"value": "47", "listHierarchyId": "TemplateID"}],
        "parts": {
            "member": [
                {"id": [{"value": owner_number, "schemeName": "MSISDN"}], "type": "Owner"},
                {"id": [{"value": member_number, "schemeName": "MSISDN"}], "type": "Member"}
            ],
            "characteristicsValue": {
                "characteristicsValue": [
                    {"characteristicName": "Disconnect", "value": "0"},
                    {"characteristicName": "LastMemberDeletion", "value": "1"}
                ]
            }
        }
    }
    headers = {
        'Authorization': f"Bearer {access_token}",
        'Content-Type': "application/json",
        'msisdn': owner_number,
        'User-Agent': random.choice(USER_AGENTS_APPLE),
        'Accept': "application/json",
        'Origin': "https://web.vodafone.com.eg",
        'Referer': "https://web.vodafone.com.eg/spa/familySharing",
        'clientId': "WebsiteConsumer"
    }
    try:
        async with session.patch(REMOVE_MEMBER_URL, data=json.dumps(payload), headers=headers, timeout=30) as response:
            return response.status in [200, 201, 204, 404]
    except:
        return False

# --- دالة قبول الدعوة ---
async def accept_invitation_async(session, owner_number, member_number, member_password):
    access_token = await authenticate_vodafone_async(session, member_number, member_password, is_mobile_agent=True)
    if not access_token:
        return False
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "msisdn": member_number,
        "Accept": "application/json",
        "Accept-Language": "ar",
        "Content-Type": "application/json; charset=UTF-8",
        "User-Agent": USER_AGENT_MOBILE,
        "clientId": "AnaVodafoneAndroid",
        "api-version": "v2",
        "useCase": "MIProfile",
    }
    data = {
        "category": [{"listHierarchyId": "TemplateID", "value": "47"}],
        "name": "FlexFamily",
        "parts": {
            "member": [
                {"id": [{"schemeName": "MSISDN", "value": owner_number}], "type": "Owner"},
                {"id": [{"schemeName": "MSISDN", "value": member_number}], "type": "Member"}
            ]
        },
        "type": "AcceptInvitation"
    }
    try:
        async with session.patch(ACCEPT_INVITATION_URL, headers=headers, json=data, timeout=30) as response:
            return response.status in [200, 201]
    except:
        return False

# ==================== BOT HANDLERS ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🚀 بدء العملية", callback_data="start_process")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 *أهلاً بيك في بوت Vodafone Flex Family!*\n\n"
        "البوت ده بيساعدك تضيف أعضاء لمجموعة فليكس فاميلي.\n"
        "اضغط 'بدء العملية' عشان تبدأ.",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "start_process":
        await query.edit_message_text("📱 *أدخل رقم المالك (اللي هيبعت الدعوة):*\nمثال: 010xxxxxxxx", parse_mode="Markdown")
        return OWNER_NUMBER

async def owner_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['owner_number'] = update.message.text
    await update.message.reply_text("🔒 *أدخل كلمة مرور المالك:*", parse_mode="Markdown")
    return OWNER_PASSWORD

async def owner_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['owner_password'] = update.message.text
    await update.message.reply_text("👥 *أدخل رقم العضو المراد إضافته:*\nمثال: 010xxxxxxxx", parse_mode="Markdown")
    return MEMBER_NUMBER

async def member_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['member_number'] = update.message.text
    await update.message.reply_text(f"🔒 *أدخل كلمة مرور العضو {context.user_data['member_number']}:*", parse_mode="Markdown")
    return MEMBER_PASSWORD

async def member_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['member_password'] = update.message.text
    
    keyboard = [
        [InlineKeyboardButton("10% (1300 فليكس)", callback_data="10")],
        [InlineKeyboardButton("20% (2600 فليكس)", callback_data="20")],
        [InlineKeyboardButton("40% (5200 فليكس)", callback_data="40")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📊 *اختار نسبة الدعوة:*", reply_markup=reply_markup, parse_mode="Markdown")
    return QUOTA_SELECT

async def quota_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    quota_map = {"10": ("10", "10% (1300 فليكس)"), "20": ("20", "20% (2600 فليكس)"), "40": ("40", "40% (5200 فليكس)")}
    quota_value, quota_display = quota_map[query.data]
    context.user_data['quota_value'] = quota_value
    context.user_data['quota_display'] = quota_display
    
    owner = context.user_data['owner_number']
    member = context.user_data['member_number']
    
    await query.edit_message_text(
        f"⚙️ *تأكيد البيانات:*\n"
        f"👤 المالك: `{owner}`\n"
        f"👥 العضو: `{member}`\n"
        f"📊 الحصة: {quota_display}\n\n"
        f"⏳ جاري بدء العملية...",
        parse_mode="Markdown"
    )
    
    # بدء العملية
    await run_process(update, context)
    return ConversationHandler.END

async def run_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_number = context.user_data['owner_number']
    owner_password = context.user_data['owner_password']
    member_number = context.user_data['member_number']
    member_password = context.user_data['member_password']
    quota_value = context.user_data['quota_value']
    quota_display = context.user_data['quota_display']
    
    chat_id = update.effective_chat.id
    
    async def send_status(msg):
        await context.bot.send_message(chat_id=chat_id, text=msg, parse_mode="Markdown")
    
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
    timeout = aiohttp.ClientTimeout(total=60)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        await send_status("🔐 *جاري تسجيل دخول المالك...*")
        owner_token = await authenticate_vodafone_async(session, owner_number, owner_password)
        
        if not owner_token:
            await send_status("❌ *فشل تسجيل دخول المالك!* تأكد من البيانات.")
            return
        
        await send_status("✅ *تم تسجيل دخول المالك بنجاح!*")
        
        attempt = 1
        max_attempts = 10
        
        while attempt <= max_attempts:
            await send_status(f"🔄 *الجولة {attempt}:* جاري إرسال الدعوة...")
            
            # طلبين متزامنين
            task1 = add_family_member_async(session, owner_token, owner_number, member_number, quota_value)
            task2 = add_family_member_async(session, owner_token, owner_number, member_number, quota_value)
            results = await asyncio.gather(task1, task2)
            
            success_count = sum(1 for r in results if r[0])
            
            if success_count >= 1:
                await send_status(f"✅ *تم إرسال الدعوة بنجاح!* ({success_count}/2 طلب ناجح)")
                break
            else:
                await send_status(f"⚠️ *فشل إرسال الدعوة* - جاري المحاولة التالية...")
                await asyncio.sleep(8)
                attempt += 1
        
        if attempt > max_attempts:
            await send_status("❌ *فشل إرسال الدعوة بعد 10 محاولات!*")
            return
        
        # انتظار قبل القبول
        await send_status("⏳ *انتظار 8 ثوانٍ قبل القبول...*")
        await asyncio.sleep(8)
        
        # سؤال القبول
        keyboard = [
            [InlineKeyboardButton("✅ نعم، اقبل", callback_data="accept_yes")],
            [InlineKeyboardButton("❌ لا، إلغاء", callback_data="accept_no")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=f"❓ *هل تريد قبول الدعوة للرقم {member_number}؟*",
            reply_markup=reply_markup,
            parse_mode="Markdown"
        )
        
        # انتظر الرد (هنستخدم طريقة بسيطة)
        context.user_data['waiting_accept'] = True
        context.user_data['accept_msg_id'] = msg.message_id

async def accept_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "accept_no":
        await query.edit_message_text("⏹️ *تم إلغاء قبول الدعوة.*", parse_mode="Markdown")
        return
    
    owner_number = context.user_data['owner_number']
    member_number = context.user_data['member_number']
    member_password = context.user_data['member_password']
    quota_display = context.user_data['quota_display']
    chat_id = update.effective_chat.id
    
    await query.edit_message_text("📥 *جاري قبول الدعوة...*", parse_mode="Markdown")
    
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
    timeout = aiohttp.ClientTimeout(total=60)
    
    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        accept_attempt = 1
        while accept_attempt <= 3:
            success = await accept_invitation_async(session, owner_number, member_number, member_password)
            if success:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🎉 *تمت العملية بنجاح!*\n"
                         f"👤 المالك: `{owner_number}`\n"
                         f"👥 العضو: `{member_number}`\n"
                         f"📊 الحصة: {quota_display}",
                    parse_mode="Markdown"
                )
                return
            
            await context.bot.send_message(chat_id=chat_id, text=f"⚠️ *فشل القبول (محاولة {accept_attempt}/3)*", parse_mode="Markdown")
            await asyncio.sleep(6)
            accept_attempt += 1
        
        await context.bot.send_message(chat_id=chat_id, text="❌ *فشل قبول الدعوة بعد 3 محاولات!*", parse_mode="Markdown")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ *تم إلغاء العملية.*", parse_mode="Markdown")
    return ConversationHandler.END

# ==================== MAIN ====================

def main():
    TOKEN = os.environ.get("BOT_TOKEN")
    
    application = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            OWNER_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_number)],
            OWNER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, owner_password)],
            MEMBER_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, member_number)],
            MEMBER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, member_password)],
            QUOTA_SELECT: [CallbackQueryHandler(quota_select, pattern="^(10|20|40)$")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^start_process$"))
    application.add_handler(CallbackQueryHandler(accept_callback, pattern="^accept_"))
    
    # للـ Render
    PORT = int(os.environ.get("PORT", 10000))
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
    
    if WEBHOOK_URL:
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=WEBHOOK_URL
        )
    else:
        application.run_polling()

if __name__ == "__main__":
    main()
