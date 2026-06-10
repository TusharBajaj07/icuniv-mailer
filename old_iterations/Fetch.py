import os
import time
import pandas as pd
from dotenv import load_dotenv
from google import genai  # ← CORRECT import
import json
from typing import Dict, List


class PlacementCellOutreach:
    def __init__(self, api_key: str = None):
        """Initialize the placement cell outreach system"""
        load_dotenv()
        
        self.api_key = api_key or os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("Please set GEMINI_API_KEY in .env file")
        
        # Modern google-genai SDK - no configure() needed
        self.client = genai.Client(api_key=self.api_key)
        
        # IIT Bombay Placement Cell Information
        self.placement_info = {
            "coordinator_name": "Aviral Vishesh Goel",
            "position": "Internship Coordinator",
            "organization": "Placement Cell, IIT Bombay",
            "program_year": "2024-25",
            "duration": "8-9 weeks from May 2025 to mid-July 2025",
            "acceptance_rate": "less than 0.4%",
            "world_ranking": "56th Worldwide in Electrical & Electronics Subject",
            "partner_universities": [
                "Massachusetts Institute of Technology", "ETH Zurich", 
                "Carnegie Mellon University", "UCD", "NTU Singapore", 
                "University of California Merced", "University of Maryland", "Stanford University"
            ]
        }
        
        self.research_areas = [
            "Microprocessors and Computer Architecture",
            "Analog Circuits and VLSI Designing", 
            "Nano scale devices and Microelectronics",
            "Image and Speech Processing",
            "Digital Signal Processing",
            "Robotics",
            "Power Electronics and Power Systems",
            "Quantum electronics and Information"
        ]
        
        self.dual_degree_specializations = [
            "Communications and Signal Processing",
            "Microelectronics"
        ]
        
        self.current_courses = [
            "Communication Systems", "Microprocessors", "Probability and Random Processes",
            "Power Electronics and Power Systems", "Digital Circuits and Digital Systems", 
            "Analog Circuits", "Semiconductor Device physics", "Image Processing"
        ]
        
        self.additional_courses = [
            "Machine Learning and Data analysis", "Queuing System analysis and IoT",
            "Neural networks", "Computing and networking", "Algorithms", 
            "Optimization", "Applied Statistics"
        ]

    def research_professor_background(self, professor_name: str, university: str, department: str = "Electrical Engineering") -> Dict:
        """Research professor's background and align with IIT Bombay's program"""
        
        research_prompt = f"""
        As an Internship Coordinator from IIT Bombay Placement Cell, research Professor {professor_name} from {university} ({department}) and provide:

        1. Their primary research areas and current projects
        2. How their research aligns with these IIT Bombay electrical engineering focus areas:
           - {', '.join(self.research_areas)}
        
        3. Potential collaboration opportunities for summer internships (May-July 2025)
        4. Their experience with international students or research collaborations
        5. Any notable achievements or recent publications
        6. Specific research areas that would benefit from IIT Bombay students' skills in:
           {', '.join(self.current_courses[:4])}

        Focus on finding connection points between their research and IIT Bombay's electrical engineering program.
        If information is limited, indicate that clearly.
        
        Provide a structured response with clear sections for easy email personalization.
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=research_prompt
            )
            
            return {
                "professor": professor_name,
                "university": university,
                "department": department,
                "research_analysis": response.text,
                "success": True
            }
            
        except Exception as e:
            print(f"Research failed for {professor_name}: {e}")
            return {
                "professor": professor_name,
                "university": university,
                "department": department,
                "research_analysis": "Research information unavailable",
                "success": False
            }

    def generate_placement_email(self, professor_info: Dict, research_data: Dict) -> str:
        """Generate personalized placement cell outreach email"""
        
        email_prompt = f"""
        Draft a professional email from IIT Bombay Placement Cell to invite university participation in summer internship program.

        PROFESSOR DETAILS:
        - Name: Professor {professor_info['name']}
        - University: {professor_info['university']}
        - Email: {professor_info['email']}
        - Department: {professor_info.get('department', 'Electrical Engineering')}

        RESEARCH BACKGROUND:
        {research_data['research_analysis']}

        EMAIL TEMPLATE FOUNDATION:
        Use this core message structure but personalize based on professor's research:

        Subject: Summer Internship Collaboration Opportunity - IIT Bombay Electrical Engineering Students

        Dear Professor {professor_info['name']},

        Greetings from Placement Cell, IIT Bombay!

        I, {self.placement_info['coordinator_name']}, am an {self.placement_info['position']} at {self.placement_info['organization']}. On behalf of the Practical Training Cell of IIT Bombay, I cordially invite {professor_info['university']} to participate in our summer internship recruitment process for {self.placement_info['program_year']}.

        PERSONALIZATION REQUIREMENTS:
        1. Reference their specific research areas that align with our program
        2. Mention how our students' skills in {', '.join(self.research_areas[:3])} could contribute
        3. Highlight relevant coursework connections
        4. Include our achievements: {self.placement_info['acceptance_rate']} acceptance rate, {self.placement_info['world_ranking']}
        5. Mention successful partnerships with universities like MIT, Stanford, ETH Zurich
        6. Specify the program duration: {self.placement_info['duration']}
        7. Reference both B.Tech (4-year) and Dual Degree (5-year) students
        8. Ask about opportunities in their specific research area
        9. Offer to share student portfolios
        10. Request information about the streamlined recruitment process

        TONE: Professional, institutional, collaborative, showing mutual benefit
        LENGTH: 250-300 words
        CLOSING: Formal with contact information and next steps

        Generate the complete email with subject line.
        """
        
        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=email_prompt
            )
            
            return response.text
            
        except Exception as e:
            print(f"Email generation failed for {professor_info['name']}: {e}")
            return self.create_fallback_placement_email(professor_info)

    def create_fallback_placement_email(self, professor_info: Dict) -> str:
        """Fallback email template when API fails"""
        return f"""
