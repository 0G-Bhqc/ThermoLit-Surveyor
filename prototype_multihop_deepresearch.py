import asyncio
import time
import json
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from sciverse_adapter import SciverseAdapter
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL, SCIVERSE_TOKEN

class AgentState(TypedDict):
    initial_query: str
    pass1_papers: List[dict]
    pass1_records: List[dict]
    followup_queries: List[str]
    pass2_papers: List[dict]
    pass2_records: List[dict]
    all_papers: List[dict]
    all_records: List[dict]
    knowledge_graph: dict
    deep_gap_report: str
    metrics: dict

adapter = SciverseAdapter(token=SCIVERSE_TOKEN)

def initial_web_search_node(state: AgentState) -> AgentState:
    start_time = time.time()
    print("[Pass 1: Broad Sciverse Search] Executing Sciverse API for initial query...")
    q = state['initial_query']
    papers = asyncio.run(adapter.semantic_search_async(q, top_k=3))
    state['pass1_papers'] = papers
    state['metrics'] = state.get('metrics', {})
    state['metrics']['pass1_search_time'] = time.time() - start_time
    state['metrics']['pass1_papers_count'] = len(papers)
    return state

def pass1_extract_node(state: AgentState) -> AgentState:
    start_time = time.time()
    print("[Pass 1: Schema Extract] Extracting thermoelectric parameters...")
    papers = state['pass1_papers']
    llm = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
    )
    records = []
    for p in papers:
        prompt = f"""Extract Thermoelectric Parameters in JSON:
{{
  "material_system": "Material formula",
  "zT_value": "reported zT @ T",
  "seebeck_coefficient": "S value with units",
  "thermal_conductivity": "kappa value with units",
  "electrical_conductivity": "sigma or resistivity with units",
  "missing_parameters": ["list of parameters missing in this text"]
}}
Excerpt: {p['text']}
Return ONLY valid JSON."""
        try:
            res = llm.invoke([HumanMessage(content=prompt)])
            txt = res.content.strip().strip("```json").strip("```")
            data = json.loads(txt)
            data['title'] = p['title']
            data['doi'] = p.get('doi', 'N/A')
            records.append(data)
        except Exception as e:
            records.append({'title': p['title'], 'doi': p.get('doi', 'N/A'), 'error': str(e)})
            
    state['pass1_records'] = records
    state['metrics']['pass1_extract_time'] = time.time() - start_time
    return state

def query_refine_node(state: AgentState) -> AgentState:
    start_time = time.time()
    print("[Iterative Deepening] Analyzing Pass 1 voids to generate targeted follow-up queries...")
    records = state['pass1_records']
    llm = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
    )
    prompt = f"""Review the extracted thermoelectric records from Pass 1:
{json.dumps(records, ensure_ascii=False, indent=2)}

Identify specific missing data or unverified mechanisms (e.g. missing Seebeck coefficient values, carrier mobility, or specific doping effects).
Generate exactly 2 targeted, highly specific academic search queries in English to retrieve the missing information via Sciverse API.

Return a JSON array of 2 string queries, e.g. ["query 1", "query 2"]. Return ONLY valid JSON array."""
    
    try:
        res = llm.invoke([HumanMessage(content=prompt)])
        txt = res.content.strip().strip("```json").strip("```")
        queries = json.loads(txt)
        if not isinstance(queries, list):
            queries = ["Bi2Te3 Seebeck coefficient nanowire", "Bi2Te3 thermal conductivity Wiedemann Franz"]
    except Exception:
        queries = ["Bi2Te3 Seebeck coefficient nanowire", "Bi2Te3 thermal conductivity Wiedemann Franz"]
        
    state['followup_queries'] = queries
    print(f"Generated Follow-up Queries: {queries}")
    state['metrics']['refine_time'] = time.time() - start_time
    return state

def secondary_web_search_node(state: AgentState) -> AgentState:
    start_time = time.time()
    print("[Pass 2: Targeted Sciverse Search] Executing Sciverse API for follow-up queries...")
    queries = state['followup_queries']
    
    async def run_all_pass2():
        tasks = [adapter.semantic_search_async(q, top_k=2) for q in queries]
        results = await asyncio.gather(*tasks)
        flat = []
        for r in results:
            flat.extend(r)
        return flat
        
    pass2_papers = asyncio.run(run_all_pass2())
    state['pass2_papers'] = pass2_papers
    state['all_papers'] = state['pass1_papers'] + pass2_papers
    state['metrics']['pass2_search_time'] = time.time() - start_time
    state['metrics']['pass2_papers_count'] = len(pass2_papers)
    return state

