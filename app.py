from flask import Flask, request, jsonify
from werkzeug.urls import url_quote  # Explicitly import url_quote

app = Flask(__name__)

@app.route('/')
def home():
    return "WhatsApp Birthday Bot is running!"

@app.route('/add_birthday', methods=['POST'])
def add_birthday():
    data = request.json
    name = data.get('name')
    birthday = data.get('birthday')
    
    # Here you would typically add logic to store the birthday
    # For now, we'll just return a success message
    return jsonify({
        "status": "success",
        "message": f"Birthday added for {name} on {birthday}"
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
