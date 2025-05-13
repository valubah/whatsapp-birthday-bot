import os
import json
import time
import schedule
import logging
import threading
import random
import requests
from datetime import datetime, timedelta
from urllib.parse import urljoin
from flask import Flask, request, jsonify

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler("birthday_bot.log")]
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# Load environment variables for WATI
WATI_ACCESS_TOKEN = os.environ.get('WATI_ACCESS_TOKEN')
WATI_API_ENDPOINT = os.environ.get('WATI_API_ENDPOINT', 'https://live-mt-server.wati.io')
WATI_ACCOUNT_ID = os.environ.get('WATI_ACCOUNT_ID', '441044')
WHATSAPP_NUMBER = os.environ.get('WHATSAPP_NUMBER')
OWNER_PHONE = os.environ.get('OWNER_PHONE', '')

# Add this near the top of the file, after the other global variables
# Cache to track processed message IDs to prevent duplicate processing
PROCESSED_MESSAGES = set()
MAX_CACHE_SIZE = 1000

# Storage for birthdays (In a production environment, use a database)
DATA_FILE = "birthdays.json"

# Advertorial messages collection
ADVERTORIALS = [
    "🎁 *Send a perfect gift!* Try GiftWizard - personalized gift recommendations for any occasion. Use code BDAY10 for 10% off your first purchase.",
    "🎂 *Planning a party?* CelebrationHub has everything you need for the perfect birthday celebration. Visit celebrationhub.com today!",
    "🎈 *Make memories last!* Use PhotoMemories app to create stunning birthday photo albums. Download now and get 50 free prints.",
    "🎊 *Need a last-minute gift?* E-GiftCards delivers instant gift cards from 500+ brands. Perfect for those forgotten birthdays!",
]

def get_random_ad():
    """Return a random advertorial message"""
    return random.choice(ADVERTORIALS)

