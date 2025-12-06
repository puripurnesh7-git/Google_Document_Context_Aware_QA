from typing import TypedDict, Optional, List
from langgraph.graph import StateGraph, START, END
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.tools.tavily_search import TavilySearchResults
import os
from dotenv import load_dotenv
from structured_doc_parsing_module import ingest_data_catalogue as moduel_for_ingest_data_catalogue
# CHANGE: Ensured Pydantic v1 is used for compatibility with LangChain/LangGraph.
from langchain_core.pydantic_v1 import BaseModel, Field
import json
import traceback

# Load environment variables
load_dotenv()

# --- Agent Definition ---

#llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0)
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0)

class UseCase(BaseModel):
    use_case_name: str = Field(description="A concise name for the competitor's AI use case.")
    description: str = Field(description="A brief summary of what the use case does and its business value.")
    required_data_points: List[str] = Field(description="A list of data types or specific data points needed to implement this use case.")

class CompetitorAnalysis(BaseModel):
    """A structured analysis of competitor AI use cases."""
    use_cases: List[UseCase] = Field(description="A list of competitor AI use cases found from web research.")

class AgentState(TypedDict):
    """Represents the state of our graph."""
    # Inputs
    document_id: Optional[str]
    company_business: Optional[str]
    location: Optional[str]
    data_scientist_man_hours: Optional[int]
    data_engineer_man_hours: Optional[int]
    # Outputs
    data_catalogue_info: Optional[str] = None
    competitor_use_cases: Optional[List[dict]] = None
    identified_use_cases: Optional[str] = None
    missing_data_sources: Optional[str] = None
    project_plan: Optional[str] = None

# --- Node Functions ---

@tool
def ingest_catalogue_from_drive(document_id: str) -> dict:
    """Ingests a document from Google Drive and extracts a data catalogue."""
    return {"data_catalogue_info": moduel_for_ingest_data_catalogue(document_id)}

def research_competitor_use_cases(state: AgentState) -> dict:
    """Searches the web for competitor use cases and structures the findings."""
    search_tool = TavilySearchResults(max_results=3)
    query = f"Fetch AI and machine learning use cases in English Language for {state['company_business']} companies in {state['location']}"
    search_results = search_tool.invoke({"query": query})
    if not search_results:
        return {"competitor_use_cases": []}
    
    structured_llm = llm.with_structured_output(CompetitorAnalysis)
    extraction_prompt = f"Based on the following web search results, extract up to 3 distinct AI use cases and display them in English only.\n\nWeb Search Results:\n{json.dumps(search_results, indent=2)}"
    structured_response = structured_llm.invoke(extraction_prompt)
    use_cases_as_dicts = [uc.dict() for uc in structured_response.use_cases]
    return {"competitor_use_cases": use_cases_as_dicts}

def identify_use_cases(state: AgentState) -> dict:
    """Identifies viable use cases from the data catalogue and competitor data."""
    prompt = f"Analyze the data catalogue and competitor use cases. Identify viable use cases that can be built with the current data.\n\nData Catalogue: {state['data_catalogue_info']}\nCompetitor Use Cases: {json.dumps(state['competitor_use_cases'], indent=2)}"
    response = llm.invoke(prompt)
    return {"identified_use_cases": response.content}

def analyze_data_gaps(state: AgentState) -> dict:
    """Analyzes missing data for competitor use cases not currently possible."""
    prompt = f"Analyze the competitor use cases and the data catalogue. Identify what data points are missing to implement the competitor use cases.\n\nData Catalogue: {state['data_catalogue_info']}\nCompetitor Use Cases: {json.dumps(state['competitor_use_cases'], indent=2)}"
    response = llm.invoke(prompt)
    return {"missing_data_sources": response.content}

def propose_project_plan(state: AgentState) -> dict:
    """Proposes a phased project plan based on team capacity and analysis."""
    prompt = f"""
    You are an operations research expert. Your team has:
    - Data Scientist Man-Hours: {state['data_scientist_man_hours']}
    - Data Engineer Man-Hours: {state['data_engineer_man_hours']}

    Analysis:
    1. Viable AI Use Cases (current data): {state['identified_use_cases']}
    2. Potential Use Cases (missing data): {state['missing_data_sources']}

    Create a phased project plan.
    **Phase 1: Immediate Implementation (No Dependencies)**
    - List use cases from "Viable AI Use Cases" that fit the capacity.
    - Estimate man-hours for DS and DE for each.

    **Phase 2: Future Roadmap (Requires Data Sourcing)**
    - List use cases from "Potential Use Cases".
    - Estimate DE hours for data sourcing, then DS hours for development.
    
    Provide a clear summary of what can be achieved now (Phase 1) vs. later (Phase 2).
    """
    response = llm.invoke(prompt)
    return {"project_plan": response.content}

