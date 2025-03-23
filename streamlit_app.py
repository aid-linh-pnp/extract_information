import streamlit as st
import json
import os
import requests
import pdfplumber
import io
from datetime import datetime

api_key = st.secrets["azure_openai"]["api_key"]
endpoint = st.secrets["azure_openai"]["endpoint"]

current_year = datetime.now().year

# Function to read the schema from a file
def read_schema(schema_path):
    try:
        with open(schema_path, 'r') as file:
            schema = json.load(file)
        return schema
    except Exception as e:
        st.error(f"Error reading schema file: {e}")
        return None

# Function to extract text from a PDF using pdfplumber
def extract_text_from_pdf_plumber(pdf_data):
    text = ""
    try:
        with io.BytesIO(pdf_data) as pdf_file:
            with pdfplumber.open(pdf_file) as pdf:
                for page in pdf.pages:
                    text += page.extract_text()
        return text
    except Exception as e:
        st.error(f"Error extracting text from PDF: {e}")
        return None

# Main function for processing the file and extracting information
def process_file(uploaded_file, user_prompt_text):
    schema_path = './schema.json'
    schema_json = read_schema(schema_path)

    if schema_json is None:
        st.error('Error: Schema could not be loaded.')
        return None

    extracted_text = ""
    
    # Ensure the file exists locally
    if not uploaded_file:
        st.error('Error: File path is missing or file does not exist.')
        return None
    
    # Read PDF data from uploaded file
    file_data = uploaded_file.getvalue()

    # Check if the file is a PDF
    if uploaded_file.name.endswith('.pdf'):
        extracted_text = extract_text_from_pdf_plumber(file_data)
        
        # If pdfplumber doesn't extract any text, fall back to OCR method
        if not extracted_text.strip():
            st.warning("No text extracted from PDF using pdfplumber.")
            return None
    else:
        st.error('Error: Unsupported file type. Only .pdf files are supported.')
        return None

    # Ensure that some text was extracted from the file
    if not extracted_text.strip():
        st.error('Error: No text extracted from the file.')
        return None
    
    # System message remains fixed
    system_message = {
        "role": "system",
        "content": """
            You are an AI assistant that helps extract information from resumes (CVs).
            Keep the language of the CV unchanged.
            Remove special characters to properly format it as an object before saving it to a JSON file.
            Remove ```json, remove $schema. 
            seniority just 4 levels: Fresher, Junior, Middle, Senior.
            Required: seniority, careerPath, percentComplete, prediction.
        """
    }

    # Process the user prompt by replacing placeholders with actual values
    final_user_prompt = user_prompt_text
    final_user_prompt = final_user_prompt.replace("{json.dumps(schema_json)}", json.dumps(schema_json))
    final_user_prompt = final_user_prompt.replace("{current_year}", str(current_year))
    final_user_prompt = final_user_prompt.replace("{extracted_text}", extracted_text)
    
    # Display what's being sent (for debugging)
    with st.expander("View processed prompt being sent to API"):
        st.text_area("Final prompt sent to API:", value=final_user_prompt, height=200, disabled=True)
    
    # User message with the processed prompt from the text area
    user_message = {
        "role": "user",
        "content": final_user_prompt
    }

    # Create request data
    data = {
        "messages": [system_message, user_message],
        "max_tokens": 16000,
        "temperature": 1,
        "top_p": 0.25
    }

    # Make the first API request to extract the CV information
    st.info("Sending request to OpenAI API for CV extraction...")
    try:
        response = requests.post(
            endpoint, 
            headers={'Content-Type': 'application/json', 'api-key': api_key}, 
            data=json.dumps(data)
        )
        
        if response.status_code == 200:
            # Extract only the content part from OpenAI API's response
            generated_text = response.json()['choices'][0]['message']['content']
            
            # Display only the extracted content
            st.subheader("Extracted Resume Information")
            try:
                extracted_info = json.loads(generated_text)  # Try to parse as JSON
                # Show the parsed JSON if possible
                st.json(extracted_info)
                
                # Store the extracted information in session state for later use
                st.session_state.extracted_info = extracted_info
                
                # Show the question generation input area
                st.session_state.show_question_input = True

            except json.JSONDecodeError:
                st.error("The returned content is not in valid JSON format.")
                st.write("Raw response:")
                st.code(generated_text)
        
        else:
            st.error(f"Request failed with status code {response.status_code}")
            st.write(response.text)
    except Exception as e:
        st.error(f"Error during API request: {e}")