def load_birthdays():
    """Load birthdays from JSON file"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        else:
            # Updated structure with users dictionary to store user-specific birthdays
            return {
                "users": {},  # User-specific personal birthdays
                "groups": {}  # Group birthdays (accessible to group members)
            }
    except Exception as e:
        logger.error(f"Error loading birthdays: {e}")
        # Updated structure with users dictionary
        return {
            "users": {},
            "groups": {}
        }

def save_birthdays(data):
    """Save birthdays to JSON file"""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        logger.info("Birthdays saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving birthdays: {e}")
        return False

def parse_date(date_str):
    """Parse date string into datetime object"""
    try:
        # Try different date formats
        formats = ["%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%m", "%d/%m"]

        for fmt in formats:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                # If year is not provided, use current year
                if fmt in ["%d-%m", "%d/%m"]:
                    current_year = datetime.now().year
                    date_obj = date_obj.replace(year=current_year)
                return date_obj
            except ValueError:
                continue

        raise ValueError(f"Could not parse date: {date_str}")
    except Exception as e:
        logger.error(f"Error parsing date: {e}")
        raise

def format_birthday(date_obj):
    """Format birthday to DD-MM-YYYY format"""
    return date_obj.strftime("%d-%m-%Y")

def check_upcoming_birthdays(days_ahead=1):
    """Check for upcoming birthdays"""
    try:
        birthdays = load_birthdays()
        today = datetime.now().date()
        upcoming = []

        # Function to calculate next birthday date
        def get_next_birthday(date_str):
            bday = datetime.strptime(date_str, "%d-%m-%Y").date().replace(year=today.year)
            if bday < today:
                bday = bday.replace(year=today.year + 1)
            return bday

        # Check personal birthdays for all users (for admin notifications only)
        for user_id, user_data in birthdays["users"].items():
            for name, info in user_data.get("birthdays", {}).items():
                bday = get_next_birthday(info["birthday"])
                days_until = (bday - today).days

                if days_until == days_ahead:
                    upcoming.append({
                        "name": name,
                        "birthday": info["birthday"],
                        "phone": user_id,  # The user who added this birthday
                        "owner_phone": user_id,  # The owner of this birthday entry
                        "days_until": days_until
                    })

        # Check group birthdays
        for group_id, group_info in birthdays["groups"].items():
            for name, info in group_info["members"].items():
                bday = get_next_birthday(info["birthday"])
                days_until = (bday - today).days

                if days_until == days_ahead:
                    upcoming.append({
                        "name": name,
                        "birthday": info["birthday"],
                        "group_id": group_id,
                        "group_name": group_info["name"],
                        "days_until": days_until
                    })

        return upcoming
    except Exception as e:
        logger.error(f"Error checking upcoming birthdays: {e}")
        return []

def send_wati_message(recipient, message, message_type="text", attachments=None, timeout=20):
    """
    Sends a WhatsApp message using the WATI API.

    Args:
        recipient (str): The recipient's phone number (with or without '+' prefix)
        message (str): The message content to send
        message_type (str, optional): The type of message - "text" (default), "template", "image", etc.
        attachments (dict, optional): Any attachments to include with the message
        timeout (int, optional): Request timeout in seconds (default: 20)

    Returns:
        dict: Response information with keys:
        - success (bool): Whether the message was sent successfully
        - message_id (str, optional): The ID of the sent message if successful
        - error (str, optional): Error message if unsuccessful
    """
    try:
        # --- Initial Checks ---
        if not WATI_ACCESS_TOKEN:
            logger.error("WATI_ACCESS_TOKEN is not configured.")
            return {"success": False, "error": "WATI_ACCESS_TOKEN not configured"}
        if not WATI_API_ENDPOINT:
            logger.error("WATI_API_ENDPOINT is not configured.")
            return {"success": False, "error": "WATI_API_ENDPOINT not configured"}
        if not recipient:
            logger.error("Recipient phone number is empty.")
            return {"success": False, "error": "Empty recipient phone number"}
        if not message and message_type == "text":
            logger.error("Message content is empty.")
            return {"success": False, "error": "Empty message content"}

        # --- Format phone number ---
        formatted_recipient = recipient
        if isinstance(recipient, str) and recipient.startswith('+'):
            formatted_recipient = recipient[1:]

        # --- Prepare API endpoint ---
        base_api_url = WATI_API_ENDPOINT.rstrip('/') + '/'  # Ensure trailing slash

        # Determine which endpoint to use based on message type
        if message_type == "text":
            relative_path = f"api/v1/sendSessionMessage/{formatted_recipient}"
        elif message_type == "template":
            relative_path = f"api/v1/sendTemplateMessage/{formatted_recipient}"
        elif message_type == "image":
            relative_path = f"api/v1/sendSessionMessage/{formatted_recipient}/image"
        elif message_type == "file":
            relative_path = f"api/v1/sendSessionMessage/{formatted_recipient}/file"
        else:
            # Default to text message
            relative_path = f"api/v1/sendSessionMessage/{formatted_recipient}"

        target_endpoint = urljoin(base_api_url, relative_path)

        # --- Prepare headers and parameters ---
        headers = {
            "Authorization": f"Bearer {WATI_ACCESS_TOKEN}"
        }

        # Prepare request data based on message type
        params = {}
        data = None
        json_data = None

        if message_type == "text":
            # For text messages, use query parameter
            params = {"messageText": message}
        elif message_type == "template":
            # For template messages, use JSON body
            json_data = {
                "template_name": message,
                "broadcast_name": f"broadcast_{int(time.time())}",
                "parameters": attachments or []
            }
        elif message_type in ["image", "file"]:
            # For media messages, use JSON body with URL
            if attachments and "url" in attachments:
                json_data = {
                    "url": attachments["url"],
                    "caption": message
                }
            else:
                return {"success": False, "error": f"URL required for {message_type} message type"}

        # --- Make the API request ---
        logger.info(f"Sending {message_type} message to {formatted_recipient}")

        try:
            if json_data:
                headers["Content-Type"] = "application/json"
                response = requests.post(
                    target_endpoint,
                    headers=headers,
                    params=params,
                    json=json_data,
                    timeout=timeout
                )
            else:
                response = requests.post(
                    target_endpoint,
                    headers=headers,
                    params=params,
                    data=data,
                    timeout=timeout
                )

            # --- Process the response ---
            response_text = response.text if response.text and response.text.strip() else '(empty response body)'

            if response.status_code in [200, 201, 202]:
                try:
                    if not response.text.strip():
                        logger.warning(f"Empty response body with status {response.status_code}")
                        return {"success": True, "warning": "Empty response body"}

                    data = response.json()
                    if isinstance(data, dict):
                        # Check for successful response patterns
                        if (data.get("result") == "success" and data.get("ok") is True) or \
                           (data.get("id") and data.get("status") in ["submitted", "sent", "OK", "queued", "success"]):

                            # Extract message ID if available
                            message_id = None
                            if "message" in data and isinstance(data["message"], dict):
                                message_id = data["message"].get("whatsappMessageId") or data["message"].get("id")
                            elif "id" in data:
                                message_id = data.get("id")

                            logger.info(f"Message sent successfully to {formatted_recipient}" +
                                        (f": ID {message_id}" if message_id else ""))

                            return {
                                "success": True,
                                "message_id": message_id,
                                "response": data
                            }
                        elif data.get("result") is False or "fault" in data or "error" in data or data.get("status") == "error":
                            error_msg = data.get("info") or data.get("error") or data.get("fault") or response_text
                            logger.error(f"API error response: {error_msg}")
                            return {"success": False, "error": error_msg, "response": data}
                        else:
                            logger.warning(f"Unclear API response: {response_text}")
                            return {"success": True, "warning": "Unclear API response", "response": data}
                except ValueError:
                    # Non-JSON response
                    if response.status_code in [200, 201, 202]:
                        logger.warning(f"Non-JSON response with success status code: {response_text}")
                        return {"success": True, "warning": "Non-JSON response", "raw_response": response_text}
                    else:
                        logger.error(f"Non-JSON error response: {response_text}")
                        return {"success": False, "error": f"Non-JSON response: {response_text}"}
            else:
                # Handle error status codes
                error_msg = f"HTTP {response.status_code}: {response_text}"
                logger.error(error_msg)

                if response.status_code == 404:
                    error_detail = "Endpoint not found. Check API URL and path."
                elif response.status_code == 400:
                    error_detail = "Bad request. Check phone number format and parameters."
                elif response.status_code in [401, 403]:
                    error_detail = "Authentication failure. Check your access token."
                else:
                    error_detail = "Unknown error."

                return {
                    "success": False,
                    "error": error_msg,
                    "error_detail": error_detail,
                    "status_code": response.status_code
                }

        except requests.exceptions.Timeout:
            timeout_msg = f"Request to WATI API timed out after {timeout}s"
            logger.error(timeout_msg)
            return {"success": False, "error": timeout_msg}
        except requests.exceptions.RequestException as e:
            error_msg = f"Request exception: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Unhandled exception: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"success": False, "error": error_msg}

def daily_check():
    """Daily check for birthdays and send reminders"""
    try:
        logger.info("Running daily birthday check...")
        upcoming = check_upcoming_birthdays(days_ahead=1)
        birthdays = load_birthdays()

        for person in upcoming:
            if "group_id" in person:
                # Send to group
                group_id = person["group_id"]
                group_info = birthdays["groups"][group_id]
                message = f"🎂 Reminder: {person['name']}'s birthday is tomorrow! 🎉\n\n{get_random_ad()}"
                send_wati_message(group_info["phone"], message)
            else:
                # Send personal birthday reminders to the user who added them
                user_id = person["owner_phone"]
                message = f"🎂 Birthday Reminder: {person['name']}'s birthday is tomorrow! 🎉\n\n{get_random_ad()}"
                send_wati_message(user_id, message)
                
                # Also notify system owner if configured
                if OWNER_PHONE and OWNER_PHONE != user_id:
                    send_wati_message(OWNER_PHONE, f"System notification: {person['name']}'s birthday tomorrow (added by {user_id})")

        logger.info(f"Daily check completed, found {len(upcoming)} upcoming birthdays")
    except Exception as e:
        logger.error(f"Error in daily check: {e}")

# Schedule daily check at 9 AM
schedule.every().day.at("09:00").do(daily_check)

def run_scheduler():
    """Run the scheduler in a separate thread"""
    while True:
        schedule.run_pending()
        time.sleep(60)  # Check every minute

# Start the scheduler in a separate thread
scheduler_thread = None

@app.route('/')
def home():
    """Homepage route"""
    return 'Birthday Bot is running!'

@app.route('/health')
def health():
    """Health check route"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})
















