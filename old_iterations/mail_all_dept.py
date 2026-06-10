import os
import time
import json
import base64
import pandas as pd
import PyPDF2
import re

from dotenv import load_dotenv
from typing import Dict, List
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr

from google import genai
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class PlacementCellOutreach:
    def __init__(self, api_key: str = None):
        """Initialize the placement cell outreach system"""
        load_dotenv()
        
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Please set GEMINI_API_KEY in .env file")
        
        self.client = genai.Client(api_key=self.api_key)
        
        # Department context loading
        # Load descriptions from iitb_research_summary.json
        self.load_summary_from_json("iitb_research_summary.json")
        # Load all department PDFs (dept_pdfs/<Dept>.pdf)
        self.load_all_dept_contexts("dept_pdfs")
        
        # Gmail API Configuration
        self.scopes = ['https://www.googleapis.com/auth/gmail.send']
        self.sender_email = "training@iitb.ac.in"
        self.sender_name = "Practical Training Cell"
        
        # Initialize Gmail API service
        self.gmail_service = self.authenticate_gmail()

    def authenticate_gmail(self):
        """Authenticate with Gmail API using OAuth2"""
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.scopes)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    raise ValueError("credentials.json file not found. Please download it from Google Cloud Console.")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.scopes)
                creds = flow.run_local_server(port=0)
            
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        
        return build('gmail', 'v1', credentials=creds)

    def extract_text_from_pdf(self, path: str) -> str:
        """Utility to extract all text from a PDF file."""
        text = ""
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t
        return text

    def load_summary_from_json(self, json_file: str):
        """Load department and centre descriptions from JSON file."""
        self.dept_descriptions = {}
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Load departments
            if 'iit_bombay_research_summary' in data:
                summary = data['iit_bombay_research_summary']
                
                # Load departments
                if 'departments' in summary:
                    for dept in summary['departments']:
                        name = dept['name']
                        description = dept['research_summary']
                        self.dept_descriptions[name] = description
                
                # Load centres
                if 'centres' in summary:
                    for centre in summary['centres']:
                        name = centre['name']
                        description = centre['research_summary']
                        self.dept_descriptions[name] = description
            
            print(f"✅ Loaded {len(self.dept_descriptions)} departments/centres from {json_file}")
            print(f"📋 Available: {list(self.dept_descriptions.keys())}")
            
        except Exception as e:
            print(f"❌ Error loading JSON file: {e}")
            self.dept_descriptions = {}

    def load_all_dept_contexts(self, folder="dept_pdfs"):
        """Load each <Dept>.pdf into dept_contexts dict (first 6000 chars)."""
        self.dept_contexts = {}
        
        if not os.path.exists(folder):
            print(f"⚠️ Warning: {folder} directory not found!")
            return
        
        for fname in os.listdir(folder):
            if fname.lower().endswith(".pdf"):
                # Extract department name from filename (remove .pdf extension)
                dept_name = fname[:-4]
                file_path = os.path.join(folder, fname)
                
                try:
                    text = self.extract_text_from_pdf(file_path)
                    self.dept_contexts[dept_name] = text[:6000]
                except Exception as e:
                    print(f"⚠️ Error loading {fname}: {e}")
        
        print(f"✅ Loaded {len(self.dept_contexts)} department PDF contexts from {folder}")
        print(f"📁 Available PDFs: {list(self.dept_contexts.keys())}")

    def research_professor_domains(self, professor_name: str, university: str) -> Dict:
        """Research professor and extract 3 specific research domains"""
        research_prompt = f"""
        Research Professor {professor_name} from {university} and identify their research work.
        
        Extract exactly 3 SPECIFIC research domains they work in. Be very specific - mention:
        - Exact technical areas (not generic terms)
        - Specific methodologies or technologies they use
        - Particular applications or systems they focus on
        - Each domain should be less than 15 words
        
        Format your response as:
        DOMAIN 1: [Specific research area]
        DOMAIN 2: [Specific research area]
        DOMAIN 3: [Specific research area]
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=research_prompt
            )
            domains = []
            for line in response.text.split('\n'):
                if line.strip().startswith('DOMAIN'):
                    domain = line.split(':', 1)[1].strip()
                    domains.append(domain)
            if len(domains) < 3:
                lines = [l.strip() for l in response.text.split('\n') if l.strip() and not l.startswith('DOMAIN')]
                domains += lines[:3 - len(domains)]
            while len(domains) < 3:
                domains.append("Advanced engineering research")
            return {
                "professor": professor_name,
                "university": university,
                "domain1": domains[0],
                "domain2": domains[1],
                "domain3": domains[2],
                "success": True
            }
        except Exception as e:
            print(f"Research failed for {professor_name}: {e}")
            return {
                "professor": professor_name,
                "university": university,
                "domain1": "Advanced engineering research",
                "domain2": "Computational modeling",
                "domain3": "Experimental techniques",
                "success": False
            }

    def select_relevant_depts(self, research_domains: Dict) -> List[str]:
        """Use LLM to pick 1–2 departments based on their summaries from JSON."""
        dept_list = "\n\n".join(f"{k}:\n{v}" for k, v in self.dept_descriptions.items())
        
        prompt = f"""
        Professor's research domains:
        1. {research_domains['domain1']}
        2. {research_domains['domain2']}
        3. {research_domains['domain3']}

        Here are IIT Bombay departments and centres with their research focus:
        {dept_list}

        Select the ONE or TWO most relevant departments/centres that best match these research domains.
        Respond ONLY with a JSON array containing the EXACT names as shown above.
        Example format: ["Aerospace Engineering", "Mechanical Engineering"]
        OR: ["Centre for Machine Intelligence & Data Science (C-MInDS)", "Computer Science & Engineering"]
        
        IMPORTANT: Use EXACT names from the list above, including any text in parentheses.
        """
        
        try:
            resp = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            ).text.strip()
            
            # Extract JSON from response
            json_match = re.search(r'\[.*?\]', resp, re.DOTALL)
            if json_match:
                resp = json_match.group()
            
            chosen = json.loads(resp)
            
            # Validate that chosen departments exist in dept_contexts
            valid_depts = []
            for dept in chosen:
                if dept in self.dept_contexts:
                    valid_depts.append(dept)
                else:
                    # Try to find closest match
                    print(f"⚠️ Department '{dept}' not found in PDF contexts.")
                    print(f"   Looking for matching PDF file...")
                    
                    # Check for exact match or close variant
                    found = False
                    for available_dept in self.dept_contexts.keys():
                        # Check if names match (ignoring case and special characters)
                        if dept.lower().replace('&', 'and') == available_dept.lower().replace('&', 'and'):
                            valid_depts.append(available_dept)
                            print(f"✅ Matched '{dept}' to PDF: '{available_dept}.pdf'")
                            found = True
                            break
                    
                    if not found:
                        # Try partial matching
                        for available_dept in self.dept_contexts.keys():
                            if dept.lower() in available_dept.lower() or available_dept.lower() in dept.lower():
                                valid_depts.append(available_dept)
                                print(f"✅ Partial match '{dept}' to PDF: '{available_dept}.pdf'")
                                found = True
                                break
                    
                    if not found:
                        print(f"❌ No matching PDF found for '{dept}'")
            
            # Limit to 2 departments maximum
            if valid_depts:
                return valid_depts[:2]
            else:
                print("⚠️ No valid departments found. Using fallback departments.")
                return list(self.dept_contexts.keys())[:2]
            
        except Exception as e:
            print(f"⚠️ Error in department selection: {e}")
            print(f"Response was: {resp}")
            # Return first 2 available departments as fallback
            return list(self.dept_contexts.keys())[:2]

    def find_iitb_connection_with_ctx(self, research_domains: Dict, dept_ctx: str) -> str:
        """Generate one connection sentence using selected dept contexts."""
        prompt = f"""
        Based on these research domains:
        - {research_domains['domain1']}
        - {research_domains['domain2']}
        - {research_domains['domain3']}
        
        And this IIT Bombay department research context:
        {dept_ctx}
        
        Provide ONE brief sentence (45-50 words) mentioning a specific IIT Bombay research project, 
        publication, or collaboration that connects to their work specifically the research domain you pick. Be specific - mention actual 
        technical terms, methods, or applications. *Do not take professors name at any cost*
        
        Format: "Students of IIT Bombay have had prior exposure to advanced research, having collaborated with professors from the [Department Name/Names] on publications and projects such as [specific research/publication details], which align closely with the domains mentioned above."
        
        Make it sound authentic and technical, not generic and should be a little detailed
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            print(f"⚠️ Error generating connection: {e}")
            return "Your research areas align closely with ongoing work at IIT Bombay in advanced engineering and computational methods."

    def convert_markdown_to_html(self, text: str) -> str:
        """Convert **bold** markdown to <strong>bold</strong> HTML"""
        return re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)

    def generate_html_email(self, prof: Dict, research_data: Dict) -> tuple:
        """Generate HTML email and return subject and body separately"""
        # 1) Select departments
        selected_depts = self.select_relevant_depts(research_data)
        
        # 2) Print chosen dept info for debugging/traceability
        if selected_depts:
            chosen_info = ", ".join(selected_depts)
            print(f"✅ Selected departments: {chosen_info}")
            for d in selected_depts:
                print(f"   📄 Using PDF: dept_pdfs/{d}.pdf")
        else:
            print("⚠️ Selected departments: None (using fallback)")
            selected_depts = list(self.dept_contexts.keys())[:2]

        # 3) Combine their full contexts
        combined_ctx = "\n\n".join(self.dept_contexts[d] for d in selected_depts if d in self.dept_contexts)
        
        # 4) Get connection sentence with combined context
        iitb_connection = self.find_iitb_connection_with_ctx(research_data, combined_ctx)
        iitb_connection = self.convert_markdown_to_html(iitb_connection)
        
        # 5) Prepare email content
        name_parts = prof['name'].split()
        last_name = name_parts[-1] if len(name_parts) > 1 else prof['name']
        domain1 = self.convert_markdown_to_html(research_data['domain1'])
        domain2 = self.convert_markdown_to_html(research_data['domain2'])
        domain3 = self.convert_markdown_to_html(research_data['domain3'])
        
        subject = "Invitation for Research Internship Collaboration with IIT Bombay"
        
        html_body = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{subject}</title>