# Function to generate technical questions based on the CV information
def generate_technical_questions(extracted_info, user_question_prompt):
    # Process the user prompt by replacing the extracted information
    final_user_prompt = user_question_prompt.replace("{json.dumps(extracted_info, indent=2)}", json.dumps(extracted_info, indent=2))

    # Display what's being sent (for debugging)
    with st.expander("View processed question prompt being sent to API"):
        st.text_area("Final question prompt sent to API:", value=final_user_prompt, height=200, disabled=True)

    # Make the second API request to generate technical questions
    data = {
        "messages": [
            {"role": "system", "content": "You are an expert technical interviewer. Generate relevant and challenging questions for the candidate based on the provided resume information. Remove ```json."},     
            {"role": "user", "content": final_user_prompt}
        ],
        "max_tokens": 10000,
        "temperature": 1,
        "top_p": 0.25
    }

    st.info("Sending request to OpenAI API for technical questions...")
    try:
        response = requests.post(
            endpoint, 
            headers={'Content-Type': 'application/json', 'api-key': api_key}, 
            data=json.dumps(data)
        )
        
        if response.status_code == 200:
            generated_questions = response.json()['choices'][0]['message']['content']
            
            # Display the generated technical questions
            st.subheader("Generated Technical Questions")
            st.text_area("Technical Questions:", value=generated_questions, height=400, disabled=True)
            
            # Try to parse as JSON for better display
            try:
                questions_json = json.loads(generated_questions)
                st.json(questions_json)
            except json.JSONDecodeError:
                # If not valid JSON, the text area above will still show the content
                pass
        
        else:
            st.error(f"Request failed with status code {response.status_code}")
            st.write(response.text)
    except Exception as e:
        st.error(f"Error during technical questions generation: {e}")

