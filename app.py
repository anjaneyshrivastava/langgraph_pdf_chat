from langchain.text_splitter import RecursiveCharacterTextSplitter
# from langchain_chroma import Chroma
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import GPT4AllEmbeddings
from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOllama
from langchain_core.output_parsers import JsonOutputParser
from langchain import hub
from langchain_core.output_parsers import StrOutputParser
from typing_extensions import TypedDict
from typing import List
from langchain.schema import Document
from langgraph.graph import END, StateGraph
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_community.document_loaders import PyPDFLoader
import streamlit as st
import os

local_llm = "llama3"
tavily_api_key = os.environ['TAVILY_API_KEY'] = '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'
st.title("Multi-PDF ChatBot using LLAMA3 & Adaptive RAG")
user_input = st.text_input("Question",placeholder="Ask about your PDF",key='input')
with st.sidebar:
    uploaded_files = st.file_uploader("Upload your file",type=['pdf'],accept_multiple_files=True)
    process = st.button("Process")

if process:
    if not uploaded_files:
        st.warning("Please upload atleast one PDF file.")
        st.stop
    
    temp_dir = 'C:/Project/Langraph_adaptiveRag_llama3/temp'
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)

    for uploaded_file in uploaded_files:
        temp_file_path = os.path.join(temp_dir,uploaded_file.name)

        with open(temp_file_path,"wb") as file:
            file.write(uploaded_file.getbuffer())

        try:
            loader = PyPDFLoader(temp_file_path)
            data = loader.load()
            st.write(f"Data loaded for {uploaded_file.name}")
        except Exception as e:
            st.error(f"Failed to load {uploaded_file.name} : {str(e)}")
    
    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size = 250, chunk_overlap=0
    )

    text_chunks = text_splitter.split_documents(data)

    embedding_function = GPT4AllEmbeddings()

    vectorstore = Chroma.from_documents(
        documents = text_chunks,
        embedding = embedding_function,
        collection_name = 'rag-Chroma',
        
    )
    retriever = vectorstore.as_retriever()
    llm = ChatOllama(model=local_llm,format='json',temperature=0)
    prompt = PromptTemplate(
        template="""You are an expert at routing a user question to a vectorstore or a websearch. \n
        Use the vectorstore for questions or LLM agents, prompt engineering, and adverserial attacks. \n
        Otherwise, use web-search. Giver a binary choice 'web_search' or 'vectorstores' based on the question. \n
        Return the a JSON with a single key 'datasources' and no premable or explaination. \n
        Question to route: {question}""",
        input_variables=["question"],
    )
    question_router = prompt | llm | JsonOutputParser()
    question = "llm agent memory"
    docs = retriever.get_relevant_documents(question)
    doc_txt = docs[1].page_content
    question_router.invoke({"question":question})

    llm = ChatOllama(model=local_llm, format="json",temperature=0)

    prompt = PromptTemplate(
        template="""You are a grader assessing relevance of a retreived document to a user question. \n
        Here is the retrieved document: \n\n {document} \n\n
        Here is the user question: {question} \n
        If the document contains keywords related to the user question, grade it as relevant. \n
        It does not need to be a stringent text. The goal is to filter out erroneous retrievals. \n
        Give a binary score 'yes' or 'no' score to indicate whteher the document is relevant to the question. \n
        Provide the binary score as a JSON with a single key 'score' and no premable or explanation.""",
        input_variables=["question","document"],
    )

    retriever_garde = prompt | llm | JsonOutputParser()
    question = "agent memory"
    docs = retriever.get_relevant_documents(question)
    doc_txt = docs[1].page_content
    st.write(retriever_garde.invoke({"question" : question, "document" : doc_txt}))

    prompt = hub.pull("rlm/rag-prompt")

    llm = ChatOllama(model=local_llm,temperature=0)

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    rag_chain = prompt | llm | StrOutputParser()

    question = "agent memory"
    generation = rag_chain.invoke({"context" : docs , "question" : question})

    llm = ChatOllama(model=local_llm, format="json",temperature=0)

    prompt = PromptTemplate(
        template = """You are grader assessing whether an answer is grounded in / supported by a set of facts. \n
        Here are the facts:
        \n ------- \n
        {documents}
        \n ------- \n
        Here is the answer: {generation}
        Give a binary score 'yes' or 'no' score to indicate whether the answer is grounded in / supported by a set of facts. \n
        Provide the binary score as a Json with a single key 'score' and no preamble or explanation.""",
        input_variables=["generation", "documents"],
    )

    hallucination_grader = prompt | llm | JsonOutputParser()
    hallucination_grader.invoke({"documents": docs, "generation": generation})

    llm = ChatOllama(model=local_llm, format="json",temperature=0)

    prompt = PromptTemplate(
        template="""You are a grader assessing whether an answer is useful to resolve a question. \n
        Here is the answer:
        \n ------- \n
        {generation}
        \n ------- \n
        Here is the question: {question}
        Give a binary score 'yes' or 'no' to indicate whether the answer is userful to resolve a question. \n
        Provide the binary score as a JSON with a single key 'score' and no preable or explanation.""",
        input_variables=["generation", "question"],
    )     
    
    answer_grader = prompt | llm | JsonOutputParser()
    answer_grader.invoke({"question" : question, "generation" : generation})

    llm = ChatOllama(model=local_llm, temperature=0)

    re_write_prompt = PromptTemplate(
        template="""You a question re-writer that converts an input question to a better version that is optimized \n
        for vectorstore retrieval. Look at the initial and formulate an improved question. \n
        Here is the initial question: \n\n {question}. Improved question with no preamble: \n """,
        input_variables=["generation","question"],
    )

    question_rewriter = re_write_prompt | llm | StrOutputParser()
    question_rewriter.invoke({"question":question})

    web_search_tool = TavilySearchResults(k=3, tavily_api_key=tavily_api_key)


    class GraphState(TypedDict):
        """
        Represents the state of our graph.

        Attributes:
            question: question
            generation: LLM generation
            documents: list of documents
        """
        question : str
        generation : str
        documents : List[str]

    def retrieve(state):
        """
        Retreive documents

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, documents, that contains retrieved documents
        """
        st.write("---Retrieve---")
        question = state["question"]

        documents = retriever.get_relevant_documents(question)
        return {"documents":documents, "question":question}
    
    def generate(state):
        """
        Generate answer

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): New key added to state, generation, that contains LLM generation
        """

        st.write("---GENERATE---")
        question = state["question"]
        documents = state["documents"]

        generation = rag_chain.invoke({"context" : documents , "question" : question})
        return {"documents" : documents , "question" : question, "generation" : generation}
    
    def grade_documents(state):
        """
        Determine whether the retrieved documents are relevant to the question.

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): Updates documents key with only filtered relevant documents
        """
        st.write("--Check Document RELEVANCE TO QUESTION---")
        question = state['question']
        documents = state["documents"]

        filtered_docs = []
        for d in documents:
            score = retriever_garde.invoke({"question":question, "document" : d.page_content})
            grade = score['score']
            if grade == "yes":
                st.write("---GRADE: DOCUMENT RLEVANT---")
                filtered_docs.append(d)
            else:
                st.write("---GRADE: DOCUMENT NOT RELEVANT")
                continue
        
        return {"documents":filtered_docs, "question":question}
    
    def transform_query(state):
        """
        Transform the query to produce a better question

        Args:
            state (dict): The current graph state

        Returns:
            State (dict): Updates question key with a re-phrased question
        """
        st.write("---TRANSFORM QUERY---")
        question = state["question"]
        documents = state["documents"]

        better_question = question_rewriter.invoke({"question" : question})
        return {"documents":documents, "question":better_question}
    
    def web_search(state):
        """
        Web search based on the re-phrased question

        Args:
            state (dict): The current graph state

        Returns:
            state (dict): Updates documents key with appended web results
        """
        st.write("---WEB SEARCH---")
        question = state["question"]

        docs = web_search_tool.invoke({"query": question})
        web_results = "\n".join([d["content"] for d in docs])
        web_results = Document(page_content=web_results)

        return {"documents" : web_results , "question":question}
    
    def route_question(state):
        """
        Route question to web search or RAG

        Args:
            state (dict): The current graph state

        Returs:
            str: Next node to call
        """
        st.write("---ROUTE QUESTION---")
        question = state["question"]
        st.write(question)
        source = question_router.invoke({"question": question})
        print(f"Source: {source}")  # Print the source dictionary

        if 'datasources' in source:
            datasource = source['datasources']
            if isinstance(datasource, list):  # Check if datasource is a list
                datasource = datasource[0]  # If it's a list, take the first element
            print(f"Datasource: {datasource}")  # Print the datasource
        else:
            print("The 'datasources' key does not exist in the source dictionary.")
            datasource = None  # Set datasource to None if 'datasources' key does not exist

        if datasource == 'web_search':
            print("---ROUTE QUESTION TO WEB SEARCH---")
            return "web_search"
        elif datasource == 'vectorstores':
            print("---ROUTE QUESTION TO VECTORSTORE---")
            return "retrieve"  # Return 'retrieve' when datasource is 'vectorstores'
        else:
            print("The datasource is neither 'web_search' nor 'vectorstore'.")
            return None  # Return None if datasource is not 'web_search' or 'vectorstore'

    def decide_to_generate(state):
        """
        Determine whether to generate an answer, or re-generate a question.

        Args:
            state (dict): The current graph state

        Returns:
            str: Binary decision for next node to call
        """   
        st.write("---ASSESS GRADED DOCUMENTS---")
        question = state['question']
        filtered_documents = state["documents"]

        if not filtered_documents:
            st.write("---DECISION: ALL DOCUMENTS ARE NOT RELEVANT TO QUESTION, TRANSFORM QUERY---")
            return "transform_query"
        
        else:
            st.write("---DECISION: GENERATE---")
            return "generate"

    def grade_generation_v_documents_and_question(state):
        """
        Determine whether the generation is grounded in the document and answer question.

        Args:
            state (dict): The current graph state

        Returns:
            str: Decision for next node to call
        """
        st.write("---CHECK HALLUCINATIONS---")
        question = state["question"]
        documents = state["documents"]
        generation = state["generation"]

        score = hallucination_grader.invoke({"documents": documents, "generation" : generation})
        grade = score['score']
        if grade == "yes":
            st.write("---DECISION: GENERATION IS GROUNDED IN DOCUMENTS---")
            st.write("---GRADE GENERATION vs QUESTION---")
            score = answer_grader.invoke({"question":question, "generation" : generation})
            grade = score['score']
            if grade == "yes":
                st.write("---DECISION: GENERATION ADDRESS QUESTION---")
                return "useful"
            else:
                st.write("---DECISION: GENERATION DOESNOT ADDRESS QUESTION---")
                return "not useful"
        else:
            st.write("---DECISION: GENERATION DOES NOT ADDRESS QUESTION---")
            return "not useful"
    
    workflow = StateGraph(GraphState)

    workflow.add_node("web_search",web_search)
    workflow.add_node("retrieve",retrieve)
    workflow.add_node("grade_documents",grade_documents)
    workflow.add_node("generate",generate)
    workflow.add_node("transform_query",transform_query)

    workflow.set_conditional_entry_point(
        route_question,
        {
            "web_search": "web_search",
            "vectorstore": "retrieve",
        },
    )

    workflow.add_edge("web_search","generate")
    workflow.add_edge("retrieve","grade_documents")
    workflow.add_conditional_edges(
        "grade_documents",
        decide_to_generate,
        {
            "transform_query" : "transform_query",
            "generate" : "generate"
        }
    )

    workflow.add_edge("transform_query", "retrieve")
    workflow.add_conditional_edges(
        "generate",
        grade_generation_v_documents_and_question,
        {
            "not supported" : "generate",
            "useful" : END,
            "not useful" : "transform_query",
        },
    )

    app = workflow.compile()

    inputs = {"question":user_input}

    for output in app.stream(inputs):
        for key , value in output.items:

            st.write(f"Node '{key}':")
        print("\n---\n")

    st.write(value["generation"])
