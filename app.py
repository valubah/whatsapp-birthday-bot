import os
import json
import time
import schedule
import logging
import threading
import random
import traceback
import requests
from datetime import datetime, timedelta
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
# Added more robust environment variable loading with defaults
WATI_ACCESS_TOKEN = os.getenv('WATI_ACCESS_TOKEN', '')
WATI_API_ENDPOINT = os.getenv('WATI_API_ENDPOINT', '')
WHATSAPP_NUMBER = os.getenv('WHATSAPP_NUMBER', '')
OWNER_PHONE = os.getenv('OWNER_PHONE', '')

DATA_FILE = "/tmp/birthdays.json"  # Use /tmp for better compatibility

# Global scheduler thread
scheduler_thread = None

# Advertorial messages (kept from original code)
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
    """Load birthdays from JSON file with enhanced error handling"""
    try:
        # Ensure the directory exists
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        else:
            default_data = {"personal": {}, "groups": {}}
            save_birthdays(default_data)
            return default_data
    except Exception as e:
        logger.error(f"Error loading birthdays: {e}")
        logger.error(traceback.format_exc())
        return {"personal": {}, "groups": {}}


def save_birthdays(data):
    """Save birthdays to JSON file with enhanced logging"""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=4)
        logger.info(f"Birthdays saved successfully to {DATA_FILE}")
        return True
    except Exception as e:
        logger.error(f"Error saving birthdays: {e}")
        logger.error(traceback.format_exc())
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
    """Enhanced WATI message sending with comprehensive logging"""
    try:
        # Validate credentials
        if not WATI_ACCESS_TOKEN or not WATI_API_ENDPOINT:
            logger.error("WATI credentials not fully configured")
            return False

        # Normalize phone number
        recipient = recipient.lstrip('+')
        
        # Use full URL or construct it
        endpoint = WATI_API_ENDPOINT.rstrip('/') + f"/api/v1/sendSessionMessage/{recipient}"
        
        logger.info(f"Sending message to {recipient}")
        logger.info(f"Endpoint: {endpoint}")
        
        headers = {
            "Authorization": f"Bearer {WATI_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        
        payload = {"message": message}
        
        try:
            response = requests.post(
                endpoint, 
                headers=headers, 
                json=payload, 
                timeout=10
            )
            
            logger.info(f"WATI Response Status: {response.status_code}")
            logger.info(f"WATI Response Text: {response.text}")
            
            if response.status_code == 200:
                logger.info(f"Message sent successfully to {recipient}")
                return True
            else:
                logger.error(f"Failed to send message: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request error sending message: {req_err}")
            logger.error(traceback.format_exc())
            return False
            
    except Exception as e:
        logger.error(f"Unexpected error in send_wati_message: {e}")
        logger.error(traceback.format_exc())
        return False



def daily_check():
    """Daily birthday check with comprehensive logging"""
    try:
        logger.info("🕒 Running daily birthday check...")
        upcoming = check_upcoming_birthdays(days_ahead=1)
        logger.info(f"Found {len(upcoming)} upcoming birthdays")
        
        for person in upcoming:
            try:
                if "group_id" in person:
                    # Group birthday logic
                    message = f"🎂 Reminder: {person['name']}'s birthday is tomorrow! 🎉\n\n{get_random_ad()}"
                else:
                    # Personal birthday logic
                    message = f"🎂 Birthday Reminder: {person['name']}'s birthday is tomorrow! 🎉\n\n{get_random_ad()}"
                
                # Send to owner phone or group
                recipient = person.get('phone', OWNER_PHONE)
                if recipient:
                    send_wati_message(recipient, message)
                else:
                    logger.warning(f"No recipient found for {person['name']}'s birthday")
                
            except Exception as person_err:
                logger.error(f"Error processing {person['name']}'s birthday: {person_err}")
        
        logger.info("Daily birthday check completed")
    except Exception as e:
        logger.error(f"Critical error in daily check: {e}")
        logger.error(traceback.format_exc())





def run_scheduler():
    """Run the scheduler in a separate thread with enhanced error handling"""
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            logger.error(traceback.format_exc())
            time.sleep(60)  # Prevent tight error loop

@app.route('/')
def home():
    """Enhanced home route with system information"""
    return jsonify({
        "status": "Birthday Bot is running",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "wati_endpoint_configured": bool(WATI_API_ENDPOINT),
            "wati_token_configured": bool(WATI_ACCESS_TOKEN),
            "birthdays_file": DATA_FILE,
            "birthdays_count": {
                "personal": len(load_birthdays().get("personal", {})),
                "groups": len(load_birthdays().get("groups", {}))
            }
        }
    })