# --- Graph Construction ---

workflow = StateGraph(AgentState)
workflow.add_node("ingest", ingest_catalogue_from_drive)
workflow.add_node("competitor_analysis", research_competitor_use_cases)
workflow.add_node("identify_use_cases", identify_use_cases)
workflow.add_node("analyze_data_gaps", analyze_data_gaps)
workflow.add_node("propose_plan", propose_project_plan)

workflow.add_edge(START, "ingest")
workflow.add_edge("ingest", "competitor_analysis")
workflow.add_edge("competitor_analysis", "identify_use_cases")
workflow.add_edge("identify_use_cases", "analyze_data_gaps")
workflow.add_edge("analyze_data_gaps", "propose_plan")
workflow.add_edge("propose_plan", END)

app = workflow.compile()

# --- Agent Runner Function ---

def run_agent(inputs: dict):
    """
    Runs the LangGraph agent and yields formatted strings for streaming.
    """
    yield "✅ **Agent Initialized**\n\n"
    yield f"- **Document ID:** `{inputs.get('document_id')}`\n"
    yield f"- **Business:** `{inputs.get('company_business')}`\n"
    yield f"- **Location:** `{inputs.get('location')}`\n"
    yield f"- **DS Hours:** `{inputs.get('data_scientist_man_hours')}`\n"
    yield f"- **DE Hours:** `{inputs.get('data_engineer_man_hours')}`\n\n"
    yield "🚀 **Starting analysis...**\n\n---\n\n"

    # CHANGE: Added a try...except block to catch and report errors during graph execution.
    # This prevents silent failures and makes it clear why the '__end__' state might not be reached.
    try:
        for event in app.stream(inputs):
            for node_name, output in event.items():
                print(f'node_name : {node_name}')
                if node_name == "ingest":
                    yield "📂 Ingesting data catalogue from Google Drive...\n"
                elif node_name == "competitor_analysis":
                    yield "🌐 Researching competitor use cases...\n"
                    print(output.keys())
                    if output.get("competitor_use_cases"):
                        for i, uc in enumerate(output["competitor_use_cases"], 1):
                            yield f"\n**{i}. {uc.get('use_case_name', 'N/A')}**\n"
                            yield f"   - **Description:** {uc.get('description', 'N/A')}\n"
                            data_points = ", ".join(uc.get('required_data_points', []))
                            yield f"   - **Required Data:** {data_points or 'N/A'}\n"
                elif node_name == "identify_use_cases":
                    yield "\n🎯 Identifying viable use cases with current data...\n"
                    print(output.keys())
                    yield(output.get("identified_use_cases"))
                elif node_name == "analyze_data_gaps":
                    yield "\n🔍 Analyzing data gaps for future use cases...\n"
                    print(output.keys())
                    yield(output.get("missing_data_sources"))
                elif node_name == "propose_plan":
                    yield "\n📋 Generating phased project plan...\n"
                    print(output.keys())
                    yield output.get("project_plan", "_No project plan was generated._")
                    
                elif node_name == "__end__":
                    final_state = output
                    
                    yield "\n---\n\n🏁 **Analysis Complete!**\n\n"
                    
                    # Stream the final report sections immediately
                    if final_state:
                        yield "\n\n### Competitor Use Case Analysis\n"
                        if final_state.get("competitor_use_cases"):
                            for i, uc in enumerate(final_state["competitor_use_cases"], 1):
                                yield f"\n**{i}. {uc.get('use_case_name', 'N/A')}**\n"
                                yield f"   - **Description:** {uc.get('description', 'N/A')}\n"
                                data_points = ", ".join(uc.get('required_data_points', []))
                                yield f"   - **Required Data:** {data_points or 'N/A'}\n"
                        else:
                            yield "_No competitor use cases were found._\n"

                        yield "\n\n### Proposed Project Plan (Operations Research Layer)\n"
                        yield final_state.get("project_plan", "_No project plan was generated._")

    except Exception as e:
        yield "\n\n---\n\n"
        yield " Bummer! An error occurred during the analysis.\n\n"
        yield "This is often caused by an issue in one of the agent's tools (e.g., API key error, document access issue, or a data processing problem).\n\n"
        yield "**Error Details:**\n"
        yield "```\n"
        yield f"{traceback.format_exc()}\n"
        yield "```\n"