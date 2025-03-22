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
    with open(schema_path, 'r') as file:
        schema = json.load(file)
    return schema

# Function to extract text from a PDF using pdfplumber
def extract_text_from_pdf_plumber(pdf_data):
    text = ""
    with io.BytesIO(pdf_data) as pdf_file:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                text += page.extract_text()
    return text

# Main function for processing the file and extracting information
def process_file(uploaded_file, user_prompt_text):
    schema_path = './schema.json'
    schema_json = read_schema(schema_path)

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

    # Make the API request
    st.info("Sending request to OpenAI API...")
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
        except json.JSONDecodeError:
            st.error("The returned content is not in valid JSON format.")
            st.write("Raw response:")
            st.code(generated_text)
        
    else:
        st.error(f"Request failed with status code {response.status_code}")
        st.write(response.text)

# Streamlit interface
def main():
    st.title('Resume Information Extractor')
    
    # Session state to persist the prompt between reruns
    if 'prompt_text' not in st.session_state:
        st.session_state.prompt_text = """Use the following schema to structure the extracted information: {json.dumps(schema_json)}
        Only return valid JSON with the extracted information, without any additional explanations.
        Export object format to store json file.
        List all skills.
        If date: 2023-00-00T00:00:00.000 change to 2023-01-01T00:00:00.000
        Please list all positions held at the same company along with their corresponding time periods, company name, and detailed duties and responsibilities for each role. If the same position is held at different times or in different teams within the same company, include each occurrence separately with its unique time period and team information. Ensure that all distinct roles, teams, and time periods are captured in a *separate array item* for each specific instance.
        - If the CV does not include the person's age, calculate the age as the person's first year of work minus 22 years old.
        - The age will be calculated as the year when the person left the job at the company, based on the tenure at each company. 
        - If the CV mentions multiple jobs with overlapping dates, *both jobs should be included*, with the same age calculated based on the year when the candidate left the job.
        - Ensure that all freelancer jobs are included in the output.
        - Tenure is month format.
        - This year is {current_year}. Calculate age as the person's age when they left each company. 
        If the CV does not include age, the age will be based on the candidate's first year of work minus 22 years old. 
        If there are multiple jobs with overlapping dates, both jobs should be included with the same age calculated as the year when they left the job. Ensure that all freelancer jobs are included in the output.
        Text extracted from PDF (with coordinates). Keep the language of the CV unchanged:
        Analyze file content: {extracted_text}"""
    
    # File uploader
    uploaded_file = st.file_uploader("Upload a PDF file", type="pdf")
    
    # Function to update session state
    def update_prompt():
        st.session_state.prompt_text = st.session_state.prompt_input
    
    # Text area for editing the prompt with key to track changes
    st.text_area(
        "Edit the prompt to send to OpenAI:", 
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

if __name__ == "__main__":
    main()