@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    """Handle incoming WhatsApp messages from WATI"""
    try:
        # Added support for GET method to respond to health checks
        if request.method == 'GET':
            logger.info("Received GET request to webhook")
            return jsonify({"status": "ok"}), 200

        # Log all headers and content for debugging
        logger.info(f"Headers: {dict(request.headers)}")
        logger.info(f"Content type: {request.content_type}")
        logger.info(f"Raw data: {request.data.decode('utf-8') if request.data else 'No data'}")

        # Extract data from request
        data = {}
        try:
            if request.content_type and 'application/json' in request.content_type:
                data = request.json
            else:
                data = request.get_json(force=True)
        except Exception as parse_error:
            logger.warning(f"Error parsing JSON: {parse_error}")
            # Try form data
            data = request.form.to_dict()
            if not data and request.data:
                try:
                    data = json.loads(request.data.decode('utf-8'))
                except Exception as e:
                    logger.warning(f"Could not parse raw data: {e}")
                    # Extract basic data with regex
                    try:
                        raw_data = request.data.decode('utf-8')
                        import re
                        text_match = re.search(r'"text"\s*:\s*"([^"]+)"', raw_data)
                        waid_match = re.search(r'"waId"\s*:\s*"([^"]+)"', raw_data)
                        groupid_match = re.search(r'"(groupId|chatId)"\s*:\s*"([^"]+)"', raw_data)

                        if text_match:
                            data['text'] = text_match.group(1)
                        if waid_match:
                            data['waId'] = waid_match.group(1)
                        if groupid_match:
                            data[groupid_match.group(1)] = groupid_match.group(2)
                    except:
                        pass

        logger.info(f"Processed data: {data}")

        # Extract message details
        incoming_msg = ""
        sender = ""
        group_id = None
        message_id = data.get('id', '')
        whatsapp_message_id = data.get('whatsappMessageId', '')
        event_type = data.get('eventType', '')
        
        # CRITICAL: Only process "received" messages from users
        # WATI sends different event types - we only want to respond to incoming user messages
        if not (event_type == 'message_received' or event_type == 'received' or 
                'received' in str(event_type).lower() or data.get('type') == 'incoming'):
            logger.info(f"Ignoring non-user message event: {event_type}")
            return jsonify({"status": "ignored", "reason": "Not a user message event"}), 200
        
        # Never process delivery reports, read receipts or sent messages
        if event_type and any(status in event_type.lower() for status in 
                             ['delivered', 'read', 'sent', 'failed', 'status']):
            logger.info(f"Ignoring status update event: {event_type}")
            return jsonify({"status": "ignored", "reason": "Status update event"}), 200

        # Check for bot-generated messages
        if (data.get('owner') is True or 
            data.get('fromMe') is True or 
            data.get('isFromMe') is True or 
            data.get('type') == 'outgoing' or 
            data.get('direction') == 'outgoing'):
            logger.info(f"Ignoring message sent by bot")
            return jsonify({"status": "ignored", "reason": "Bot's own message"}), 200

        # Check if we've already processed this message
        unique_id = message_id or whatsapp_message_id or data.get('messageId', '')
        if not unique_id:
            # Try to create a unique ID from combination of sender and timestamp
            timestamp = data.get('timestamp', '') or data.get('creation_time', '') or str(time.time())
            unique_id = f"{sender}_{timestamp}"
            
        if unique_id in PROCESSED_MESSAGES:
            logger.info(f"Ignoring already processed message: {unique_id}")
            return jsonify({"status": "ignored", "reason": "Already processed"}), 200
        
        # Add message ID to processed set
        PROCESSED_MESSAGES.add(unique_id)
        # Prevent set from growing too large
        if len(PROCESSED_MESSAGES) > MAX_CACHE_SIZE:
            # Remove oldest entries (approximation by just clearing half the set)
            logger.info(f"Clearing message cache ({len(PROCESSED_MESSAGES)} items)")
            PROCESSED_MESSAGES.clear()

        # Extract message content (handle various possible field names)
        for field in ['text', 'body', 'message', 'messageText', 'caption']:
            if field in data:
                if isinstance(data.get(field), str):
                    incoming_msg = data.get(field, '').strip().lower()
                    if incoming_msg:
                        break
                elif isinstance(data.get(field), dict) and 'body' in data.get(field):
                    incoming_msg = data.get(field).get('body', '').strip().lower()
                    if incoming_msg:
                        break

        # Extract sender ID (handle various possible field names)
        for field in ['waId', 'from', 'sender', 'contactId', 'senderPhone', 'senderName', 'senderId']:
            if field in data:
                sender = data.get(field, '')
                if sender:
                    break
                    
        # If still no sender, check nested objects
        if not sender and 'conversation' in data and isinstance(data['conversation'], dict):
            sender = data['conversation'].get('id', '')

        # Ensure sender is not our bot's WhatsApp number 
        if WHATSAPP_NUMBER and sender == WHATSAPP_NUMBER:
            logger.info(f"Ignoring message from our own number")
            return jsonify({"status": "ignored", "reason": "Message from our own number"}), 200

        # Check for group ID (handle various possible field names)
        for field in ['groupId', 'chatId', 'group_id', 'groupName']:
            if field in data:
                group_id = data.get(field)
                if group_id:
                    break

        logger.info(f"Extracted data: Message: '{incoming_msg}', Sender: '{sender}', Group: '{group_id}'")

        # Only process if we have both a message and sender
        if incoming_msg and sender:
            logger.info(f"Processing user message from {sender}: '{incoming_msg}'")
            
            # Process commands
            response_message = process_command(incoming_msg, sender, group_id)

            # Send response via WATI API (only once)
            if response_message:
                result = send_wati_message(sender, response_message)
                if result.get("success"):
                    logger.info(f"Successfully sent response to {sender}")
                else:
                    logger.error(f"Failed to send response to {sender}: {result.get('error')}")

            return jsonify({"status": "success", "message": "Processed message"}), 200
        else:
            # If we don't have a message or sender, just acknowledge the webhook
            logger.warning("Valid webhook request but could not extract message data")
            return jsonify({"status": "acknowledged", "message": "Request received but no valid message data found"}), 200

    except Exception as e:
        logger.error(f"Error in webhook: {str(e)}", exc_info=True)
        # Always return a success to stop WATI from retrying
        return jsonify({"status": "error", "message": str(e)}), 200








