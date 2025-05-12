import os
import json
import time
import schedule
import logging
import threadin
import random
import requests
from datetime import datetime, timedelta
from urllib.parse import urljoin  # Add this import to fix the erro
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
WATI_ACCOUNT_ID = os.environ.get('WATI_ACCOUNT_ID', '441044')  # Fixed account ID
WHATSAPP_NUMBER = os.environ.get('WHATSAPP_NUMBER')
OWNER_PHONE = os.environ.get('OWNER_PHONE', '')  # Default to empty string if not set

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
            return {"personal": {}, "groups": {}}
    except Exception as e:
        logger.error(f"Error loading birthdays: {e}")
        return {"personal": {}, "groups": {}}

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

        # Check personal birthdays
        for name, info in birthdays["personal"].items():
            bday = datetime.strptime(info["birthday"], "%d-%m-%Y").date().replace(year=today.year)
            # If birthday has passed this year, check for next year
            if bday < today:
                bday = bday.replace(year=today.year + 1)

            days_until = (bday - today).days

            if days_until == days_ahead:
                upcoming.append({
                    "name": name,
                    "birthday": info["birthday"],
                    "phone": info["phone"],
                    "days_until": days_until
                })

        # Check group birthdays
        for group_id, group_info in birthdays["groups"].items():
            for name, info in group_info["members"].items():
                bday = datetime.strptime(info["birthday"], "%d-%m-%Y").date().replace(year=today.year)
                # If birthday has passed this year, check for next year
                if bday < today:
                    bday = bday.replace(year=today.year + 1)

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







