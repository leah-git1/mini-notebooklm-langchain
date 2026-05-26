import os
import uuid
import streamlit as st
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

# טעינת משתני סביבה
load_dotenv()

# הגדרת עיצוב דף בסיסי ב-Streamlit
st.set_page_config(
    page_title="Mini NotebookLM",
    page_icon="🧠",
    layout="wide"
)

# ==========================================
# 1. הגדרת ה-State Graph של LangGraph
# ==========================================
from typing import TypedDict, List, Dict, Any

class ResearchState(TypedDict):
    topic: str
    raw_sources: List[Dict[str, Any]]
    approved_sources: List[Dict[str, Any]]
    summary: str

def gather_sources(state: ResearchState) -> Dict[str, Any]:
    # ייבוא חכם של Tavily
    try:
        from langchain_tavily import TavilySearchResults
    except ImportError:
        from langchain_community.tools.tavily_search import TavilySearchResults
        
    search_tool = TavilySearchResults(max_results=5)
    search_results = search_tool.invoke({"query": state["topic"]})
    
    sources = []
    for idx, result in enumerate(search_results, 1):
        sources.append({
            "id": idx,
            "title": result.get("title", f"Source {idx}"),
            "url": result.get("url", "#"),
            "content": result.get("content", "")
        })
    return {"raw_sources": sources}

def summarize_sources(state: ResearchState) -> Dict[str, Any]:
    approved = state.get("approved_sources", [])
    if not approved:
        return {"summary": "No sources were approved by the user."}
    
    context_parts = []
    for src in approved:
        context_parts.append(f"Title: {src['title']}\nURL: {src['url']}\nContent: {src['content']}\n---")
    context = "\n".join(context_parts)
    
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    system_prompt = (
        "You are an expert research editor. Summarize the approved sources provided below into a structured summary.\n"
        "Focus on extracting key insights, and list the verified URLs at the end as references."
    )
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Topic: {state['topic']}\n\nSources Context:\n{context}")
    ])
    return {"summary": response.content}

# שמירת הגרף בזיכרון של Streamlit כדי שלא יאותחל מחדש בכל לחיצת כפתור (Rerun)
@st.cache_resource
def get_compiled_app():
    workflow = StateGraph(ResearchState)
    workflow.add_node("gather_sources", gather_sources)
    workflow.add_node("summarize_sources", summarize_sources)
    workflow.add_edge(START, "gather_sources")
    workflow.add_edge("gather_sources", "summarize_sources")
    workflow.add_edge("summarize_sources", END)
    
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory, interrupt_before=["summarize_sources"])

app = get_compiled_app()

# ==========================================
# 2. ניהול המצב של ממשק המשתמש (UI Session State)
# ==========================================
if "step" not in st.session_state:
    st.session_state.step = "INPUT"  # שלבים אפשריים: INPUT, APPROVE, SUMMARY
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "topic" not in st.session_state:
    st.session_state.topic = ""
if "raw_sources" not in st.session_state:
    st.session_state.raw_sources = []
if "selected_source_ids" not in st.session_state:
    st.session_state.selected_source_ids = []

config = {"configurable": {"thread_id": st.session_state.thread_id}}


st.title("🧠 Mini NotebookLM - Research Agent")
st.write("Welcome to your autonomous research assistant. Provide a topic, approve the sources, and get a professional summary.")

# בדיקת מפתחות API
if not os.getenv("OPENAI_API_KEY") or not os.getenv("TAVILY_API_KEY"):
    st.error("⚠️ API Keys are missing. Please configure your `.env` file.")
    st.stop()


if st.session_state.step == "INPUT":
    st.subheader("What would you like to research today?")
    topic_input = st.text_input(
        "Enter research topic:", 
        placeholder="e.g., Breakthroughs in Fusion Energy in 2024",
        value=st.session_state.topic
    )
    
    if st.button("Start Research 🚀", use_container_width=True):
        if topic_input.strip() == "":
            st.warning("Please enter a valid topic.")
        else:
            st.session_state.topic = topic_input
            with st.spinner("🕵️‍♂️ Agent is searching the web and gathering sources..."):

                app.invoke({"topic": topic_input}, config)
                

                state_info = app.get_state(config)
                st.session_state.raw_sources = state_info.values.get("raw_sources", [])
                st.session_state.step = "APPROVE"
                st.rerun()


elif st.session_state.step == "APPROVE":
    st.subheader(f"📋 Sources found for: *\"{st.session_state.topic}\"*")
    st.write("Select the sources you want to include in the final summary:")
    
    approved_sources_temp = []
    

    for src in st.session_state.raw_sources:
        col1, col2 = st.columns([0.05, 0.95])
        with col1:

            is_checked = st.checkbox("", key=f"src_{src['id']}", value=True)
            if is_checked:
                approved_sources_temp.append(src)
        with col2:
            with st.expander(f"**[{src['id']}] {src['title']}**", expanded=True):
                st.markdown(f"**Link:** [{src['url']}]({src['url']})")
                st.write(src['content'][:300] + "...")
                
    st.write("---")
    
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("⬅️ Start Over", use_container_width=True):
            st.session_state.step = "INPUT"
            st.session_state.thread_id = str(uuid.uuid4()) # איפוס הזיכרון
            st.rerun()
            
    with col_next:
        if st.button("Generate Summary ✨", use_container_width=True):
            if not approved_sources_temp:
                st.error("Please select at least one source to generate a summary.")
            else:
                with st.spinner("✍️ Resuming agent to write the summary..."):

                    app.update_state(config, {"approved_sources": approved_sources_temp})

                    final_state = app.invoke(None, config)
                    
                    st.session_state.summary = final_state.get("summary", "No summary generated.")
                    st.session_state.step = "SUMMARY"
                    st.rerun()

elif st.session_state.step == "SUMMARY":
    st.subheader(f"📝 Research Summary: *\"{st.session_state.topic}\"*")
    
    st.markdown(st.session_state.summary)
    
    st.write("---")
    
    st.download_button(
        label="📥 Download Summary as Markdown",
        data=st.session_state.summary,
        file_name=f"summary_{st.session_state.topic.replace(' ', '_')}.md",
        mime="text/markdown",
        use_container_width=True
    )
    
    if st.button("🔄 Start a New Research Session", use_container_width=True):
        st.session_state.step = "INPUT"
        st.session_state.topic = ""
        st.session_state.raw_sources = []
        st.session_state.thread_id = str(uuid.uuid4()) # איפוס מזהה שיחה
        st.rerun()