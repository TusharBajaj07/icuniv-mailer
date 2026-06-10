import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

# Gmail API scope for sending emails
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def authenticate_gmail():
    creds = None
    # The file token.json stores the user's access and refresh tokens
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)  # Download from Google Cloud Console
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    
    return build('gmail', 'v1', credentials=creds)

def send_email_from_training(service, to_email, subject, body_text, body_html=None):
    """
    Send email from training@iitb.ac.in alias
    """
    # Create message
    message = MIMEMultipart('alternative') if body_html else MIMEText(body_text)
    
    # Set headers - THIS IS THE CRUCIAL PART
    message['From'] = 'IIT Bombay Training Cell <training@iitb.ac.in>'
    message['To'] = to_email
    message['Subject'] = subject
    
    # Add body content
    if body_html:
        text_part = MIMEText(body_text, 'plain')
        html_part = MIMEText(body_html, 'html')
        message.attach(text_part)
        message.attach(html_part)
    
    # Encode message
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
    
    # Send email
    try:
        sent_message = service.users().messages().send(
            userId='me',
            body={'raw': raw_message}
        ).execute()
        
        print(f'Message sent successfully! Message ID: {sent_message["id"]}')
        return sent_message
    
    except Exception as error:
        print(f'An error occurred: {error}')
        return None
def main():
    # Authenticate and build service
    service = authenticate_gmail()
    
    # Example email details
    recipient_email = "23b2107@iitb.ac.in"
    email_subject = "Test Email from Training Cell"
    email_body = """
    Dear Recipient,
    
    This is a test email sent from IIT Bombay Training Cell.
    
    Best regards,
    Training Cell Team
    IIT Bombay
    """
    
    # Optional HTML body
    email_html = """
    <html>
        <body>
            <h2>IIT Bombay Training Cell</h2>
            <p>Dear Recipient,</p>
            <p>This is a test email sent from <strong>IIT Bombay Training Cell</strong>.</p>
            <p>Best regards,<br>
            Training Cell Team<br>
            IIT Bombay</p>
        </body>
    </html>
    """
    
    # Send the email
    result = send_email_from_training(
        service=service,
        to_email=recipient_email,
        subject=email_subject,
        body_text=email_body,
        body_html=email_html
    )
    
    if result:
        print("Email sent successfully from training@iitb.ac.in!")
    else:
        print("Failed to send email")

if __name__ == '__main__':
    main()