def send_wati_message(recipient, message):
    """
    Sends a WhatsApp message using the WATI API with real user data.
    Optimized for production use with proper error handling.
    """
    try:
        # --- Initial Checks ---
        if not WATI_ACCESS_TOKEN:
            logger.error("WATI_ACCESS_TOKEN is not configured.")
            return False
        if not WATI_API_ENDPOINT:
            logger.error("WATI_API_ENDPOINT is not configured.")
            return False
        if not recipient:
            logger.error("Recipient phone number is empty.")
            return False
        if not message:
            logger.error("Message content is empty.")
            return False

        # --- Format recipient number ---
        # Remove any '+' prefix and ensure valid number format
        formatted_recipient = recipient
        if isinstance(recipient, str):
            # Remove any '+' prefix
            if recipient.startswith('+'):
                formatted_recipient = recipient[1:]
            # Remove any spaces or special characters
            formatted_recipient = ''.join(c for c in formatted_recipient if c.isdigit())
            # Ensure it follows WATI's expected format
            if not formatted_recipient.isdigit():
                logger.error(f"Invalid recipient number format: {recipient}")
                return False

        # --- Prepare API Request ---
        base_api_url = WATI_API_ENDPOINT.rstrip('/') + '/'
        relative_path = f"api/v1/sendSessionMessage/{formatted_recipient}"
        target_endpoint = urljoin(base_api_url, relative_path)

        headers = {
            "Authorization": f"Bearer {WATI_ACCESS_TOKEN}",
            "Content-Type": "application/json"  # Include for future API compatibility
        }

        # Message content with formatting and emojis
        query_params = {
            "messageText": message
        }

        logger.info(f"Sending message to {formatted_recipient} via WATI API")
        
        # --- Make API Request ---
        response = requests.post(
            target_endpoint,
            headers=headers,
            params=query_params,
            timeout=20  # 20 second timeout
        )

        # --- Process Response ---
        if response.status_code in [200, 201, 202]:
            try:
                resp_data = response.json() if response.text.strip() else {}
                
                # Check for success indicators in response
                if (resp_data.get("result") == "success" or 
                    resp_data.get("status") in ["submitted", "sent", "queued", "success"] or
                    (isinstance(resp_data.get("message"), dict) and resp_data["message"].get("id"))):
                    logger.info(f"Message sent successfully to {formatted_recipient}")
                    return True
                else:
                    logger.warning(f"Unexpected success response structure: {response.text}")
                    # Still return True if we got a 200 range status code
                    return True
            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON response with status {response.status_code}: {response.text}")
                # Still return True if we got a 200 range status code
                return True
        else:
            # Handle specific error responses
            error_message = f"Failed to send message. Status code: {response.status_code}"
            
            try:
                error_data = response.json() if response.text.strip() else {}
                if error_data.get("info"):
                    error_message += f", Info: {error_data['info']}"
                elif error_data.get("message"):
                    error_message += f", Message: {error_data['message']}"
            except:
                if response.text:
                    error_message += f", Response: {response.text[:100]}..."
            
            logger.error(error_message)
            
            # Specific error handling based on status code
            if response.status_code == 401:
                logger.critical("Authentication failed. Check your WATI_ACCESS_TOKEN")
            elif response.status_code == 404:
                logger.critical(f"API endpoint not found: {target_endpoint}")
            elif response.status_code == 400:
                logger.error(f"Bad request. Check recipient format: {formatted_recipient}")
                
            return False

    except requests.exceptions.Timeout:
        logger.error(f"Request to WATI API timed out for {formatted_recipient}")
        return False
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error when sending to {formatted_recipient}. Check network or API endpoint.")
        return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error when sending to {formatted_recipient}: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error in send_wati_message: {str(e)}", exc_info=True)
        return False

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    """Handle incoming WhatsApp messages from WATI with improved user menu display"""
    try:
        # Handle GET requests (health checks)
        if request.method == 'GET':
            logger.info("Received GET request to webhook")
            return jsonify({"status": "ok"}), 200
            
        # Log request details for debugging
        logger.info(f"Received webhook request: {request.headers.get('Content-Type', 'unknown content type')}")
        
        # Extract data from request
        try:
            if request.is_json:
                data = request.get_json()
            else:
                # Try to parse as JSON anyway
                try:
                    data = json.loads(request.data.decode('utf-8'))
                except:
                    # Fall back to form data
                    data = request.form.to_dict()
        except Exception as e:
            logger.warning(f"Error parsing webhook data: {str(e)}")
            data = {}
            
            # Last resort - try to extract from raw data
            try:
                raw_data = request.data.decode('utf-8')
                logger.debug(f"Raw webhook data: {raw_data}")
                
                # Extract key fields with regex
                import re
                for pattern, key in [
                    (r'"text"\s*:\s*"([^"]+)"', 'text'),
                    (r'"body"\s*:\s*"([^"]+)"', 'body'),
                    (r'"waId"\s*:\s*"([^"]+)"', 'waId'),
                    (r'"from"\s*:\s*"([^"]+)"', 'from'),
                    (r'"(groupId|chatId)"\s*:\s*"([^"]+)"', lambda m: (m.group(1), m.group(2)))
                ]:
                    match = re.search(pattern, raw_data)
                    if match:
                        if callable(key):
                            k, v = key(match)
                            data[k] = v
                        else:
                            data[key] = match.group(1)
            except Exception as e:
                logger.error(f"Failed to extract data from raw webhook: {str(e)}")
        
        logger.info(f"Processed webhook data: {data}")
        
        # Extract message content, sender, and group info
        incoming_msg = ""
        sender = ""
        group_id = None
        
        # Extract message from various possible fields
        for field in ['text', 'body', 'message', 'messageText']:
            if field in data:
                if isinstance(data[field], str):
                    incoming_msg = data[field].strip()
                elif isinstance(data[field], dict) and 'text' in data[field]:
                    incoming_msg = data[field]['text'].strip()
                
                if incoming_msg:
                    break
                    
        # If we still don't have a message but have a data object
        if not incoming_msg and isinstance(data, dict):
            # Try to look in nested objects
            for key, value in data.items():
                if isinstance(value, dict) and 'text' in value:
                    incoming_msg = value['text'].strip()
                    break
                    
        # Extract sender information
        for field in ['waId', 'from', 'sender', 'contactId', 'senderName']:
            if field in data:
                sender = data[field]
                if sender:
                    break
        
        # Extract group information        
        for field in ['groupId', 'chatId', 'group_id']:
            if field in data:
                group_id = data[field]
                if group_id:
                    break
                    
        # If still no sender but we have a data object, check for nested objects
        if not sender and isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    for sender_field in ['waId', 'from', 'sender', 'contactId']:
                        if sender_field in value:
                            sender = value[sender_field]
                            if sender:
                                break
                    if sender:
                        break
                        
        # Convert incoming_msg to lowercase for easier command matching
        if incoming_msg:
            incoming_msg = incoming_msg.lower()
            
        logger.info(f"Extracted message: '{incoming_msg}', sender: '{sender}', group: '{group_id}'")
        
        # If no message or just a greeting, show the welcome menu
        if not incoming_msg or incoming_msg in ['hi', 'hello', 'hey', 'start', 'hola', 'menu', 'bot']:
            welcome_message = f"""
👋 *Welcome to Birthday Alert Bot!*

I'll help you remember birthdays and send timely reminders. 
Here's what I can do:

1️⃣ *add <name> <DD-MM-YYYY>* 
   Example: add Mom 15-05-1970

2️⃣ *list* - Show all saved birthdays

3️⃣ *next* - Show upcoming birthdays

4️⃣ *remove <name>* - Delete a birthday
   Example: remove Mom

5️⃣ *help* - Show this menu again

{get_random_ad()}
"""
            success = send_wati_message(sender, welcome_message)
            if success:
                logger.info(f"Sent welcome menu to {sender}")
            else:
                logger.error(f"Failed to send welcome menu to {sender}")
                
            return jsonify({"status": "success", "message": "Sent welcome menu"}), 200
            
        # If we have a real message and sender, process the command
        if incoming_msg and sender:
            # Process the command
            response_message = process_command(incoming_msg, sender, group_id)
            
            # Send response
            if response_message:
                success = send_wati_message(sender, response_message)
                if success:
                    logger.info(f"Successfully sent response to {sender}")
                else:
                    logger.error(f"Failed to send response to {sender}")
                
            return jsonify({"status": "success", "message": "Processed command"}), 200
        else:
            # Log the issue but still return success to avoid retries
            logger.warning(f"Webhook received but couldn't extract valid message or sender")
            return jsonify({"status": "acknowledged", "message": "Request received but insufficient data"}), 200
            
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 200  # Return 200 to avoid retries