</head>
<body>
    <div style="font-size:small; font-family: Arial, sans-serif; line-height: 1.4; color: #333;">
        
        <p>Dear Prof. {last_name},</p>
        
        <p>I, <strong>Tushar Bajaj</strong>, am writing on the behalf of <strong>Practical Training Cell of IIT Bombay.</strong></p>
        
        <p>IIT Bombay is recognized as India's premier technological institute, consistently attracting the finest analytical minds from across the country, with an acceptance rate of less than 0.4%. It is also ranked as the top technological university in India.</p>
        
        <p>With a strong inclination towards engineering and technology-related domains, students at IIT Bombay are intrigued by your recent research work in:</p>
        
        <ul style="margin-left: 20px;">
            <li><strong>{domain1}</strong></li>
            <li><strong>{domain2}</strong></li>
            <li><strong>{domain3}</strong></li>
        </ul>
        
        <p>{iitb_connection}</p>
        
        <p>Over the past few years, reputed universities such as MIT, ETH Zurich, Carnegie Mellon University, UCD, NTU Singapore, University of California Merced, University of Maryland, and Stanford University have hosted IIT Bombay students for summer research internships.</p>
        
        <p>On behalf of the Practical Training Cell, I would like to cordially invite your esteemed university to participate in our <strong>summer internship</strong> recruitment program for the year 2025–26. Our students are available for research internships of 8–9 weeks from May 2026 to mid-July 2026.</p>
        
        <p>We sincerely look forward to the possibility of collaboration and to facilitating a smooth recruitment process at IIT Bombay.</p>
        
        <p>Thanks and Regards,</p>
        
    </div>
    
    <br>
    
    <table style="color:rgb(0,0,0); font-family:arial,helvetica,sans-serif; border-width:medium; border-style:none; border-collapse:collapse;">
        <tbody>
            <tr style="height:0pt;">
                <td style="padding:5pt; border-right:1.5pt solid rgb(17,85,204); vertical-align:top;">
                    <p dir="ltr" style="margin-top:0pt; margin-bottom:0pt; line-height:1.2;">
                        <span style="font-size:11pt; font-family:Arial; background-color:transparent; vertical-align:baseline;">
                            <img src="cid:iitb_logo" 
                                 width="101" 
                                 height="87" 
                                 style="border-width: medium; border-style: none;" 
                                 alt="IIT Bombay Logo">
                        </span>
                    </p>
                </td>
                <td style="padding:5pt; border-left:1.5pt solid rgb(17,85,204); vertical-align:top;">
                    <p dir="ltr" style="margin-top:0pt; margin-bottom:0pt; line-height:1.2;">
                        <font color="#3d85c6" face="georgia">
                            <span style="font-size:16px;">
                                <b>Tushar Bajaj</b>
                            </span>
                        </font>
                    </p>
                    <p dir="ltr" style="margin-top:0pt; margin-bottom:0pt; line-height:1.38; color:rgb(34,34,34); font-size:12.8px;">
                        <span style="font-size:9.5pt; font-family:georgia; color:rgb(102,102,102); vertical-align:baseline;">
                            Internship Coordinator
                        </span>
                    </p>
                    <p dir="ltr" style="margin-top:0pt; margin-bottom:0pt; line-height:1.38; color:rgb(34,34,34); font-size:12.8px;">
                        <span style="font-size:9.5pt; font-family:georgia; color:rgb(102,102,102); vertical-align:baseline;">
                            Institute Placement Team 2025-26
                        </span>
                    </p>
                    <p dir="ltr" style="margin-top:0pt; margin-bottom:0pt; line-height:1.38; color:rgb(34,34,34); font-size:12.8px;">
                        <span style="font-size:9.5pt; font-family:georgia; color:rgb(61,133,198); font-weight:700; vertical-align:baseline;">
                            Indian Institute of Technology, Bombay
                        </span>
                    </p>
                    <p dir="ltr" style="margin-top:0pt; margin-bottom:0pt; line-height:1.38; font-size:12.8px; color:rgb(80,0,80);">
                        <span style="font-size:9.5pt; font-family:georgia; vertical-align:baseline;">
                            <font color="#666666">
                                Contact: (+91) 9205811174 | 
                                <a href="https://www.linkedin.com/in/tushar-bajaj-207b79221/" target="_blank">LinkedIn</a>
                            </font>
                        </span>
                    </p>
                </td>
            </tr>
        </tbody>
    </table>
    
