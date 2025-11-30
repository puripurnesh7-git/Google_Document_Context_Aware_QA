import streamlit as st
import re
import agent  # Import the new agent module
import  agent_formatted

# --- Core Logic ---

def extract_google_doc_id(url: str) -> str | None:
    """Extracts the document ID from a Google Docs URL using regex."""
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if match:
        return match.group(1)
    return None

# --- Streamlit UI ---

def set_page_background():
    """Injects CSS to set a background text watermark."""
    page_bg_css = """
    <style>
    .stApp::before {
        content: "Your inHouse Data strategy LLM";
        position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%);
        font-size: 3rem; color: rgba(0, 0, 0, 0.05); font-weight: bold;
        z-index: -1; text-align: center; pointer-events: none; white-space: pre-wrap; width: 100%;
    }
    </style>
    """
    st.markdown(page_bg_css, unsafe_allow_html=True)

st.set_page_config(page_title="AI Strategist", layout="wide")
set_page_background()

st.title("🤖 LeapFrog Agent")
st.markdown("<u>Harnessing 'Unlocking Untapped Potential'</u>", unsafe_allow_html=True)
st.markdown("Provide the details below to start the agent.")

# --- Input Columns ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Data & Business Context")
    source_type = st.radio(
        "**Select Data Source**",
        ("Google Doc", "Confluence", "Cloud Data Catalogue"),
        horizontal=True, key="source_type"
    )
    doc_link = ""
    if source_type == "Google Doc":
        doc_link = st.text_input("🔗 **Google Document Link**", placeholder="https://docs.google.com/document/d/...")
    else:
        st.text_input("🔗 **Link**", placeholder="Coming soon...", disabled=True)
    
    company_business = st.text_input("🏢 **Company Business**", placeholder="e.g., Pharma")
    location = st.text_input("📍 **Location**", placeholder="e.g., New York")

with col2:
    st.subheader("Team Capacity")
    # ADDED: Man-hour inputs
    ds_hours = st.number_input("🧑‍🔬 **Data Scientist Man-Hours**", min_value=0, value=160, step=10)
    de_hours = st.number_input("🧑‍💻**Data Engineer Man-Hours**", min_value=0, value=160, step=10)

# --- Agent Trigger ---
st.markdown("---")
if st.button("▶️ Run Agent", type="primary", use_container_width=True):
    # Validate inputs
    if source_type != "Google Doc":
        st.warning("This data source is not yet supported. Please select 'Google Doc'.")
    elif not all([doc_link, company_business, location]):
        st.error("Please fill in all the fields in 'Data & Business Context'.")
    else:
        with st.spinner("Extracting Document ID..."):
            doc_id = extract_google_doc_id(doc_link)
        
        if doc_id:
            st.success(f"Successfully extracted Document ID: **{doc_id}**")
            
            st.markdown("---")
            st.subheader("Agent Response Stream")
            
            # Prepare inputs for the agent
            agent_inputs = {
                "document_id": doc_id,
                "company_business": company_business,
                "location": location,
                "data_scientist_man_hours": ds_hours,
                "data_engineer_man_hours": de_hours,
            }
            
            # Call the real agent from agent.py and stream its response
            st.write_stream(agent.run_agent(agent_inputs))
            #st.write_stream(agent_formatted.formatted_run_agent(agent_inputs))
        else:
            st.error("Could not extract a valid Google Document ID from the link. Please check the URL.")