def main():
    """Main function to set up and start the application"""
    try:
        # Logging environment details for debugging
        logger.info("🚀 Starting Birthday Bot")
        logger.info(f"WATI Endpoint: {WATI_API_ENDPOINT}")
        logger.info(f"Data File: {DATA_FILE}")
        
        # Ensure data file exists
        if not os.path.exists(DATA_FILE):
            save_birthdays({"personal": {}, "groups": {}})
        
        # Schedule daily check at 9 AM
        schedule.every().day.at("09:00").do(daily_check)
        
        # Start scheduler in a daemon thread
        global scheduler_thread
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        
        logger.info("Scheduler thread started successfully")
        
    except Exception as e:
        logger.error(f"Error in main setup: {e}")
        logger.error(traceback.format_exc())

if __name__ == '__main__':
    # Initialize the application
    main()
    
    # Run Flask
    port = int(os.getenv('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=True)
else:
    # For WSGI servers
    main()



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
            
        # Parse incoming data from WATI
        logger.info(f"Received webhook request with content type: {request.content_type}")
        
        # Handle different content types
        if request.content_type and 'application/json' in request.content_type:
            data = request.json
            logger.info(f"Received JSON webhook data: {data}")
        else:
            try:
                data = request.get_json(force=True)
                logger.info(f"Forced JSON parsing: {data}")
            except:
                # Try to parse form data
                data = request.form.to_dict()
                logger.info(f"Received form data: {data}")
                if not data and request.data:
                    # Try to parse raw data
                    try:
                        data = json.loads(request.data.decode('utf-8'))
                        logger.info(f"Parsed raw data: {data}")
                    except:
                        logger.warning(f"Could not parse raw data: {request.data}")
                        data = {}
        
        # Extract message info - handle different WATI webhook formats
        incoming_msg = ""
        sender = ""
        group_id = None
        
        # Extract the message data correctly based on structure in your logs
        if 'text' in data:
            incoming_msg = data.get('text', '').strip().lower()
            # Get the sender from waId field based on your logs
            sender = data.get('waId', '')
            # Check if this is a group message
            group_id = data.get('groupId', data.get('chatId', None))
            
            logger.info(f"Extracted data from standard format: msg='{incoming_msg}', sender='{sender}', group='{group_id}'")
        
        # Log extracted data
        logger.info(f"Final extracted - Message: '{incoming_msg}', Sender: '{sender}', Group: '{group_id}'")
        
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
            return f"""
👋 Welcome to Whatsapp Birthday Alert Messenger!

I'll help you remember birthdays. Try these commands:
- *add <name> <DD-MM-YYYY>* e.g add valentine 25-12-1990
- *list*
- *help* (for more commands)

{get_random_ad()}
            """
            
    except Exception as e:
        logger.error(f"Error processing command: {e}")
        return f"❌ An error occurred. Please try again.\n\n{get_random_ad()}"

# Simple diagnostic endpoint to help with debugging webhook issues
@app.route('/diagnose', methods=['GET'])
def diagnose():
    """Diagnostic endpoint to check bot status"""
    try:
        status = {
            "bot_status": "running",
            "timestamp": datetime.now().isoformat(),
            "environment_vars": {
                "WATI_API_ENDPOINT": bool(WATI_API_ENDPOINT),
                "WATI_ACCESS_TOKEN": bool(WATI_ACCESS_TOKEN),
                "WHATSAPP_NUMBER": bool(WHATSAPP_NUMBER),
                "OWNER_PHONE": bool(OWNER_PHONE),
            },
            "birthdays_file_exists": os.path.exists(DATA_FILE),
            "birthdays_count": {
                "personal": len(load_birthdays().get("personal", {})),
                "groups": sum(len(group_info.get("members", {})) for group_id, group_info in load_birthdays().get("groups", {}).items())
            },
            "upcoming_birthdays": len(check_upcoming_birthdays(days_ahead=1))
        }
        return jsonify(status)
    except Exception as e:
        logger.error(f"Error in diagnose endpoint: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/test_wati', methods=['GET'])
def test_wati():
    """Test WATI API connection"""
    phone = request.args.get('phone', '')
    if not phone:
        return jsonify({"status": "error", "message": "Please provide a phone number using the 'phone' query parameter"}), 400
    
    test_message = "🧪 This is a test message from your Birthday Alert Bot! 🎂"
    success = send_wati_message(phone, test_message)
    
    if success:
        return jsonify({"status": "success", "message": f"Test message sent to {phone} successfully"})
    else:
        return jsonify({"status": "error", "message": "Failed to send test message. Check logs for details."}), 500

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