def pass2_extract_and_synthesize_node(state: AgentState) -> AgentState:
    start_time = time.time()
    print("[Synthesize Engine] Extracting Pass 2 data, building Knowledge Graph & Multi-hop Gap Analysis...")
    
    llm = ChatOpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
    )
    
    pass2_records = []
    for p in state['pass2_papers']:
        prompt = f"""Extract Thermoelectric Parameters in JSON:
{{
  "material_system": "Material formula",
  "zT_value": "reported zT @ T",
  "seebeck_coefficient": "S value with units",
  "thermal_conductivity": "kappa value with units",
  "electrical_conductivity": "sigma or resistivity with units"
}}
Excerpt: {p['text']}
Return ONLY valid JSON."""
        try:
            res = llm.invoke([HumanMessage(content=prompt)])
            txt = res.content.strip().strip("```json").strip("```")
            data = json.loads(txt)
            data['title'] = p['title']
            data['doi'] = p.get('doi', 'N/A')
            pass2_records.append(data)
        except Exception:
            pass2_records.append({'title': p['title'], 'doi': p.get('doi', 'N/A')})
            
    state['pass2_records'] = pass2_records
    state['all_records'] = state['pass1_records'] + pass2_records
    
    synthesis_prompt = f"""You are the World's Leading AI for Science Thermoelectricity Specialist.
You have completed a 2-Pass Iterative DeepResearch Workflow combining broad search and targeted follow-up search via Sciverse API.

All Literature Records ({len(state['all_records'])} items across Pass 1 & Pass 2):
{json.dumps(state['all_records'], ensure_ascii=False, indent=2)}

Please generate a comprehensive, highly rigorous, physics-driven Academic Literature Survey Report on "Bi2Te3 Thermoelectric Decoupling & Research Gap Analysis".

Requirements:
1. **Multiscale Material Parameter Matrix**: Build a Markdown table comparing all material variants found across S, sigma, kappa_tot, kappa_e (derived via Wiedemann-Franz law kappa_e=L*sigma*T), kappa_l, and zT.
2. **Physics Transport Decoupling Analysis**: Detail the Wiedemann-Franz relationship kappa_e = L_0 * sigma * T and Debye-Callaway phonon scattering boundary effects.
3. **Cross-Pass Iterative Findings**: Explain how Pass 2 targeted search filled the knowledge gaps identified in Pass 1.
4. **5 Falsifiable Scientific Hypotheses (H1 to H5)**: Formulate 5 quantitative, experimentally testable hypotheses with precise equations/thresholds and MEMS/TEM/Debye-Callaway validation protocols.
5. **Sciverse Evidence Chain**: Provide a table of Sciverse hits and DOIs.

Write in elegant, authoritative Chinese academic markdown format.
"""
    res = llm.invoke([HumanMessage(content=synthesis_prompt)])
    state['deep_gap_report'] = res.content
    state['metrics']['synthesis_time'] = time.time() - start_time
    state['metrics']['total_papers_analyzed'] = len(state['all_papers'])
    return state

# Graph Workflow Construction
workflow = StateGraph(AgentState)
workflow.add_node("pass1_search", initial_web_search_node)
workflow.add_node("pass1_extract", pass1_extract_node)
workflow.add_node("query_refine", query_refine_node)
workflow.add_node("pass2_search", secondary_web_search_node)
workflow.add_node("synthesize", pass2_extract_and_synthesize_node)

workflow.set_entry_point("pass1_search")
workflow.add_edge("pass1_search", "pass1_extract")
workflow.add_edge("pass1_extract", "query_refine")
workflow.add_edge("query_refine", "pass2_search")
workflow.add_edge("pass2_search", "synthesize")
workflow.add_edge("synthesize", END)

app = workflow.compile()

def run_agent(query: str = "Bi2Te3 thermoelectric figure of merit zT Seebeck conductivity") -> dict:
    initial_state = {
        "initial_query": query,
        "metrics": {}
    }
    start_total = time.time()
    final_state = app.invoke(initial_state)
    total_duration = time.time() - start_total
    final_state['metrics']['total_pipeline_duration'] = total_duration
    return final_state

if __name__ == "__main__":
    print("=================================================================")
    print("Starting Multi-Hop Iterative DeepResearch Agent (ThermoLit-Surveyor)")
    print("=================================================================")
    res = run_agent()
    print("\n=== MULTI-HOP DEEPRESEARCH REPORT GENERATED ===")
    print(res['deep_gap_report'][:1000] + "\n...[Truncated for console]")
