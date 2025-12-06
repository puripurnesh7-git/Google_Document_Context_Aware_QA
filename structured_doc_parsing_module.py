import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.auth.transport.requests import Request
# CHANGE: Import RefreshError to handle token revocation exceptions.
from google.auth.exceptions import RefreshError

# The scope defines the level of access you're requesting.
SCOPES = ['https://www.googleapis.com/auth/documents.readonly']

# CHANGE: The function is refactored to gracefully handle invalid refresh tokens.
def get_google_docs_service():
    """Authenticates and returns the Google Docs API service object."""
    creds = None
    # Use a more specific token file name to avoid conflicts.
    token_file = 'token_docs_readonly.json'
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError:
                # If refresh fails, the token is invalid. Delete it and re-authenticate.
                print(f"Refresh token is invalid. Deleting '{token_file}' and re-authenticating.")
                os.remove(token_file)
                creds = None  # Force re-authentication by falling through.
        
        # If we still don't have valid credentials, run the full auth flow.
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Save the credentials for the next run
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
            
    return build('docs', 'v1', credentials=creds)

def read_google_doc_structured_content(document_id: str) -> dict:
    """Reads and returns the structured JSON content of a Google Doc."""
    try:
        service = get_google_docs_service()
        doc = service.documents().get(documentId=document_id).execute()
        return doc
    except HttpError as error:
        print(f"An error occurred: {error}")
        return {}

def _get_text_from_paragraph_elements(elements):
    """Helper to extract text from a list of paragraph elements."""
    text = ""
    for value in elements:
        if "textRun" in value:
            text += value.get("textRun", {}).get("content", "")
    return text

def _get_text_from_cell(cell):
    """
    Helper to correctly extract text from a table cell, which has a
    more complex nested structure than a simple paragraph.
    """
    text = ""
    # A cell's content is a list of structural elements (like paragraphs).
    for element in cell.get('content', []):
        if 'paragraph' in element:
            # Use the paragraph helper to get text from the paragraph's elements.
            text += _get_text_from_paragraph_elements(element['paragraph'].get('elements', []))
    return text.strip()

def parse_docs_json(doc_json: dict) -> dict:
    """
    Parses structured JSON from a Google Doc to create a data catalogue.
    This function uses a state machine to correctly identify datasets and their associated tables.
    """
    datasets = []
    current_dataset = None
    current_table_name = ""
    
    is_parsing_sources = False
    is_parsing_table_info = False
    
    for element in doc_json.get('body', {}).get('content', []):
        if 'paragraph' in element:
            paragraph = element['paragraph']
            style_type = paragraph.get('paragraphStyle', {}).get('namedStyleType')
            text = _get_text_from_paragraph_elements(paragraph.get('elements', [])).strip()

            # State transitions are now only triggered by headings.
            if style_type == 'HEADING_2' and text:
                if current_dataset:
                    datasets.append(current_dataset)
                current_dataset = {
                    "name": text,
                    "data_source": "",
                    "schema": {"columns": []}
                }
                # Reset states for the new dataset
                is_parsing_sources = False
                is_parsing_table_info = False
                current_table_name = ""
            
            elif style_type == 'HEADING_3':
                if "Sourced from:" in text:
                    is_parsing_sources = True
                    is_parsing_table_info = False  # Explicitly turn off table parsing
                elif "Table Information:" in text:
                    is_parsing_table_info = True
                    is_parsing_sources = False  # Explicitly turn off source parsing
            
            elif is_parsing_sources and 'listProperties' in paragraph and text:
                if current_dataset:
                    source_text = f", {text}" if current_dataset["data_source"] else text
                    current_dataset["data_source"] += source_text

        # This block now correctly processes all tables as long as the state is active.
        elif 'table' in element and is_parsing_table_info and current_dataset:
            table = element['table']
            rows = table.get('tableRows', [])
            
            if len(rows) > 1:
                header_row = rows[0].get('tableCells', [])
                # Use the correct helper to parse headers.
                headers = [_get_text_from_cell(cell) for cell in header_row]
                
                if 'Table Name' in headers and 'Column' in headers and 'Description' in headers:
                    for row in rows[1:]:
                        cells = row.get('tableCells', [])
                        
                        # Add a guard to prevent IndexError on malformed rows.
                        if len(cells) < 3:
                            continue

                        # Use the correct helper for data cells.
                        table_name_cell = _get_text_from_cell(cells[0])
                        column_name_cell = _get_text_from_cell(cells[1])
                        description_cell = _get_text_from_cell(cells[2])

                        if table_name_cell:
                            current_table_name = table_name_cell
                        
                        # Ensure row has content before adding.
                        if not column_name_cell and not description_cell:
                            continue

                        is_pii = "(PII" in description_cell

                        column = {
                            "table_name": current_table_name,
                            "column_name": column_name_cell,
                            "description": description_cell,
                            "is_pii": is_pii
                        }
                        current_dataset["schema"]["columns"].append(column)

    if current_dataset and current_dataset not in datasets:
        datasets.append(current_dataset)
    
    for dataset in datasets:
        dataset["data_source"] = dataset["data_source"].strip(', ')
    
    return {"datasets": datasets}

def ingest_data_catalogue(document_id: str) -> dict:
    """
    Ingests and parses a document from Google Docs using its structure.
    """
    print(f"-> Ingesting and parsing structured data from Google Docs with Document ID: {document_id}")
    doc_json = read_google_doc_structured_content(document_id)
    if doc_json:
        structured_catalogue = parse_docs_json(doc_json)
        return structured_catalogue
    else:
        return {"error": "Could not read structured document content."}

# Example usage:
#
#catalogue_data = ingest_data_catalogue(document_id)


#print(type(catalogue_data))
#print(json.dumps(catalogue_data, indent=2))