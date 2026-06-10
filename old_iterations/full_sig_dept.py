import os
import time
import json
import base64
import pandas as pd
import PyPDF2
import re
import signal
from contextlib import contextmanager

from dotenv import load_dotenv
from typing import Dict, List
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr

from google import genai
from google.genai import types
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


@contextmanager
def timeout_handler(seconds):
    """Context manager for handling timeouts"""
    def timeout_signal_handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds} seconds")
    
    # Set the signal handler and alarm
    old_handler = signal.signal(signal.SIGALRM, timeout_signal_handler)
    signal.alarm(seconds)
    
    try:
        yield
    finally:
        # Restore the old handler and cancel the alarm
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


class PlacementCellOutreach:
    def __init__(self, api_key: str = None):
        """Initialize the placement cell outreach system"""
        load_dotenv()
        
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Please set GEMINI_API_KEY in .env file")
        
        self.client = genai.Client(api_key=self.api_key)
        
        # Department context loading
        self.load_summary_from_json("iitb_research_summary.json")
        self.load_all_dept_contexts("dept_pdfs")
        
        # Load IC contacts
        self.load_ic_contacts("contacts.csv")
        
        # Gmail API Configuration
        self.scopes = ['https://www.googleapis.com/auth/gmail.send']
        self.sender_email = "training@iitb.ac.in"
        self.sender_name = "Practical Training Cell"
        
        # Initialize Gmail API service
        self.gmail_service = self.authenticate_gmail()

    def load_ic_contacts(self, csv_file: str):
        """Load Internship Coordinator contact information from CSV"""
        try:
            self.ic_contacts = pd.read_csv(csv_file)
            # Create a dictionary for easy lookup
            self.ic_dict = {}
            for _, row in self.ic_contacts.iterrows():
                self.ic_dict[row['name_IC']] = {
                    'name': row['name_IC'],
                    'phone': row['ph_no'],
                    'linkedin': row['linkedin_link']
                }
            print(f"✅ Loaded {len(self.ic_dict)} IC contacts from {csv_file}")
            print(f"📋 Available ICs: {list(self.ic_dict.keys())}")
        except Exception as e:
            print(f"❌ Error loading IC contacts: {e}")
            self.ic_dict = {}

    def get_ic_info(self, ic_name: str) -> Dict:
        """Retrieve IC contact information by name"""
        if ic_name in self.ic_dict:
            return self.ic_dict[ic_name]
        else:
            print(f"⚠️ IC '{ic_name}' not found in contacts.csv. Using default.")
            # Return default values if IC not found
            return {
                'name': 'Tushar Bajaj',
                'phone': '(+91) 9205811174',
                'linkedin': 'https://www.linkedin.com/in/tushar-bajaj-207b79221/'
            }

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
            
            if 'iit_bombay_research_summary' in data:
                summary = data['iit_bombay_research_summary']
                
                if 'departments' in summary:
                    for dept in summary['departments']:
                        name = dept['name']
                        description = dept['research_summary']
                        self.dept_descriptions[name] = description
                
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
                dept_name = fname[:-4]
                file_path = os.path.join(folder, fname)
                
                try:
                    text = self.extract_text_from_pdf(file_path)
                    self.dept_contexts[dept_name] = text[:6000]
                except Exception as e:
                    print(f"⚠️ Error loading {fname}: {e}")
        
        print(f"✅ Loaded {len(self.dept_contexts)} department PDF contexts from {folder}")
        print(f"📁 Available PDFs: {list(self.dept_contexts.keys())}")

    def validate_research_quality(self, response_text: str, domains: List[str]) -> Dict:
        """Validate if the research information is adequate and not generic/unavailable"""
        
        # Keywords that indicate no data found or poor quality response
        negative_keywords = [
            "could not find",
            "couldn't find",
            "unable to find",
            "no information",
            "not available",
            "insufficient information",
            "limited information",
            "cannot identify",
            "can't identify",
            "no data",
            "i don't have",
            "i do not have",
            "not enough information",
            "unable to access",
            "no specific",
            "generic",
            "general research"
        ]
        
        response_lower = response_text.lower()
        
        # Check for negative indicators
        for keyword in negative_keywords:
            if keyword in response_lower:
                return {
                    "valid": False,
                    "reason": f"Response contains '{keyword}' - indicating insufficient data",
                    "response_preview": response_text[:200]
                }
        
        # Check if domains are too generic or placeholder-like
        generic_domains = [
            "advanced engineering research",
            "computational modeling",
            "experimental techniques",
            "general research",
            "various research",
            "research work",
            "academic research"
        ]
        
        generic_count = sum(1 for domain in domains if any(gen.lower() in domain.lower() for gen in generic_domains))
        
        if generic_count >= 2:
            return {
                "valid": False,
                "reason": f"Research domains are too generic ({generic_count}/3 domains)",
                "generic_domains": domains
            }
        
        # Check if domains are too short (likely incomplete)
        if any(len(domain.strip()) < 10 for domain in domains):
            return {
                "valid": False,
                "reason": "One or more domains are too short or incomplete",
                "domains": domains
            }
        
        return {
            "valid": True,
            "reason": "Research information is adequate and specific"
        }

    def research_professor_domains(self, professor_name: str, university: str) -> Dict:
        """Research professor and extract 3 specific research domains using Google Search Grounding"""
        research_prompt = f"""
        Research Professor {professor_name} from {university} and identify their current research work.
        
        Find their recent publications, research interests from their university profile, Google Scholar, 
        or research pages.
        
        If you cannot find specific information about this professor, explicitly state "I could not find sufficient information about Professor {professor_name}."
        
        Otherwise, extract exactly 3 SPECIFIC research domains they work in. Be very specific - mention:
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
            # Create Google Search grounding tool
            grounding_tool = types.Tool(
                google_search=types.GoogleSearch()
            )
            
            # Configure generation with grounding
            config = types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=1.0  # Recommended for grounding
            )
            
            # Generate content with Google Search grounding
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=research_prompt,
                config=config
            )
            
            # Store full response for logging
            full_response_text = response.text
            
            # Check if grounding was used
            grounded = False
            search_queries = []
            grounding_sources = []
            
            if hasattr(response, 'candidates') and len(response.candidates) > 0:
                candidate = response.candidates[0]
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    grounded = True
                    if hasattr(candidate.grounding_metadata, 'web_search_queries'):
                        search_queries = candidate.grounding_metadata.web_search_queries
                    
                    # Extract grounding sources if available
                    if hasattr(candidate.grounding_metadata, 'grounding_chunks'):
                        for chunk in candidate.grounding_metadata.grounding_chunks[:5]:  # Top 5 sources
                            if hasattr(chunk, 'web') and hasattr(chunk.web, 'uri'):
                                grounding_sources.append({
                                    'url': chunk.web.uri,
                                    'title': getattr(chunk.web, 'title', 'N/A')
                                })
            
            print(f"🔍 Google Search Grounding: {'✅ Used' if grounded else '⚠️ Not used (answered from knowledge)'}")
            if search_queries:
                print(f"   Search queries: {search_queries}")
            if grounding_sources:
                print(f"   Sources found: {len(grounding_sources)}")
            
            # Extract domains from response
            domains = []
            for line in full_response_text.split('\n'):
                if line.strip().startswith('DOMAIN'):
                    domain = line.split(':', 1)[1].strip()
                    domains.append(domain)
            
            if len(domains) < 3:
                lines = [l.strip() for l in full_response_text.split('\n') 
                        if l.strip() and not l.startswith('DOMAIN')]
                domains += lines[:3 - len(domains)]
            
            # Validate research quality
            validation = self.validate_research_quality(full_response_text, domains)
            
            if not validation['valid']:
                print(f"❌ Research validation failed: {validation['reason']}")
                return {
                    "professor": professor_name,
                    "university": university,
                    "domain1": domains[0] if len(domains) > 0 else "N/A",
                    "domain2": domains[1] if len(domains) > 1 else "N/A",
                    "domain3": domains[2] if len(domains) > 2 else "N/A",
                    "success": False,
                    "grounded": grounded,
                    "search_queries": search_queries,
                    "grounding_sources": grounding_sources,
                    "validation": validation,
                    "full_response": full_response_text,
                    "error_type": "insufficient_data"
                }
            
            # Ensure we have exactly 3 domains
            while len(domains) < 3:
                domains.append("Research domain not specified")
            
            print(f"✅ Research validation passed")
            
            return {
                "professor": professor_name,
                "university": university,
                "domain1": domains[0],
                "domain2": domains[1],
                "domain3": domains[2],
                "success": True,
                "grounded": grounded,
                "search_queries": search_queries,
                "grounding_sources": grounding_sources,
                "validation": validation,
                "full_response": full_response_text
            }
            
        except Exception as e:
            print(f"❌ Research failed for {professor_name}: {e}")
            return {
                "professor": professor_name,
                "university": university,
                "domain1": "N/A",
                "domain2": "N/A",
                "domain3": "N/A",
                "success": False,
                "grounded": False,
                "search_queries": [],
                "grounding_sources": [],
                "validation": {"valid": False, "reason": f"Exception: {str(e)}"},
                "full_response": "",
                "error_type": "exception",
                "error_message": str(e)
            }

    def get_llm_suggested_depts(self, research_domains: Dict) -> List[str]:
        """Get raw LLM suggested departments without any fallback logic"""
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
                model="gemini-2.5-flash-lite",
                contents=prompt
            ).text.strip()
            
            json_match = re.search(r'\[.*?\]', resp, re.DOTALL)
            if json_match:
                resp = json_match.group()
            
            chosen = json.loads(resp)
            return chosen
        except Exception as e:
            print(f"⚠️ Error in LLM department suggestion: {e}")
            return []

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
                model="gemini-2.5-flash-lite",
                contents=prompt
            ).text.strip()
            
            json_match = re.search(r'\[.*?\]', resp, re.DOTALL)
            if json_match:
                resp = json_match.group()
            
            chosen = json.loads(resp)
            
            valid_depts = []
            for dept in chosen:
                if dept in self.dept_contexts:
                    valid_depts.append(dept)
                else:
                    print(f"⚠️ Department '{dept}' not found in PDF contexts.")
                    print(f"   Looking for matching PDF file...")
                    
                    found = False
                    for available_dept in self.dept_contexts.keys():
                        if dept.lower().replace('&', 'and') == available_dept.lower().replace('&', 'and'):
                            valid_depts.append(available_dept)
                            print(f"✅ Matched '{dept}' to PDF: '{available_dept}.pdf'")
                            found = True
                            break
                    
                    if not found:
                        for available_dept in self.dept_contexts.keys():
                            if dept.lower() in available_dept.lower() or available_dept.lower() in dept.lower():
                                valid_depts.append(available_dept)
                                print(f"✅ Partial match '{dept}' to PDF: '{available_dept}.pdf'")
                                found = True
                                break
                    
                    if not found:
                        print(f"❌ No matching PDF found for '{dept}'")
            
            if valid_depts:
                return valid_depts[:2]
            else:
                print("⚠️ No valid departments found. Using fallback departments.")
                return list(self.dept_contexts.keys())[:2]
            
        except Exception as e:
            print(f"⚠️ Error in department selection: {e}")
            print(f"Response was: {resp}")
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
                model="gemini-2.5-flash-lite",
                contents=prompt
            )
            return response.text.strip()
        except Exception as e:
            print(f"⚠️ Error generating connection: {e}")
            return "Your research areas align closely with ongoing work at IIT Bombay in advanced engineering and computational methods."

    def convert_markdown_to_html(self, text: str) -> str:
        """Convert **bold** markdown to <strong>bold</strong> HTML"""
        return re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)

    def generate_html_email(self, prof: Dict, research_data: Dict, ic_info: Dict) -> tuple:
        """Generate HTML email and return subject and body separately"""
        # Select departments
        selected_depts = self.select_relevant_depts(research_data)
        
        if selected_depts:
            chosen_info = ", ".join(selected_depts)
            print(f"✅ Selected departments: {chosen_info}")
            for d in selected_depts:
                print(f"   📄 Using PDF: dept_pdfs/{d}.pdf")
        else:
            print("⚠️ Selected departments: None (using fallback)")
            selected_depts = list(self.dept_contexts.keys())[:2]

        # Combine contexts
        combined_ctx = "\n\n".join(self.dept_contexts[d] for d in selected_depts if d in self.dept_contexts)
        
        # Get connection sentence
        iitb_connection = self.find_iitb_connection_with_ctx(research_data, combined_ctx)
        iitb_connection = self.convert_markdown_to_html(iitb_connection)
        
        # Prepare email content
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
        
        <p>I, <strong>{ic_info['name']}</strong>, am writing on the behalf of <strong>Practical Training Cell of IIT Bombay.</strong></p>
        
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
                                <b>{ic_info['name']}</b>
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
                                Contact: {ic_info['phone']} | 
                                <a href="{ic_info['linkedin']}" target="_blank">LinkedIn</a>
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

            results, sent_count, failed_count, skipped_count, no_data_count, timeout_count = [], 0, 0, 0, 0, 0
            print(f"\n📧 Starting Gmail API email campaign for {len(df)} professors...")
            print(f"📨 Using sender address: {self.sender_email}")
            print(f"🔍 Google Search Grounding: ENABLED")
            print(f"✅ Research Validation: ENABLED")
            print("="*60 + "\n")
            
            for idx, prof in df.iterrows():
                if prof.get('email_sent', False):
                    print(f"⏭️  Skipping {prof['name']} - Email already sent\n")
                    continue

                print(f"\n{'='*60}")
                print(f"Processing Professor: {prof['name']}")
                print(f"University: {prof['university']}")
                
                # Start timer for this professor
                start_time = time.time()
                
                try:
                    # Wrap the entire email sending process in a timeout (150 seconds = 2.5 minutes)
                    with timeout_handler(150):
                        
                        # Get IC information
                        ic_name = prof.get('IC', 'Tushar Bajaj')
                        ic_info = self.get_ic_info(ic_name)
                        print(f"IC Assigned: {ic_info['name']}")
                        print(f"{'='*60}")
                        
                        # Research professor with Google Search grounding
                        research_data = self.research_professor_domains(prof['name'], prof['university'])
                        
                        # Check if research was successful
                        if not research_data['success']:
                            print(f"🚫 Skipping {prof['name']} - {research_data.get('validation', {}).get('reason', 'Research failed')}")
                            no_data_count += 1
                            
                            # Log the skipped professor due to insufficient data
                            result = {
                                "prof_name": prof['name'],
                                "prof_email": prof['email'],
                                "university": prof['university'],
                                "ic_name": ic_info['name'],
                                "status": "skipped",
                                "reason": "insufficient_research_data",
                                "validation": research_data.get('validation', {}),
                                "domain1": research_data.get('domain1', 'N/A'),
                                "domain2": research_data.get('domain2', 'N/A'),
                                "domain3": research_data.get('domain3', 'N/A'),
                                "grounded": research_data.get('grounded', False),
                                "search_queries": research_data.get('search_queries', []),
                                "grounding_sources": research_data.get('grounding_sources', []),
                                "full_gemini_response": research_data.get('full_response', ''),
                                "error_type": research_data.get('error_type', 'unknown'),
                                "error_message": research_data.get('error_message', ''),
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                            }
                            results.append(result)
                            
                            with open(log_file, 'w', encoding='utf-8') as f:
                                json.dump({
                                    "campaign_info": {
                                        "total_processed": len(results),
                                        "emails_sent": sent_count,
                                        "emails_failed": failed_count,
                                        "emails_skipped_humanities": skipped_count,
                                        "emails_skipped_no_data": no_data_count,
                                        "emails_skipped_timeout": timeout_count,
                                        "google_search_grounding": "enabled",
                                        "research_validation": "enabled",
                                        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                                        "method": "Gmail API with OAuth2",
                                        "sender_address": self.sender_email
                                    },
                                    "results": results
                                }, f, indent=2, ensure_ascii=False)
                            
                            continue
                        
                        print(f"\n🔬 Research Domains Identified:")
                        print(f"   1. {research_data['domain1']}")
                        print(f"   2. {research_data['domain2']}")
                        print(f"   3. {research_data['domain3']}\n")
                        
                        # Get LLM suggested departments BEFORE any fallback logic
                        llm_suggested_depts = self.get_llm_suggested_depts(research_data)
                        
                        # Check if Humanities & Social Sciences is in the suggested departments
                        if "Humanities & Social Sciences" in llm_suggested_depts:
                            print(f"🔕 Skipping {prof['name']} - Humanities & Social Sciences was identified as relevant department")
                            print(f"   Suggested departments: {llm_suggested_depts}\n")
                            skipped_count += 1
                            
                            # Log the skipped professor
                            result = {
                                "prof_name": prof['name'],
                                "prof_email": prof['email'],
                                "university": prof['university'],
                                "ic_name": ic_info['name'],
                                "status": "skipped",
                                "reason": "humanities_social_sciences_department",
                                "suggested_departments": llm_suggested_depts,
                                "domain1": research_data['domain1'],
                                "domain2": research_data['domain2'],
                                "domain3": research_data['domain3'],
                                "grounded": research_data.get('grounded', False),
                                "search_queries": research_data.get('search_queries', []),
                                "grounding_sources": research_data.get('grounding_sources', []),
                                "full_gemini_response": research_data.get('full_response', ''),
                                "validation": research_data.get('validation', {}),
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                            }
                            results.append(result)
                            
                            with open(log_file, 'w', encoding='utf-8') as f:
                                json.dump({
                                    "campaign_info": {
                                        "total_processed": len(results),
                                        "emails_sent": sent_count,
                                        "emails_failed": failed_count,
                                        "emails_skipped_humanities": skipped_count,
                                        "emails_skipped_no_data": no_data_count,
                                        "emails_skipped_timeout": timeout_count,
                                        "google_search_grounding": "enabled",
                                        "research_validation": "enabled",
                                        "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                                        "method": "Gmail API with OAuth2",
                                        "sender_address": self.sender_email
                                    },
                                    "results": results
                                }, f, indent=2, ensure_ascii=False)
                            
                            continue
                        
                        # Proceed with normal email generation and sending
                        subject, html_body = self.generate_html_email(prof.to_dict(), research_data, ic_info)
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
                            "ic_name": ic_info['name'],
                            "ic_phone": ic_info['phone'],
                            "ic_linkedin": ic_info['linkedin'],
                            "subject": subject,
                            "email_sent": email_success,
                            "status": "sent" if email_success else "failed",
                            "domain1": research_data['domain1'],
                            "domain2": research_data['domain2'],
                            "domain3": research_data['domain3'],
                            "research_success": research_data['success'],
                            "grounded": research_data.get('grounded', False),
                            "search_queries": research_data.get('search_queries', []),
                            "grounding_sources": research_data.get('grounding_sources', []),
                            "full_gemini_response": research_data.get('full_response', ''),
                            "validation": research_data.get('validation', {}),
                            "processing_time": time.time() - start_time,
                            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                        }
                        results.append(result)

                        with open(log_file, 'w', encoding='utf-8') as f:
                            json.dump({
                                "campaign_info": {
                                    "total_processed": len(results),
                                    "emails_sent": sent_count,
                                    "emails_failed": failed_count,
                                    "emails_skipped_humanities": skipped_count,
                                    "emails_skipped_no_data": no_data_count,
                                    "emails_skipped_timeout": timeout_count,
                                    "google_search_grounding": "enabled",
                                    "research_validation": "enabled",
                                    "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "method": "Gmail API with OAuth2",
                                    "sender_address": self.sender_email
                                },
                                "results": results
                            }, f, indent=2, ensure_ascii=False)

                        df.to_csv(csv_file, index=False)
                        
                        elapsed_time = time.time() - start_time
                        print(f"✅ Completed in {elapsed_time:.2f} seconds")
                        print(f"\n⏱️ Waiting 2 seconds before next email...\n")
                        time.sleep(2)
                
                except TimeoutError as te:
                    elapsed_time = time.time() - start_time
                    print(f"⏰ TIMEOUT: Skipping {prof['name']} - Processing exceeded 2.5 minutes ({elapsed_time:.2f} seconds)")
                    timeout_count += 1
                    
                    # Log the timeout
                    result = {
                        "prof_name": prof['name'],
                        "prof_email": prof['email'],
                        "university": prof['university'],
                        "ic_name": ic_name,
                        "status": "skipped",
                        "reason": "timeout_exceeded",
                        "processing_time": elapsed_time,
                        "timeout_limit": 150,
                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                    }
                    results.append(result)
                    
                    with open(log_file, 'w', encoding='utf-8') as f:
                        json.dump({
                            "campaign_info": {
                                "total_processed": len(results),
                                "emails_sent": sent_count,
                                "emails_failed": failed_count,
                                "emails_skipped_humanities": skipped_count,
                                "emails_skipped_no_data": no_data_count,
                                "emails_skipped_timeout": timeout_count,
                                "google_search_grounding": "enabled",
                                "research_validation": "enabled",
                                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                                "method": "Gmail API with OAuth2",
                                "sender_address": self.sender_email
                            },
                            "results": results
                        }, f, indent=2, ensure_ascii=False)
                    
                    continue
            
            print("\n" + "="*60)
            print(f"📊 GMAIL API EMAIL CAMPAIGN SUMMARY:")
            print(f"✅ Successfully sent: {sent_count} emails")
            print(f"❌ Failed to send: {failed_count} emails")
            print(f"🔕 Skipped (Humanities & Social Sciences): {skipped_count} emails")
            print(f"🚫 Skipped (Insufficient Research Data): {no_data_count} emails")
            print(f"⏰ Skipped (Timeout > 2.5 min): {timeout_count} emails")
            print(f"🔍 Google Search Grounding: ENABLED")
            print(f"✅ Research Validation: ENABLED")
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
        print(f"🔍 Google Search Grounding: ENABLED for accurate research domain extraction")
        print(f"✅ Research Validation: ENABLED to skip professors with insufficient data")
        print(f"⏰ Timeout Protection: ENABLED (2.5 minutes per professor)")
    except Exception as e:
        print(f"❌ System initialization failed: {e}")
        return
    
    results = placement_system.process_and_send_emails("professors.csv")
    if results:
        print(f"\n🎯 Gmail API campaign completed! Processed {len(results)} professors")
        print("\n🔬 Sample research domains extracted:")
        for i, result in enumerate(results[:3]):
            if result.get('research_success'):
                print(f"\n{i+1}. {result['prof_name']}:")
                print(f"   • {result['domain1']}")
                print(f"   • {result['domain2']}")
                print(f"   • {result['domain3']}")
                if result.get('grounded'):
                    print(f"   🔍 Grounded with Google Search")
    print("\n🏁 Program completed!")


if __name__ == "__main__":
    main()