</body>
</html>'''
        
        return subject, html_body

    def send_email(self, to_email: str, subject: str, html_content: str, logo_path: str = "logo.png") -> bool:
        """Send HTML email with embedded logo using Gmail API"""
        try:
            if not os.path.exists(logo_path):
                html_content = html_content.replace('src="cid:iitb_logo"', 'style="display:none;"')

            message = MIMEMultipart('related')
            message['From'] = formataddr((self.sender_name, self.sender_email))
            message['To'] = to_email
            message['Subject'] = subject

            msg_alt = MIMEMultipart('alternative')
            message.attach(msg_alt)
            msg_alt.attach(MIMEText(html_content, 'html'))

            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as f:
                    img_data = f.read()
                img = MIMEImage(img_data)
                img.add_header('Content-ID', '<iitb_logo>')
                image_filename = os.path.basename(logo_path)
                img.add_header('Content-Disposition', 'inline', filename=image_filename)
                message.attach(img)

            raw_msg = base64.urlsafe_b64encode(message.as_bytes()).decode()
            self.gmail_service.users().messages().send(
                userId='me', body={'raw': raw_msg}
            ).execute()

            print(f"✅ Email sent successfully to {to_email}")
            return True
        except Exception as e:
            print(f"❌ Failed to send email to {to_email}. Error: {e}")
            return False

    def process_and_send_emails(self, csv_file: str, log_file: str = "email_sending_log.json") -> List[Dict]:
        """Process professors and send emails directly using Gmail API"""
        try:
            df = pd.read_csv(csv_file)
            if 'email_sent' not in df.columns:
                df['email_sent'] = False

            results, sent_count, failed_count = [], 0, 0
            print(f"\n📧 Starting Gmail API email campaign for {len(df)} professors...")
            print(f"📨 Using sender address: {self.sender_email}")
            print("="*60 + "\n")
            
            for idx, prof in df.iterrows():
                if prof.get('email_sent', False):
                    print(f"⏭️  Skipping {prof['name']} - Email already sent\n")
                    continue

                print(f"\n{'='*60}")
                print(f"Processing Professor: {prof['name']}")
                print(f"University: {prof['university']}")
                print(f"{'='*60}")
                
                research_data = self.research_professor_domains(prof['name'], prof['university'])
                
                print(f"\n🔬 Research Domains Identified:")
                print(f"   1. {research_data['domain1']}")
                print(f"   2. {research_data['domain2']}")
                print(f"   3. {research_data['domain3']}\n")
                
                subject, html_body = self.generate_html_email(prof.to_dict(), research_data)
                email_success = self.send_email(prof['email'], subject, html_body, "logo.png")
                
                df.at[idx, 'email_sent'] = email_success
                if email_success:
                    sent_count += 1
                else:
                    failed_count += 1

                result = {
                    "prof_name": prof['name'],
                    "prof_email": prof['email'],
                    "university": prof['university'],
                    "subject": subject,
                    "email_sent": email_success,
                    "domain1": research_data['domain1'],
                    "domain2": research_data['domain2'],
                    "domain3": research_data['domain3'],
                    "research_success": research_data['success'],
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                results.append(result)

                with open(log_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "campaign_info": {
                            "total_processed": len(results),
                            "emails_sent": sent_count,
                            "emails_failed": failed_count,
                            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "method": "Gmail API with OAuth2",
                            "sender_address": self.sender_email
                        },
                        "results": results
                    }, f, indent=2, ensure_ascii=False)

                df.to_csv(csv_file, index=False)
                print(f"\n⏱️ Waiting 2 seconds before next email...\n")
                time.sleep(2)
            
            print("\n" + "="*60)
            print(f"📊 GMAIL API EMAIL CAMPAIGN SUMMARY:")
            print(f"✅ Successfully sent: {sent_count} emails")
            print(f"❌ Failed to send: {failed_count} emails")
            print(f"📄 Log saved to: {log_file}")
            print("="*60)
            
            return results
            
        except Exception as e:
            print(f"💥 Error in Gmail API email campaign: {e}")
            return []


def main():
    print("🚀 IIT Bombay Placement Cell - Professor Outreach System (Gmail API)")
    print("=" * 70)
    
    try:
        placement_system = PlacementCellOutreach()
        print("✅ System initialized successfully")
        print(f"📧 Gmail API authenticated")
        print(f"📨 Sender configured: {placement_system.sender_email}")
    except Exception as e:
        print(f"❌ System initialization failed: {e}")
        return
    
    results = placement_system.process_and_send_emails("professors.csv")
    if results:
        print(f"\n🎯 Gmail API campaign completed! Processed {len(results)} professors")
        print("\n🔬 Sample research domains extracted:")
        for i, result in enumerate(results[:3]):
            if result['research_success']:
                print(f"\n{i+1}. {result['prof_name']}:")
                print(f"   • {result['domain1']}")
                print(f"   • {result['domain2']}")
                print(f"   • {result['domain3']}")
    print("\n🏁 Program completed!")


if __name__ == "__main__":
    main()