def process_command(incoming_msg, sender, group_id=None):
    """Process commands and return appropriate response message"""
    try:
        # Log the command processing for debugging
        logger.info(f"Processing command: '{incoming_msg}' from sender: {sender}, group: {group_id}")

        if incoming_msg.startswith('help'):
            return f"""
🤖 *Whatsapp Birthday Alert Commands*:
- *add <name> <DD-MM-YYYY>*: Add a birthday
- *remove <name>*: Remove a birthday
- *list*: List all birthdays
- *next*: Show next birthday
- *help*: Show this message

{get_random_ad()}
"""

        elif incoming_msg.startswith('add '):
            parts = incoming_msg[4:].split()
            if len(parts) >= 2:
                name = ' '.join(parts[:-1])
                date_str = parts[-1]

                try:
                    date_obj = parse_date(date_str)
                    formatted_date = format_birthday(date_obj)

                    birthdays = load_birthdays()

                    if group_id:
                        # Add to group
                        if group_id not in birthdays["groups"]:
                            birthdays["groups"][group_id] = {
                                "name": f"Group {group_id[-6:]}",
                                "phone": sender,
                                "members": {}
                            }

                        birthdays["groups"][group_id]["members"][name] = {
                            "birthday": formatted_date,
                            "added_by": sender
                        }
                        message = f"✅ Added {name}'s birthday ({formatted_date}) to the group!\n\n{get_random_ad()}"
                    else:
                        # Add to personal list
                        birthdays["personal"][name] = {
                            "birthday": formatted_date,
                            "phone": sender,
                            "added_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        message = f"✅ Added {name}'s birthday ({formatted_date}) to your list!\n\n{get_random_ad()}"

                    save_birthdays(birthdays)
                    return message

                except Exception as e:
                    return f"❌ Error: {str(e)}\nPlease use format: add <name> <DD-MM-YYYY>\n\n{get_random_ad()}"
            else:
                return f"❌ Error: Please use format: add <name> <DD-MM-YYYY>\n\n{get_random_ad()}"

        elif incoming_msg.startswith('remove '):
            name = incoming_msg[7:].strip()
            birthdays = load_birthdays()

            if group_id and group_id in birthdays["groups"]:
                if name in birthdays["groups"][group_id]["members"]:
                    del birthdays["groups"][group_id]["members"][name]
                    save_birthdays(birthdays)
                    return f"✅ Removed {name}'s birthday from the group!\n\n{get_random_ad()}"
                else:
                    return f"❌ Error: {name} not found in this group's birthday list.\n\n{get_random_ad()}"
            else:
                if name in birthdays["personal"]:
                    del birthdays["personal"][name]
                    save_birthdays(birthdays)
                    return f"✅ Removed {name}'s birthday from your list!\n\n{get_random_ad()}"
                else:
                    return f"❌ Error: {name} not found in your birthday list.\n\n{get_random_ad()}"

        elif incoming_msg == 'list':
            birthdays = load_birthdays()

            if group_id and group_id in birthdays["groups"]:
                group_info = birthdays["groups"][group_id]
                if not group_info["members"]:
                    return f"📅 No birthdays saved for this group yet.\n\n{get_random_ad()}"
                else:
                    message = "📅 *Group Birthday List*:\n"
                    for name, info in sorted(group_info["members"].items()):
                        date_obj = datetime.strptime(info["birthday"], "%d-%m-%Y")
                        message += f"- {name}: {date_obj.strftime('%d %B')}\n"
                    message += f"\n{get_random_ad()}"
                    return message
            else:
                if not birthdays["personal"]:
                    return f"📅 No birthdays saved yet.\n\n{get_random_ad()}"
                else:
                    message = "📅 *Your Birthday List*:\n"
                    for name, info in sorted(birthdays["personal"].items()):
                        date_obj = datetime.strptime(info["birthday"], "%d-%m-%Y")
                        message += f"- {name}: {date_obj.strftime('%d %B')}\n"
                    message += f"\n{get_random_ad()}"
                    return message

        elif incoming_msg == 'next':
            today = datetime.now().date()
            birthdays = load_birthdays()
            next_birthdays = []

            # Function to calculate days until next birthday
            def days_until_birthday(date_str):
                bday = datetime.strptime(date_str, "%d-%m-%Y").date().replace(year=today.year)
                if bday < today:
                    bday = bday.replace(year=today.year + 1)
                return (bday - today).days

            if group_id and group_id in birthdays["groups"]:
                group_info = birthdays["groups"][group_id]
                for name, info in group_info["members"].items():
                    days = days_until_birthday(info["birthday"])
                    next_birthdays.append((name, info["birthday"], days))
            else:
                for name, info in birthdays["personal"].items():
                    days = days_until_birthday(info["birthday"])
                    next_birthdays.append((name, info["birthday"], days))

            if not next_birthdays:
                return f"📅 No birthdays saved yet.\n\n{get_random_ad()}"
            else:
                next_birthdays.sort(key=lambda x: x[2])  # Sort by days until birthday
                next_person = next_birthdays[0]

                if next_person[2] == 0:
                    return f"🎂 Today is {next_person[0]}'s birthday! 🎉\n\n{get_random_ad()}"
                elif next_person[2] == 1:
                    return f"🎂 Tomorrow is {next_person[0]}'s birthday! 🎉\n\n{get_random_ad()}"
                else:
                    bday = datetime.strptime(next_person[1], "%d-%m-%Y")
                    return f"🎂 Next birthday: {next_person[0]} on {bday.strftime('%d %B')} (in {next_person[2]} days)\n\n{get_random_ad()}"

        else:
            # Default welcome message
            return f"""
👋 *Welcome to Whatsapp Birthday Alert Messenger!*

I'll help you remember birthdays. Try these commands:
- *add <name> <DD-MM-YYYY>* e.g add valentine 25-12-1990
- *list*
- *help* (for more commands)

{get_random_ad()}
"""

    except Exception as e:
        logger.error(f"Error processing command: {e}")
        return f"❌ An error occurred: {str(e)}. Please try again.\n\n{get_random_ad()}"










# Simple diagnostic endpoint to help with debugging webhook issues
@app.route('/diagnose', methods=['GET'])
def diagnose():
    """Diagnostic endpoint to check bot status"""
    try:
        status = {
            "bot_status": "running",
            "timestamp": datetime.now().isoformat(),
            "environment_vars": {
                "WATI_API_ENDPOINT": WATI_API_ENDPOINT,
                "WATI_ACCESS_TOKEN": bool(WATI_ACCESS_TOKEN),
                "WATI_ACCOUNT_ID": WATI_ACCOUNT_ID,
                "WHATSAPP_NUMBER": WHATSAPP_NUMBER if WHATSAPP_NUMBER else "Not set",
                "OWNER_PHONE": OWNER_PHONE if OWNER_PHONE else "Not set",
            },
            "birthdays_file_exists": os.path.exists(DATA_FILE),
            "birthdays_count": {
                "personal": len(load_birthdays().get("personal", {})),
                "groups": sum(len(group_info.get("members", {})) for group_id, group_info in load_birthdays().get("groups", {}).items())
            },
            "upcoming_birthdays": len(check_upcoming_birthdays(days_ahead=1)),
            "test_endpoints": {
                "test_wati": f"/test_wati?phone={OWNER_PHONE}",
                "health": "/health"
            }
        }
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error in diagnose endpoint: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500








if __name__ == '__main__':
    # Create data file if it doesn't exist
    if not os.path.exists(DATA_FILE):
        save_birthdays({"personal": {}, "groups": {}})

    # Start the scheduler in a separate thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()

    # Run Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
else:
    # For WSGI servers like gunicorn or when running on PythonAnywhere
    # Create data file if it doesn't exist
    if not os.path.exists(DATA_FILE):
        save_birthdays({"personal": {}, "groups": {}})

    # Start the scheduler only once
    if not scheduler_thread:
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        logger.info("Scheduler started in WSGI mode")
