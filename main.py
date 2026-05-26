import os
import warnings
from typing import TypedDict, List, Dict, Any
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

# השתקת אזהרות פג-תוקף
warnings.filterwarnings("ignore", category=DeprecationWarning)

# ייבוא חכם של Tavily
try:
    from langchain_tavily import TavilySearchResults
except ImportError:
    from langchain_community.tools.tavily_search import TavilySearchResults

# טעינת מפתחות API
load_dotenv()

# ==========================================
# 1. הגדרת ה-State (המצב) של הגרף
# ==========================================
class ResearchState(TypedDict):
    topic: str                  # הנושא שנחקר
    raw_sources: List[Dict[str, Any]]  # כל המקורות שנמצאו בחיפוש
    approved_sources: List[Dict[str, Any]]  # המקורות שהמשתמש אישר
    summary: str                # הסיכום הסופי של המקורות המאושרים


# ==========================================
# 2. הגדרת הפונקציות (Nodes) של הגרף
# ==========================================

def gather_sources(state: ResearchState) -> Dict[str, Any]:
    """שלב א' - חיפוש מקורות מידע ברשת באמצעות Tavily"""
    topic = state["topic"]
    print(f"\n🔎 Searching the web for: '{topic}'...")
    
    # הפעלת כלי החיפוש
    search_tool = TavilySearchResults(max_results=5)
    search_results = search_tool.invoke({"query": topic})
    
    sources = []
    # עיבוד התוצאות למבנה פשוט ונוח
    for idx, result in enumerate(search_results, 1):
        sources.append({
            "id": idx,
            "title": result.get("title", f"Source {idx}"),
            "url": result.get("url", "#"),
            "content": result.get("content", "")
        })
        
    return {"raw_sources": sources}


def summarize_sources(state: ResearchState) -> Dict[str, Any]:
    """שלב ג' - סיכום המקורות שאושרו בלבד"""
    approved = state.get("approved_sources", [])
    if not approved:
        return {"summary": "No sources were approved by the user."}
    
    print("\n✍️ Generating summary from approved sources...")
    
    # בניית הקשר (Context) מהמקורות המאושרים
    context_parts = []
    for src in approved:
        context_parts.append(f"Title: {src['title']}\nURL: {src['url']}\nContent: {src['content']}\n---")
    context = "\n".join(context_parts)
    
    # פנייה ל-LLM לצורך סיכום ממוקד
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)
    
    system_prompt = (
        "You are an expert editor. Summarize the approved sources provided below into a structured summary.\n"
        "Focus on extracting key insights, and list the verified URLs at the end as references."
    )
    
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Topic: {state['topic']}\n\nSources Context:\n{context}")
    ])
    
    return {"summary": response.content}


# ==========================================
# 3. בניית ה-Workflow וחיבור ה-Checkpointer
# ==========================================

# יצירת Graph חדש המבוסס על ה-State שלנו
workflow = StateGraph(ResearchState)

# הוספת הבלוקים (Nodes) לגרף
workflow.add_node("gather_sources", gather_sources)
workflow.add_node("summarize_sources", summarize_sources)

# הגדרת זרימת העבודה (Edges)
workflow.add_edge(START, "gather_sources")
workflow.add_edge("gather_sources", "summarize_sources")
workflow.add_edge("summarize_sources", END)

# יצירת זיכרון זמני (Checkpointer) לשמירת מצב הריצה
memory = MemorySaver()

# קימפול הגרף עם הגדרת עצירה (Interrupt) לפני שלב הסיכום!
app = workflow.compile(
    checkpointer=memory,
    interrupt_before=["summarize_sources"] # כאן מתרחש ה-Human in the loop
)


# ==========================================
# 4. הרצת התוכנית הראשית (CLI Interaction)
# ==========================================

def run_notebook_lm_flow():
    topic = "Key advancements in Quantum Computing in 2024"
    
    # הגדרת מזהה ייחודי לשיחה (Thread ID) - קריטי לצורך הזיכרון
    config = {"configurable": {"thread_id": "session_1"}}
    
    # 🏁 הרצה ראשונית - הגרף ירוץ ויעצור ממש לפני שלב הסיכום
    print("🚀 Starting NotebookLM Process...")
    app.invoke({"topic": topic}, config)
    
    # שליפת המצב הנוכחי של הגרף לאחר העצירה
    state_info = app.get_state(config)
    raw_sources = state_info.values.get("raw_sources", [])
    
    # הצגת המקורות למשתמש בטרמינל
    print("\n==========================================")
    print("📋 SOURCES GATHERED BY AGENT:")
    print("==========================================")
    for src in raw_sources:
        print(f"[{src['id']}] {src['title']}")
        print(f"    Link: {src['url']}")
        print(f"    Snippet: {src['content'][:150]}...\n")
    print("==========================================")
    
    # 👥 שלב ה-Human in the loop: קבלת קלט מהמשתמש
    user_input = input("Enter the source numbers you wish to approve (comma separated, e.g., '1,3,5'): ")
    
    # עיבוד בחירת המשתמש
    try:
        approved_ids = [int(x.strip()) for x in user_input.split(",") if x.strip().isdigit()]
    except Exception:
        approved_ids = []
        
    approved_sources = [src for src in raw_sources if src["id"] in approved_ids]
    print(f"\n✅ You approved {len(approved_sources)} sources.")
    
    # עדכון ה-State של הגרף בבחירות של המשתמש בצורה מאובטחת
    app.update_state(config, {"approved_sources": approved_sources})
    
    # 🔄 המשך הרצת הגרף מנקודת העצירה ועד לסיום
    print("\n🔄 Resuming flow to generate summary...")
    final_state = app.invoke(None, config)
    
    # הצגת התוצר הסופי
    print("\n==========================================")
    print("📝 FINAL INITIAL SUMMARY:")
    print("==========================================")
    print(final_state.get("summary", "No summary generated."))
    print("==========================================")


if __name__ == "__main__":
    run_notebook_lm_flow()