Subject: Summer Internship Collaboration Opportunity - IIT Bombay Electrical Engineering Students

Dear Professor {professor_info['name']},

Greetings from Placement Cell, IIT Bombay!

I, {self.placement_info['coordinator_name']}, am an {self.placement_info['position']} at {self.placement_info['organization']}. On behalf of the Practical Training Cell of IIT Bombay, I cordially invite {professor_info['university']} to participate in our summer internship recruitment process for {self.placement_info['program_year']}.

IIT Bombay attracts the finest analytical minds from across India with an acceptance rate of {self.placement_info['acceptance_rate']}, and is ranked {self.placement_info['world_ranking']}. Distinguished universities like MIT, Stanford, ETH Zurich, and Carnegie Mellon have successfully collaborated with us, with students publishing in international journals and receiving pre-PhD offers.

Our electrical engineering students specialize in:
• {self.research_areas[0]}
• {self.research_areas[1]} 
• {self.research_areas[6]}
• {self.research_areas[7]}

Students are pursuing advanced coursework in {', '.join(self.current_courses[:4])} and additional courses in {', '.join(self.additional_courses[:3])}.

We have students in 4-year B.Tech and 5-year Dual Degree programs available for {self.placement_info['duration']}. These research-oriented students would greatly benefit from opportunities under your guidance, while providing valuable contributions to your research projects.

Could you inform us about research opportunities for our electrical engineering students? I would be happy to guide you through our streamlined recruitment process and share detailed student portfolios.

We would also appreciate knowing about opportunities for Computer Science and Physics students.

Looking forward to a fruitful collaboration.

Best regards,
{self.placement_info['coordinator_name']}
{self.placement_info['position']}
{self.placement_info['organization']}
IIT Bombay
"""

    def process_electrical_professors(self, csv_file: str, output_file: str = "placement_outreach_results.json") -> List[Dict]:
        """Process electrical engineering professors database"""
        try:
            df = pd.read_csv(csv_file)
            required_columns = ['name', 'email', 'university']
            
            if not all(col in df.columns for col in required_columns):
                print(f"Warning: CSV should contain {required_columns}")
            
            results = []
            
            print(f"Processing {len(df)} electrical engineering professors...")
            
            for index, prof in df.iterrows():
                print(f"\nProcessing {index + 1}/{len(df)}: Prof. {prof['name']} from {prof['university']}")
                
                # Research professor background
                research_data = self.research_professor_background(
                    prof['name'], 
                    prof['university'], 
                    prof.get('department', 'Electrical Engineering')
                )
                
                # Generate personalized email
                email_content = self.generate_placement_email(prof.to_dict(), research_data)
                
                # Compile results
                result = {
                    "professor_name": prof['name'],
                    "professor_email": prof['email'],
                    "university": prof['university'],
                    "department": prof.get('department', 'Electrical Engineering'),
                    "research_analysis": research_data['research_analysis'],
                    "research_success": research_data['success'],
                    "generated_email": email_content,
                    "coordinator": self.placement_info['coordinator_name'],
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                
                results.append(result)
                
                # Save intermediate results
                with open(output_file, 'w') as f:
                    json.dump(results, f, indent=2)
                
                # Rate limiting
                time.sleep(2)
            
            print(f"\nCompleted! {len(results)} emails generated and saved to {output_file}")
            return results
            
        except Exception as e:
            print(f"Error processing professors: {e}")
            return []

    def export_to_csv(self, results: List[Dict], csv_file: str = "placement_emails.csv"):
        """Export results to CSV for easy review"""
        df = pd.DataFrame(results)
        df.to_csv(csv_file, index=False)
        print(f"Results exported to {csv_file}")

# Usage Example
def main():
    # Initialize placement cell outreach system
    placement_system = PlacementCellOutreach()
    
    # Process electrical engineering professors
    results = placement_system.process_electrical_professors("professors.csv")
    
    # Export results
    if results:
        placement_system.export_to_csv(results)
        
        # Display sample email
        print("\n" + "="*60)
        print("SAMPLE GENERATED PLACEMENT EMAIL:")
        print("="*60)
        print(f"TO: {results[0]['professor_email']}")
        print(results[0]['generated_email'])
        print("="*60)

if __name__ == "__main__":
    main()
