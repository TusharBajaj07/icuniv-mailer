import os
import time
import pandas as pd
from dotenv import load_dotenv
from google import genai
import json
from typing import Dict, List
import PyPDF2
import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formataddr

class PlacementCellOutreach:
    def __init__(self, api_key: str = None):
        """Initialize the placement cell outreach system"""
        load_dotenv()
        
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Please set GEMINI_API_KEY in .env file")
        
        self.client = genai.Client(api_key=self.api_key)
        
        # Load mechanical engineering research areas from PDF
        self.mech_research_context = self.load_mech_research_data("mech.pdf")
        
        # Email Configuration
        self.smtp_server = "smtp-auth.iitb.ac.in"
        self.smtp_port = 587
        self.sender_email = "training@iitb.ac.in"
        self.sender_name = "Practical Training Cell"
        self.sender_password = os.getenv('IITB_EMAIL_PASSWORD')
        
        if not self.sender_password:
            raise ValueError("Please set IITB_EMAIL_PASSWORD in .env file")

    def load_mech_research_data(self, pdf_file: str) -> str:
        """Extract mechanical engineering research context from PDF"""
        try:
            with open(pdf_file, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text()
            
            return text[:6000]  # Keep substantial context for matching
            
        except Exception as e:
            print(f"Error loading mech research data: {e}")
            # Fallback context
            return """
            IIT Bombay Mechanical Engineering Department focuses on advanced research in thermal systems, 
            computational fluid dynamics, manufacturing processes, robotics and automation, renewable energy 
            systems, structural mechanics, control systems, and biomechanical engineering applications.
            """

    def research_professor_domains(self, professor_name: str, university: str) -> Dict:
        """Research professor and extract 3 specific research domains"""
        
        research_prompt = f"""
        Research Professor {professor_name} from {university} and identify their research work.
        
        Extract exactly 3 SPECIFIC research domains they work in. Be very specific - mention:
        - Exact technical areas (not generic terms)
        - Specific methodologies or technologies they use
        - Particular applications or systems they focus on
        - Each domain should be less than 15 words
        
        Examples of good specificity:
        - "Machine learning-based control systems for autonomous vehicles"
        - "Heat transfer enhancement in microchannel cooling systems"
        - "Additive manufacturing of bio-compatible titanium alloys"
        
        Format your response as:
        DOMAIN 1: [Specific research area with technical details]
        DOMAIN 2: [Specific research area with technical details]  
        DOMAIN 3: [Specific research area with technical details]
        
        Be concrete and technical, avoid generic phrases like "materials science" or "mechanical engineering."
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=research_prompt
            )
            
            domains_text = response.text
            
            # Extract the 3 domains
            domains = []
            for line in domains_text.split('\n'):
                if line.strip().startswith('DOMAIN'):
                    domain = line.split(':', 1)[1].strip() if ':' in line else line.strip()
                    domains.append(domain)
            
            if len(domains) < 3:
                # Fallback parsing
                lines = [l.strip() for l in domains_text.split('\n') if l.strip() and not l.startswith('DOMAIN')]
                domains = lines[:3] if len(lines) >= 3 else domains + ['Advanced engineering research']
            
            return {
                "professor": professor_name,
                "university": university,
                "domain1": domains[0] if len(domains) > 0 else "Advanced research methods",
                "domain2": domains[1] if len(domains) > 1 else "Computational modeling",
                "domain3": domains[2] if len(domains) > 2 else "Experimental techniques",
                "success": True
            }
            
        except Exception as e:
            print(f"Research failed for {professor_name}: {e}")
            return {
                "professor": professor_name,
                "university": university,
                "domain1": "Advanced engineering research",
                "domain2": "Computational modeling and simulation",
                "domain3": "Experimental and theoretical analysis",
                "success": False
            }

    def find_iitb_connection(self, research_domains: Dict) -> str:
        """Find relevant IIT Bombay research connections"""
        
        connection_prompt = f"""
        Based on these professor's research domains:
        1. {research_domains['domain1']}
        2. {research_domains['domain2']}
        3. {research_domains['domain3']}
        
        And this IIT Bombay Mechanical Engineering context:
        {self.mech_research_context[:3000]}
        
        Provide ONE brief sentence (35-45 words) mentioning a specific IIT Bombay research project, 
        publication, or collaboration that connects to their work. Be specific - mention actual 
        technical terms, methods, or applications.
        
        Format: "Students of IIT Bombay have had prior exposure to advanced research, having collaborated with professors from the [Department Name] on publications and projects such as [specific research/publication details], which align closely with the domains mentioned above."
        
        Make it sound authentic and technical, not generic.
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=connection_prompt
            )
            
            return response.text.strip()
            
        except Exception as e:
            return "Students of IIT Bombay have had prior exposure to advanced research, having collaborated with professors from the Mechanical Engineering Department on publications and projects in computational modeling and experimental analysis, which align closely with the domains mentioned above."

    def convert_markdown_to_html(self, text: str) -> str:
        """Convert **bold** markdown to <strong>bold</strong> HTML"""
        # Replace **text** with <strong>text</strong>
        text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
        return text

    def generate_html_email(self, professor_info: Dict, research_data: Dict) -> tuple:
        """Generate HTML email and return subject and body separately"""
        
        # Get IIT Bombay connection
        iitb_connection = self.find_iitb_connection(research_data)
        iitb_connection = self.convert_markdown_to_html(iitb_connection)
        
        # Extract last name
        name_parts = professor_info['name'].split()
        last_name = name_parts[-1] if len(name_parts) > 1 else professor_info['name']
        
        # Convert domains to HTML (handle any bold formatting)
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
        
        <p>Greetings from the <strong>Placement Cell IIT Bombay</strong>. My name is <strong>Tushar Bajaj</strong>, and I am writing on behalf of the Practical Training Cell of IIT Bombay.</p>
        
        <p>IIT Bombay is recognized as India's premier technological institute, consistently attracting the finest analytical minds from across the country, with an acceptance rate of less than 0.4%. It is also ranked as the top technological university in India.</p>
        
        <p>With a strong inclination towards engineering and technology-related domains, students at IIT Bombay are intrigued by your recent research work in:</p>
        
        <ul style="margin-left: 20px;">
            <li><strong>{domain1}</strong></li>
            <li><strong>{domain2}</strong></li>
            <li><strong>{domain3}</strong></li>
        </ul>
        
        <p>{iitb_connection}</p>
        
        <p>Over the past few years, reputed universities such as MIT, ETH Zurich, Carnegie Mellon University, UCD, NTU Singapore, University of California Merced, University of Maryland, and Stanford University have hosted IIT Bombay students for summer research internships.</p>
        
        <p>On behalf of the Practical Training Cell, I would like to cordially invite your esteemed university to participate in our <strong>summer internship</strong> recruitment program for the year 2025–26. Our students are available for research internships of 8–9 weeks from May 2025 to mid-July 2025.</p>
        
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
        """Send HTML email with embedded logo using IITB SMTP server"""
        try:
            # Check if logo file exists
            if not os.path.exists(logo_path):
                print(f"⚠️  Warning: Logo file '{logo_path}' not found. Email will be sent without logo.")
                # Remove the logo from HTML if file doesn't exist
                html_content = html_content.replace('src="cid:iitb_logo"', 'style="display:none;"')
            
            # Set up the MIME
            message = MIMEMultipart('related')
            message['From'] = formataddr((self.sender_name, self.sender_email))
            message['To'] = to_email
            message['Subject'] = subject
            message["Disposition-Notification-To"] = self.sender_email
            message["Return-Receipt-To"] = self.sender_email
            message["Delivery-Status-Notification-To"] = self.sender_email

            # Create alternative container for HTML
            msg_alternative = MIMEMultipart('alternative')
            message.attach(msg_alternative)

            # Attach the HTML content
            mime_text = MIMEText(html_content, 'html')
            msg_alternative.attach(mime_text)

            # Attach the logo if it exists
            if os.path.exists(logo_path):
                with open(logo_path, 'rb') as f:
                    img_data = f.read()
                
                # Create MIMEImage object
                image = MIMEImage(img_data)
                image.add_header('Content-ID', '<iitb_logo>')
                image.add_header('Content-Disposition', 'inline', filename='logo.png')
                
                # Attach image to message
                message.attach(image)
                print(f"📎 Logo attached: {logo_path}")

            # Create SMTP session
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()  # Enable security
            server.login(self.sender_email, self.sender_password)

            # Send the email
            server.sendmail(self.sender_email, to_email, message.as_string())
            server.quit()

            print(f"✅ Email sent successfully to {to_email}")
            return True

        except Exception as e:
            print(f"❌ Failed to send email to {to_email}. Error: {e}")
            return False

    def process_and_send_emails(self, csv_file: str, log_file: str = "email_sending_log.json") -> List[Dict]:
        """Process professors and send emails directly"""
        try:
            df = pd.read_csv(csv_file)
            
            # Check if logo exists
            if not os.path.exists("logo.png"):
                print("⚠️  WARNING: logo.png not found in current directory!")
                print("📁 Current directory contents:", [f for f in os.listdir('.') if f.endswith(('.png', '.jpg', '.jpeg'))])
                response = input("Continue without logo? (y/n): ").lower().strip()
                if response != 'y':
                    print("❌ Stopping. Please add logo.png to the current directory.")
                    return []
            else:
                print("✅ Logo file found: logo.png")
            
            # Add sent status column if it doesn't exist
            if 'email_sent' not in df.columns:
                df['email_sent'] = False
            
            results = []
            sent_count = 0
            failed_count = 0
            
            print(f"📧 Starting email campaign for {len(df)} professors...")
            print(f"📨 Using IITB email: {self.sender_email}")
            print("="*60)
            
            for index, prof in df.iterrows():
                # Skip if already sent
                if prof.get('email_sent', False):
                    print(f"⏭️  Skipping {prof['name']} - Email already sent")
                    continue
                
                print(f"\n📍 Processing {index + 1}/{len(df)}: Prof. {prof['name']} from {prof['university']}")
                
                # Research professor's specific domains
                research_data = self.research_professor_domains(prof['name'], prof['university'])
                
                # Generate HTML email
                subject, html_body = self.generate_html_email(prof.to_dict(), research_data)
                
                # Send email with logo
                email_success = self.send_email(prof['email'], subject, html_body, "logo.png")
                
                # Update DataFrame
                df.at[index, 'email_sent'] = email_success
                
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
                
                if email_success:
                    sent_count += 1
                else:
                    failed_count += 1
                
                # Save progress
                with open(log_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "campaign_info": {
                            "total_processed": len(results),
                            "emails_sent": sent_count,
                            "emails_failed": failed_count,
                            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S")
                        },
                        "results": results
                    }, f, indent=2, ensure_ascii=False)
                
                # Save updated CSV
                df.to_csv(csv_file, index=False)
                
                # Rate limiting - be respectful
                print(f"⏱️  Waiting 3 seconds before next email...")
                time.sleep(3)
            
            print("\n" + "="*60)
            print(f"📊 EMAIL CAMPAIGN SUMMARY:")
            print(f"✅ Successfully sent: {sent_count} emails")
            print(f"❌ Failed to send: {failed_count} emails")
            print(f"📄 Log saved to: {log_file}")
            print(f"💾 Updated CSV saved to: {csv_file}")
            
            return results
            
        except Exception as e:
            print(f"💥 Error in email campaign: {e}")
            return []

def main():
    print("🚀 IIT Bombay Placement Cell - Professor Outreach System")
    print("=" * 60)
    
    # Initialize system
    try:
        placement_system = PlacementCellOutreach()
        print("✅ System initialized successfully")
        print(f"📧 Email configured: {placement_system.sender_email}")
    except Exception as e:
        print(f"❌ System initialization failed: {e}")
        return
    
    # Process professors and send emails
    results = placement_system.process_and_send_emails("professors.csv")
    
    if results:
        print(f"\n🎯 Campaign completed! Processed {len(results)} professors")
        
        # Show sample domains extracted
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
