import os
import logging
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

class RAGPipeline:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        self.embeddings = OpenAIEmbeddings()
        
        try:
            self.vector_store = Chroma(
                persist_directory=self.persist_directory,
                embedding_function=self.embeddings
            )
            self.retriever = self.vector_store.as_retriever(search_kwargs={"k": 4})
            logger.info("ChromaDB vector store loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load ChromaDB: {e}")
            self.vector_store = None
            self.retriever = None

        # You can switch to gpt-4 or any other model as needed.
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.3)
        self.prompt = PromptTemplate.from_template(SYSTEM_PROMPT)

    def format_docs(self, docs):
        return "\n\n".join(doc.page_content for doc in docs)

    def answer_question(self, question: str, history: str) -> str:
        """Answers a question using the retrieved context and chat history."""
        if not self.retriever:
            return "I'm sorry, my knowledge base is currently unavailable."
            
        try:
            docs = self.retriever.invoke(question)
            context = self.format_docs(docs)
            
            chain = self.prompt | self.llm | StrOutputParser()
            
            response = chain.invoke({
                "context": context,
                "history": history,
                "question": question
            })
            
            if "UNKNOWN_ANSWER" in response:
                return None
                
            return response
        except Exception as e:
            logger.error(f"Error generating answer: {e}")
            return None

    def learn_qa_pair(self, question: str, answer: str):
        """Learns a new Q&A pair dynamically by adding it to the vector store."""
        if not self.vector_store:
            logger.error("Cannot learn: Vector store is not initialized.")
            return

        text = f"Question: {question}\nAnswer: {answer}"
        try:
            self.vector_store.add_texts(texts=[text], metadatas=[{"source": "human_assistant"}])
            logger.info("Successfully learned new Q&A pair from human assistant.")
        except Exception as e:
            logger.error(f"Failed to learn Q&A pair: {e}")