def process_command(incoming_msg, sender, group_id=None):
    """Process user commands with improved formatting and real user data handling"""
    try:
        logger.info(f"Processing command: '{incoming_msg}' from {sender}")
        
        # Help command
        if incoming_msg.startswith('help'):
            return f"""
🤖 *Birthday Alert Bot - Commands*:

1️⃣ *add <name> <DD-MM-YYYY>* 
   Example: add Mom 15-05-1970

2️⃣ *list* - Show all saved birthdays

3️⃣ *next* - Show upcoming birthdays

4️⃣ *remove <name>* - Delete a birthday
   Example: remove Mom

5️⃣ *help* - Show this menu again

{get_random_ad()}
"""

        # Add birthday command
        elif incoming_msg.startswith('add '):
            parts = incoming_msg[4:].split()
            if len(parts) >= 2:
                name = ' '.join(parts[:-1])
                date_str = parts[-1]

                try:
                    date_obj = parse_date(date_str)
                    formatted_date = format_birthday(date_obj)
                    
                    # Validate name
                    if len(name) < 2:
                        return f"❌ Name is too short. Please use a longer name.\n\n{get_random_ad()}"
                        
                    # Check if birthday is in the future
                    if date_obj.date() > datetime.now().date() and date_obj.year == datetime.now().year:
                        return f"❌ Birthday date cannot be in the future. Please enter a valid date.\n\n{get_random_ad()}"

                    birthdays = load_birthdays()

                    # Handle group vs personal birthday
                    if group_id:
                        # Add to group birthdays
                        if group_id not in birthdays["groups"]:
                            # Create new group entry
                            group_name = f"Group {group_id[-6:]}"  # Use last 6 digits of group ID as name
                            birthdays["groups"][group_id] = {
                                "name": group_name,
                                "phone": group_id,  # Use group_id as the contact point
                                "members": {}
                            }

                        # Add birthday to group
                        birthdays["groups"][group_id]["members"][name] = {
                            "birthday": formatted_date,
                            "added_by": sender,
                            "added_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        # Calculate days until birthday
                        today = datetime.now().date()
                        bday = datetime.strptime(formatted_date, "%d-%m-%Y").date().replace(year=today.year)
                        if bday < today:
                            bday = bday.replace(year=today.year + 1)
                        days_until = (bday - today).days
                        
                        # Create response message
                        if days_until == 0:
                            birthday_info = f"🎉 That's today! Happy Birthday to {name}! 🎂"
                        elif days_until == 1:
                            birthday_info = f"That's tomorrow! 🎉"
                        else:
                            birthday_info = f"Coming up in {days_until} days"
                            
                        message = f"""
✅ *Birthday Added to Group*

*Name*: {name}
*Date*: {date_obj.strftime('%d %B')} ({formatted_date})
*Status*: {birthday_info}

I'll send a reminder to this group one day before.

{get_random_ad()}
"""
                    else:
                        # Add to personal birthdays
                        birthdays["personal"][name] = {
                            "birthday": formatted_date,
                            "phone": sender,
                            "added_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        }
                        
                        # Calculate days until birthday
                        today = datetime.now().date()
                        bday = datetime.strptime(formatted_date, "%d-%m-%Y").date().replace(year=today.year)
                        if bday < today:
                            bday = bday.replace(year=today.year + 1)
                        days_until = (bday - today).days
                        
                        # Create response message
                        if days_until == 0:
                            birthday_info = f"🎉 That's today! Happy Birthday to {name}! 🎂"
                        elif days_until == 1:
                            birthday_info = f"That's tomorrow! 🎉"
                        else:
                            birthday_info = f"Coming up in {days_until} days"
                            
                        message = f"""
✅ *Birthday Added Successfully*

*Name*: {name}
*Date*: {date_obj.strftime('%d %B')} ({formatted_date})
*Status*: {birthday_info}

I'll send you a reminder one day before.

{get_random_ad()}
"""

                    # Save updated birthdays
                    save_birthdays(birthdays)
                    return message

                except Exception as e:
                    return f"""
❌ *Error Adding Birthday*

Please use the correct format:
*add <name> <DD-MM-YYYY>*

Example: add Mom 15-05-1970

{get_random_ad()}
"""
            else:
                return f"""
❌ *Error: Missing Information*

Please use the correct format:
*add <name> <DD-MM-YYYY>*

Example: add Mom 15-05-1970

{get_random_ad()}
"""

        # Remove birthday command
        elif incoming_msg.startswith('remove '):
            name = incoming_msg[7:].strip()
            if not name:
                return f"❌ Please specify a name to remove.\n\n{get_random_ad()}"
                
            birthdays = load_birthdays()

            if group_id and group_id in birthdays["groups"]:
                # Remove from group
                if name in birthdays["groups"][group_id]["members"]:
                    removed_info = birthdays["groups"][group_id]["members"][name]
                    del birthdays["groups"][group_id]["members"][name]
                    save_birthdays(birthdays)
                    return f"""
✅ *Birthday Removed*

Successfully removed {name}'s birthday from the group.

{get_random_ad()}
"""
                else:
                    # Try case-insensitive search
                    for member_name in list(birthdays["groups"][group_id]["members"].keys()):
                        if member_name.lower() == name.lower():
                            del birthdays["groups"][group_id]["members"][member_name]
                            save_birthdays(birthdays)
                            return f"""
✅ *Birthday Removed*

Successfully removed {member_name}'s birthday from the group.

{get_random_ad()}
"""
                    
                    # Not found
                    return f"""
❌ *Name Not Found*

Could not find "{name}" in this group's birthday list.
Use *list* to see all birthdays.

{get_random_ad()}
"""
            else:
                # Remove from personal list
                if name in birthdays["personal"]:
                    removed_info = birthdays["personal"][name]
                    del birthdays["personal"][name]
                    save_birthdays(birthdays)
                    return f"""
✅ *Birthday Removed*

Successfully removed {name}'s birthday from your list.

{get_random_ad()}
"""
                else:
                    # Try case-insensitive search
                    for person_name in list(birthdays["personal"].keys()):
                        if person_name.lower() == name.lower():
                            del birthdays["personal"][person_name]
                            save_birthdays(birthdays)
                            return f"""
✅ *Birthday Removed*

Successfully removed {person_name}'s birthday from your list.

{get_random_ad()}
"""
                    
                    # Not found
                    return f"""
❌ *Name Not Found*

Could not find "{name}" in your birthday list.
Use *list* to see all birthdays.

{get_random_ad()}
"""

        # List birthdays command
        elif incoming_msg == 'list':
            birthdays = load_birthdays()
            today = datetime.now().date()

            # Helper function to format birthday listing
            def format_birthday_entry(name, birthday_info):
                bday = datetime.strptime(birthday_info["birthday"], "%d-%m-%Y")
                this_year_bday = bday.date().replace(year=today.year)
                if this_year_bday < today:
                    this_year_bday = this_year_bday.replace(year=today.year + 1)
                days_until = (this_year_bday - today).days
                
                if days_until == 0:
                    status = "🎉 TODAY! 🎂"
                elif days_until == 1:
                    status = "📅 Tomorrow!"
                else:
                    status = f"📆 In {days_until} days"
                    
                return f"• *{name}*: {bday.strftime('%d %B')} ({status})"

            if group_id and group_id in birthdays["groups"]:
                # List group birthdays
                group_info = birthdays["groups"][group_id]
                if not group_info["members"]:
                    return f"""
📋 *Group Birthday List*

No birthdays saved for this group yet.
Add one with: *add <name> <DD-MM-YYYY>*

{get_random_ad()}
"""
                else:
                    message = "📋 *Group Birthday List*\n\n"
                    
                    # Sort birthdays by days until
                    sorted_birthdays = []
                    for name, info in group_info["members"].items():
                        bday = datetime.strptime(info["birthday"], "%d-%m-%Y").date()
                        this_year_bday = bday.replace(year=today.year)
                        if this_year_bday < today:
                            this_year_bday = this_year_bday.replace(year=today.year + 1)
                        days_until = (this_year_bday - today).days
                        sorted_birthdays.append((name, info, days_until))
                    
                    sorted_birthdays.sort(key=lambda x: x[2])  # Sort by days until
                    
                    for name, info, _ in sorted_birthdays:
                        message += format_birthday_entry(name, info) + "\n"
                        
                    message += f"\n{get_random_ad()}"
                    return message
            else:
                # List personal birthdays
                if not birthdays["personal"]:
                    return f"""
📋 *Your Birthday List*

No birthdays saved yet.
Add one with: *add <name> <DD-MM-YYYY>*

{get_random_ad()}
"""
                else:
                    message = "📋 *Your Birthday List*\n\n"
                    
                    # Sort birthdays by days until
                    sorted_birthdays = []
                    for name, info in birthdays["personal"].items():
                        bday = datetime.strptime(info["birthday"], "%d-%m-%Y").date()
                        this_year_bday = bday.replace(year=today.year)
                        if this_year_bday < today:
                            this_year_bday = this_year_bday.replace(year=today.year + 1)
                        days_until = (this_year_bday - today).days
                        sorted_birthdays.append((name, info, days_until))
                    
                    sorted_birthdays.sort(key=lambda x: x[2])  # Sort by days until
                    
                    for name, info, _ in sorted_birthdays:
                        message += format_birthday_entry(name, info) + "\n"
                        
                    message += f"\n{get_random_ad()}"
                    return message

        # Next birthday command
        elif incoming_msg == 'next':
            today = datetime.now().date()
            birthdays = load_birthdays()
            next_birthdays = []

            # Calculate days until next birthday
            def days_until_birthday(date_str):
                bday = datetime.strptime(date_str, "%d-%m-%Y").date().replace(year=today.year)
                if bday < today:
                    bday = bday.replace(year=today.year + 1)
                return (bday - today).days

            # Collect relevant birthdays based on context
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
                context = "this group" if group_id else "your list"
                return f"""
📅 *No Birthdays Found*

There are no birthdays saved in {context} yet.
Add one with: *add <name> <DD-MM-YYYY>*

{get_random_ad()}
"""
            else:
                # Sort by days until birthday
                next_birthdays.sort(key=lambda x: x[2])
                next_person = next_birthdays[0]
                
                # Format date
                bday = datetime.strptime(next_person[1], "%d-%m-%Y")
                formatted_date = bday.strftime('%d %B')
                
                # Create appropriate message based on timing
                if next_person[2] == 0:
                    return f"""
🎉 *Today is {next_person[0]}'s Birthday!* 🎂

Don't forget to send your wishes!

{get_random_ad()}
"""
                elif next_person[2] == 1:
                    return f"""
🎂 *Birthday Tomorrow!*

*{next_person[0]}*'s birthday is tomorrow ({formatted_date})!
Time to prepare your wishes!

{get_random_ad()}
"""
                else:
                    return f"""
📆 *Next Birthday*

*{next_person[0]}* on {formatted_date}
That's {next_person[2]} days from today

{get_random_ad()}
"""

        # Default response for unknown commands
        else:
            return f"""
👋 *Birthday Alert Bot*

I didn't understand that command. Here's what I can do:

1️⃣ *add <name> <DD-MM-YYYY>* 
   Example: add Mom 15-05-1970

2️⃣ *list* - Show all saved birthdays

3️⃣ *next* - Show upcoming birthdays

4️⃣ *remove <name>* - Delete a birthday

5️⃣ *help* - Show this menu again

{get_random_ad()}
"""
            
    except Exception as e:
        logger.error(f"Error processing command: {str(e)}", exc_info=True)
        return f"""
❌ *Oops! Something went wrong*

Please try again or type *help* for assistance.

{get_random_ad()}
"""





















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
                # Send to individual
                message = f"🎂 Birthday Reminder: {person['name']}'s birthday is tomorrow! 🎉\n\n{get_random_ad()}"
                if OWNER_PHONE:
                    send_wati_message(OWNER_PHONE, message)

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
        
        # Extract message content (handle various possible field names)
        for field in ['text', 'body', 'message']:
            if field in data:
                incoming_msg = data.get(field, '').strip().lower()
                if incoming_msg:
                    break
        
        # Extract sender ID (handle various possible field names)
        for field in ['waId', 'from', 'sender', 'contactId']:
            if field in data:
                sender = data.get(field, '')
                if sender:
                    break
            
        # Check for group ID (handle various possible field names)
        for field in ['groupId', 'chatId', 'group_id']:
            if field in data:
                group_id = data.get(field)
                if group_id:
                    break
            
        logger.info(f"Extracted data: Message: '{incoming_msg}', Sender: '{sender}', Group: '{group_id}'")
        
        # Special handling for empty messages - just send help message
        if not incoming_msg and sender:
            response_message = process_command("help", sender, group_id)
            success = send_wati_message(sender, response_message)
            if success:
                logger.info(f"Sent help message to {sender} for empty message")
            else:
                logger.error(f"Failed to send help message to {sender}")
            return jsonify({"status": "success", "message": "Sent help message for empty request"}), 200
            
        # Only process if we have a message and sender
        if incoming_msg and sender:
            # Process commands
            response_message = process_command(incoming_msg, sender, group_id)
            
            # Send response via WATI API
            if response_message:
                success = send_wati_message(sender, response_message)
                if success:
                    logger.info(f"Successfully sent response to {sender}")
                else:
                    logger.error(f"Failed to send response to {sender}")
                
            return jsonify({"status": "success", "message": "Processed message"}), 200
        else:
            # If we don't have a message but the request came in, acknowledge it anyway
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

@app.route('/test_wati', methods=['GET'])
def test_wati():
    """Test WATI API connection"""
    try:
        phone = request.args.get('phone', OWNER_PHONE)
        if not phone:
            return jsonify({"status": "error", "message": "Please provide a phone number using the 'phone' query parameter"}), 400
        
        test_message = "🧪 This is a test message from your Birthday Alert Bot! 🎂\n\nIf you're seeing this, your WhatsApp integration is working correctly."
        
        logger.info(f"Testing WATI API connection for phone: {phone}")
        
        # Build the base endpoint
        base_endpoint = WATI_API_ENDPOINT
        if WATI_ACCOUNT_ID not in base_endpoint:
            base_endpoint = f"{base_endpoint}/{WATI_ACCOUNT_ID}"
        
        # Log detailed API information for debugging
        logger.info(f"WATI API Base URL: {base_endpoint}")
        logger.info(f"WATI Account ID: {WATI_ACCOUNT_ID}")
        logger.info(f"WATI Token Available: {bool(WATI_ACCESS_TOKEN)}")
        
        success = send_wati_message(phone, test_message)
        
        if success:
            return jsonify({"status": "success", "message": f"Test message sent to {phone} successfully"})
        else:
            # Try with a simpler message in case formatting is the issue
            simple_message = "Test message from Birthday Bot"
            simple_success = send_wati_message(phone, simple_message)
            
            if simple_success:
                return jsonify({"status": "success", "message": f"Simple test message sent to {phone} successfully"})
            else:
                return jsonify({
                    "status": "error", 
                    "message": "Failed to send test message. Check logs for details.",
                    "api_details": {
                        "endpoint": base_endpoint,
                        "account_id": WATI_ACCOUNT_ID
                    }
                }), 500
    except Exception as e:
        logger.error(f"Error in test_wati endpoint: {e}", exc_info=True)
        return jsonify({"status": "error", "message": str(e)}), 500

# Add a manual trigger for birthday notifications
@app.route('/send_notifications', methods=['GET'])
def send_notifications():
    """Manually trigger birthday notifications"""
    try:
        days_ahead = int(request.args.get('days', 1))
        upcoming = check_upcoming_birthdays(days_ahead=days_ahead)
        
        if not upcoming:
            return jsonify({"status": "success", "message": f"No birthdays found in the next {days_ahead} days"})
            
        birthdays = load_birthdays()
        notification_count = 0
        
        for person in upcoming:
            if "group_id" in person:
                # Send to group
                group_id = person["group_id"]
                group_info = birthdays["groups"][group_id]
                message = f"🎂 Reminder: {person['name']}'s birthday is {'today' if days_ahead == 0 else 'tomorrow' if days_ahead == 1 else f'in {days_ahead} days'}! 🎉\n\n{get_random_ad()}"        
                if send_wati_message(group_info["phone"], message):
                    notification_count += 1
            else:
                # Send to individual
                message = f"🎂 Birthday Reminder: {person['name']}'s birthday is {'today' if days_ahead == 0 else 'tomorrow' if days_ahead == 1 else f'in {days_ahead} days'}! 🎉\n\n{get_random_ad()}"
                recipient = OWNER_PHONE if OWNER_PHONE else person.get('phone', '')
                if recipient and send_wati_message(recipient, message):
                    notification_count += 1
                    
        return jsonify({
            "status": "success", 
            "message": f"Sent {notification_count} notification(s) for {len(upcoming)} upcoming birthday(s)",
            "upcoming_birthdays": [f"{p['name']} ({p['birthday']})" for p in upcoming]
        })
        
    except Exception as e:
        logger.error(f"Error sending notifications: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Add convenient endpoint to manually add a birthday for testing
@app.route('/add_birthday', methods=['GET'])
def add_test_birthday():
    """Add a test birthday for debugging"""
    try:
        name = request.args.get('name', 'Test Person')
        date_str = request.args.get('date', datetime.now().strftime('%d-%m-%Y'))
        phone = request.args.get('phone', OWNER_PHONE)
        
        try:
            date_obj = parse_date(date_str)
            formatted_date = format_birthday(date_obj)

            birthdays = load_birthdays()
            
            # Add to personal list
            birthdays["personal"][name] = {
                "birthday": formatted_date,
                "phone": phone,
                "added_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            save_birthdays(birthdays)
            
            # Calculate days until birthday
            today = datetime.now().date()
            bday = datetime.strptime(formatted_date, "%d-%m-%Y").date().replace(year=today.year)
            if bday < today:
                bday = bday.replace(year=today.year + 1)
            days_until = (bday - today).days
            
            return jsonify({
                "status": "success", 
                "message": f"Added {name}'s birthday ({formatted_date}) for testing",
                "days_until": days_until
            })
            
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error parsing date: {str(e)}"}), 400
            
    except Exception as e:
        logger.error(f"Error adding test birthday: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# Main execution block
if __name__ == '__main__':
    # Create data file if it doesn't exist
    if not os.path.exists(DATA_FILE):
        save_birthdays({"personal": {}, "groups": {}})
        logger.info(f"Created new birthdays data file: {DATA_FILE}")

    # Start scheduler thread
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.start()
    logger.info("Started scheduler thread")

    # Log configuration information
    logger.info(f"Starting Birthday Bot with the following configuration:")
    logger.info(f"WATI API Endpoint: {WATI_API_ENDPOINT}")
    logger.info(f"WATI Account ID: {WATI_ACCOUNT_ID}")
    logger.info(f"WhatsApp Number: {WHATSAPP_NUMBER if WHATSAPP_NUMBER else 'Not set'}")
    logger.info(f"Owner Phone: {OWNER_PHONE if OWNER_PHONE else 'Not set'}")
    
    # Run daily check on startup
    logger.info("Running initial birthday check...")
    daily_check()
    
    # Start the Flask app
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
