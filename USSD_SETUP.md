# USSD Setup

The Flask callback is `POST /ussd`. It supports the Africa's Talking USSD callback fields `phoneNumber` and `text`, and replies with `CON` to keep a session open or `END` to close it.

## Configure Africa's Talking

1. Generate a random webhook token and set it as `USSD_WEBHOOK_TOKEN` in your local `.env` file. Keep it private.
2. Deploy the Flask application to a public HTTPS URL.
3. In the Africa's Talking dashboard, set the USSD callback URL for your shortcode to `https://YOUR_HOST/ussd?token=YOUR_RANDOM_TOKEN`.
4. Test with a phone number that is already registered on a customer account. The stored phone number must be the same Tanzanian number as the caller ID; common `0...`, `255...`, and `+255...` formats are normalized.
5. Dial the shortcode and choose one of the menu options:
   - `1`: latest risk assessment
   - `2`: most recently added active farm
   - `3`: latest insurance recommendation

The callback uses the existing MySQL configuration in `.env` and the customer's `users.phone` value. No Africa's Talking SDK or API key is needed for incoming USSD sessions; the API key is used for outbound Africa's Talking services such as SMS. Do not add API keys to source code or commit them. The key shared in chat should be revoked and replaced in the Africa's Talking dashboard before using any outbound service.

## Local Testing

Africa's Talking must be able to reach the callback over the public internet. For local testing, expose the Flask server through a temporary HTTPS tunnel and configure that tunnel URL with `/ussd` as the callback. Do not use Flask's development server as a production deployment.
