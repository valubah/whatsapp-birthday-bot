# WhatsApp Birthday Alert Bot

## Overview
A WhatsApp bot to track and remind about birthdays using WATI API.

## Deployment
Deployed on Koyeb with Flask and Gunicorn.

## Environment Variables
- `WATI_ACCESS_TOKEN`: WATI API access token
- `WATI_API_ENDPOINT`: WATI API endpoint
- `WHATSAPP_NUMBER`: Your WhatsApp number
- `OWNER_PHONE`: Owner's phone number
- `PORT`: Application port (default: 5000)

## Setup
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set environment variables
4. Run with: `gunicorn app:app`
