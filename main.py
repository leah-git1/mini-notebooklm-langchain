import os
import warnings
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.prebuilt import create_react_agent

# השתקת אזהרות פג תוקף (Deprecation Warnings)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# מנגנון ייבוא חכם ל-Tavily
try:
    from langchain_tavily import TavilySearchResults
except ImportError:
    from langchain_community.tools.tavily_search import TavilySearchResults

# טעינת מפתחות ה-API
load_dotenv()

def verify_api_keys() -> None:
    """ודא שמפתחות ה-API הוגדרו בהצלחה בקובץ .env"""
    if not os.getenv("OPENAI_API_KEY"):
        raise ValueError("❌ ERROR: OPENAI_API_KEY is missing. Please check your .env file.")
    if not os.getenv("TAVILY_API_KEY"):
        raise ValueError("❌ ERROR: TAVILY_API_KEY is missing. Please check your .env file.")

def run_research_agent(topic: str) -> None:
    """
    מפעילה סוכן לאיסוף מקורות מידע באמצעות מנוע החיפוש Tavily.
    """
    verify_api_keys()

    # 1. אתחול מודל השפה
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2)

    # 2. אתחול כלי החיפוש של Tavily (מקסימום 3 תוצאות)
    search_tool = TavilySearchResults(max_results=3)
    tools = [search_tool]

    # 3. הגדרת הנחיות המערכת (System Prompt)
    system_prompt = (
        "You are an expert research assistant for a NotebookLM-like application.\n"
        "Your mission is to gather high-quality, reliable, and diverse sources about the user's topic.\n\n"
        "Instructions:\n"
        "1. Identify key search terms and use the search tool to find real web articles or documentation.\n"
        "2. Present your findings in a structured list. For each source, you MUST include:\n"
        "   - **Title**: The title of the page.\n"
        "   - **URL**: The exact web link (do not hallucinate or change URLs).\n"
        "   - **Description**: A 2-sentence summary of what this source contains.\n"
        "3. Only use real links provided by the tool. Be factual and objective."
    )

    # 4. יצירת ה-Agent הבסיסי - ללא פרמטרים שמשתנים בין גרסאות!
    # פתרון זה תואם 100% לכל גרסאות LangGraph בעבר ובעתיד
    agent_executor = create_react_agent(
        model=llm,
        tools=tools
    )

    print(f"🕵️‍♂️ Agent initialized. Searching the web for: '{topic}'...\n")

    try:
        # 5. הפעלת הסוכן: אנו מעבירים את ה-System Prompt כהודעה הראשונה בגרף
        response = agent_executor.invoke({
            "messages": [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Please find high-quality sources about: {topic}")
            ]
        })

        # חילוץ ההודעה האחרונה בגרף (התוצאה הסופית)
        final_message = response["messages"][-1]
        
        print("\n" + "="*50)
        print("📋 AGENT RESEARCH RESULTS:")
        print("="*50)
        print(final_message.content)
        print("="*50)

    except Exception as e:
        print(f"❌ An error occurred during search: {e}")

if __name__ == "__main__":
    # הרצת בדיקה על נושא מסוים
    test_topic = "React 19 key features and release updates"
    run_research_agent(test_topic)