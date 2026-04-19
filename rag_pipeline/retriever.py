import os
import logging
from langchain_chroma import Chroma
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config.prompts import get_system_prompt

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
            logger.info("ChromaDB vector store loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load ChromaDB: {e}")
            self.vector_store = None

        # You can switch to gpt-4 or any other model as needed.
        self.llm = ChatOpenAI(model="gpt-4o", temperature=0.3)

    def format_docs(self, docs):
        return "\n\n---\n\n".join(doc.page_content for doc in docs)

    def retrieve_with_scores(self, question: str, k: int = 12, min_score: float = 0.15):
        """
        Retrieves documents using similarity search with relevance scores.
        Filters out chunks that are too irrelevant (below min_score).
        Lower min_score = more permissive (includes more chunks).
        """
        if not self.vector_store:
            return []

        try:
            results = self.vector_store.similarity_search_with_relevance_scores(question, k=k)
            
            # Log scores for debugging
            for doc, score in results[:5]:
                preview = doc.page_content[:80].replace('\n', ' ')
                logger.info(f"  Score: {score:.3f} | {preview}...")

            # Filter by minimum relevance score
            filtered = [doc for doc, score in results if score >= min_score]
            
            if not filtered:
                logger.info(f"No chunks passed the relevance threshold ({min_score})")
                # Fall back to top 5 results anyway to give the LLM a chance
                filtered = [doc for doc, score in results[:5]]
            
            logger.info(f"Retrieved {len(filtered)} relevant chunks (from {len(results)} total)")
            return filtered
            
        except Exception as e:
            logger.error(f"Error during retrieval: {e}")
            return []

    def answer_question(self, question: str, history: str) -> str:
        """Answers a question using the retrieved context and chat history."""
        if not self.vector_store:
            return "I'm sorry, my knowledge base is currently unavailable."
            
        try:
            docs = self.retrieve_with_scores(question)
            
            if not docs:
                logger.info("No documents retrieved. Staying silent.")
                return None
            
            context = self.format_docs(docs)
            
            # Build prompt fresh each time so STRICTNESS_LEVEL changes take effect
            prompt = PromptTemplate.from_template(get_system_prompt())
            chain = prompt | self.llm | StrOutputParser()
            
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

        text = f"[Topic: Learned from Human Assistant]\n\nQuestion: {question}\nAnswer: {answer}"
        try:
            self.vector_store.add_texts(texts=[text], metadatas=[{"source": "human_assistant"}])
            logger.info("Successfully learned new Q&A pair from human assistant.")
        except Exception as e:
            logger.error(f"Failed to learn Q&A pair: {e}")