# Streamlit interface
def main():
    st.title('Resume Information Extractor')

    # Initialize session state variables
    if 'prompt_text' not in st.session_state:
        st.session_state.prompt_text = """### Updated Enhanced Prompt with OpenAI-Friendly Schema

        Extract all relevant information from the provided CV and structure it using the schema below. Ensure the extracted information is precise and consistent with the requirements.

        #### Schema:
        {
        "contact": {
            "phoneNumbers": ["<Extracted Phone 1>", "<Extracted Phone 2>", "..."],
            "emails": ["<Extracted Email 1>", "<Extracted Email 2>", "..."],
            "address": "<Extracted Address>"
        },
        "nationalities": ["<Extracted Nationality 1>", "<Extracted Nationality 2>", "..."],
        "profiles": [
            {
            "platform": "<Platform Name (e.g., LinkedIn, GitHub)>",
            "url": "<Profile URL>"
            }
        ],
        "professional_summary": "<Extracted Professional Summary>",
        "work_experiences": [
            {
            "jobTitle": "<Extracted Job Title>",
            "employerName": "<Extracted Employer Name>",
            "startDate": "<Formatted Start Date (ISO 8601)>",
            "endDate": "<Formatted End Date (ISO 8601)>",
            "tenure": "<Calculated Tenure in Months>",
            "ageAtStart": "<Calculated Age at Start>",
            "ageAtEnd": "<Calculated Age at End>",
            "responsibilities": ["<Responsibility 1>", "<Responsibility 2>", "..."],
            "skillsUsed": ["<Skill 1>", "<Skill 2>", "..."],
            "impact": "<Brief description of achievements or outcomes>",
            "roleType": "<Full-Time, Part-Time, Freelancer>",
            "seniority": "<Seniority Level> (required from OpenAI)",
            "timeAllocation": "<Percentage if overlapping roles>",
            "team": "<Team Name>",
            "projects": [
                {
                "projectName": "<Project Name>",
                "role": "<Role in Project>",
                "responsibilities": ["<Responsibility 1>", "..."],
                "skillsUsed": ["<Skill 1>", "..."],
                "impact": "<Project outcome>"
                }
            ]
            }
        ],
        "education": [
            {
            "degree": "<Extracted Degree>",
            "institution": "<Extracted Institution>",
            "startYear": "<Start Year>",
            "endYear": "<End Year>",
            "score": "<Extracted Score (GPA/Percentage)>"
            }
        ],
        "skills": {
            "technicalSkills": ["<Technical Skill 1>", "<Technical Skill 2>", "..."],
            "softSkills": ["<Soft Skill 1>", "<Soft Skill 2>", "..."]
        },
        "awards": ["<Award 1>", "<Award 2>", "..."],
        "certifications": ["<Certification 1>", "<Certification 2>", "..."],
        "publications": [
            {
            "title": "<Publication Title>",
            "date": "<Publication Date (ISO 8601)>",
            "journal": "<Journal/Publisher Name>",
            "description": "<Brief Description>"
            }
        ],
        "languages": [
            {
            "language": "<Language Name>",
            "proficiency": "<Proficiency Level (e.g., Native, Fluent, Intermediate)>"
            }
        ],
        "additional_information": ["<Additional Info 1>", "..."],
        "careerInsights": {
            "careerPath": "<Summary of career trajectory> (required from OpenAI)",
            "industryExperience": ["<Industry 1>", "<Industry 2>", "..."]
        },
        "prediction": {
            "time_to_leave_current_company": "<Predicted Time to Leave>",
            "reasons_for_leaving": [
            "<Reason 1>",
            "<Reason 2>",
            "..."
            ]
        },
        "cv_analysis": {
            "percentComplete": "<Calculated Completeness Percentage> (eg. 70) (required from OpenAI)"
        }
        }

        #### Guidelines:
        1. *Contact Details*:
        - Extract all phone numbers and emails mentioned in the CV. Ensure each is listed separately in the phoneNumbers and emails arrays.

        2. *Nationalities*:
        - Extract all nationalities mentioned in the CV and list them in the nationalities array.

        3. *Profiles*:
        - Extract all online profiles (e.g., LinkedIn, GitHub) mentioned in the CV, including the platform name and URL.

        4. *Formatting Dates*:
        - Ensure all dates are in ISO 8601 format (YYYY-MM-DDTHH:MM:SS.000).
        - Replace placeholder or incomplete dates (e.g., 2023-00-00) with 2023-01-01T00:00:00.000.

        5. *Work Experiences*:
        - Include all positions held at the same company, capturing each distinct job title, time period, team information (if applicable), and detailed responsibilities. If a position was held multiple times or in different teams, treat each as a separate array item.
        - Include overlapping jobs with accurate start and end dates.
        - Calculate tenure in months for each role.
        - Calculate the candidate's age at the start and end of each job:
            - If the CV does not include the person's birth year, estimate their age by subtracting 22 years from their first year of work.

        6. *Education*:
        - Include degree, institution, years of study, and score (e.g., GPA, percentage).

        7. *Skills*:
        - Extract and list all technical and soft skills mentioned in the CV.

        8. *Awards, Certifications, and Publications*:
        - Include all awards, certifications, and publications with relevant details.

        9. *Languages*:
        - List all languages spoken, along with proficiency levels (e.g., Native, Fluent, Intermediate).

        10. *Derived Insights*:
            - Add careerInsights such as careerPath (a summary of the candidate's career trajectory) and industryExperience (industries the candidate has worked in).

        11. *CV Completeness*:
            - Evaluate the percentage completeness of the CV based on the presence of key sections (contact, professional summary, work experiences, education, skills).
            - Assign a percentage (e.g., 100% for a complete CV).
        
        12. Seniority:
            - OpenAI will assess the candidate's seniority based on the work experience, responsibilities, and expertise mentioned in the CV.
            - The seniority levels will be classified into 4 categories: Fresher, Junior, Middle, Senior.
        #### Output:
        Return only valid JSON formatted as per the schema above.
        Ensure the JSON is clean and does not include any unnecessary explanations or formatting issues.

        13. *Predictions*:
            - Predict when the candidate is likely to leave their current company (time_to_leave_current_company) based on their tenure patterns, career progression, and external trends.
            - Provide possible reasons for leaving (reasons_for_leaving), such as lack of growth opportunities, better offers, or role stagnation.
            
        #### Analyze Content:
        text
        {extracted_text}"""

    if 'question_prompt_text' not in st.session_state:
        st.session_state.question_prompt_text = """
        Generate 15 technical interview multiple questions based on the following resume information:
        {json.dumps(extracted_info, indent=2)}
        The questions should be relevant to the skills and experience listed in the resume.
        Based on the candidate's seniority, adjust the difficulty level of the questions.
        Output format: JSON:
        [
            {
                "question": "Question Text",
                "options": [
                    "Option 1",
                    "Option 2",
                    "Option 3",
                    "Option 4"
                ],
                "correct_answer": "Correct Option",
                "seniority": "Seniority level",
                "skills": [
                    "Skill 1",
                    "Skill 2",
                    "..."
                ],
                "job_title": "Job Title",
                "domains": [
                    "Healthcare",
                    "Banking",
                    "..."
                ]
            }
        ]
        """
    
    if 'show_question_input' not in st.session_state:
        st.session_state.show_question_input = False
    
    if 'extracted_info' not in st.session_state:
        st.session_state.extracted_info = None

    # File uploader
    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
    
    # Function to update session state for extract prompt
    def update_prompt():
        st.session_state.prompt_text = st.session_state.prompt_input
    
    # Function to update session state for question prompt
    def update_question_prompt():
        st.session_state.question_prompt_text = st.session_state.question_prompt_input
    
    # Text area for editing the prompt with key to track changes
    st.text_area(
        "Edit the prompt to send to OpenAI for CV extraction:", 
        value=st.session_state.prompt_text, 
        height=400,
        key="prompt_input",
        on_change=update_prompt
    )
    
    if uploaded_file is not None:
        if st.button("Extract Information"):
            with st.spinner('Processing with your customized prompt...'):
                # Pass the current value from session state to ensure latest edits are used
                process_file(uploaded_file, st.session_state.prompt_text)
    
    # Display question generation input only after extraction is complete
    if st.session_state.show_question_input and st.session_state.extracted_info is not None:
        st.markdown("---")
        st.subheader("Generate Technical Questions")
        
        # Text area for editing the question prompt
        st.text_area(
            "Edit the prompt to send to OpenAI for question generation:", 
            value=st.session_state.question_prompt_text, 
            height=300,
            key="question_prompt_input",
            on_change=update_question_prompt
        )
        
        if st.button("Generate Questions"):
            with st.spinner('Generating technical questions...'):
                # Pass the current value from session state
                generate_technical_questions(
                    st.session_state.extracted_info, 
                    st.session_state.question_prompt_text
                )

if __name__ == "__main__":
    main()