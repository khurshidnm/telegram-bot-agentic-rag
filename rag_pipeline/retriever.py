import os
import logging
import uuid
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

    def answer_question(self, question: str, history: str, script_hint: str = "Auto") -> str:
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
                "question": question,
                "script_hint": script_hint,
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

    @staticmethod
    def _format_qa_text(question: str, answer: str) -> str:
        return f"[Topic: Learned from Admin]\n\nQuestion: {question}\nAnswer: {answer}"

    def add_admin_qa_pair(self, question: str, answer: str, admin_id: int) -> str | None:
        """Adds an admin-provided Q&A pair and returns the stored document ID."""
        if not self.vector_store:
            logger.error("Cannot add admin Q&A: Vector store is not initialized.")
            return None

        doc_id = str(uuid.uuid4())
        metadata = {
            "source": "admin_manual",
            "admin_id": int(admin_id),
            "record_type": "qa_pair",
        }
        text = self._format_qa_text(question=question, answer=answer)

        try:
            self.vector_store.add_texts(texts=[text], metadatas=[metadata], ids=[doc_id])
            return doc_id
        except Exception as e:
            logger.error(f"Failed to add admin Q&A pair: {e}")
            return None

    def list_knowledge_entries(self, limit: int = 20, offset: int = 0) -> list[dict]:
        """Returns a paginated list of stored knowledge entries."""
        if not self.vector_store:
            return []

        try:
            data = self.vector_store.get(
                include=["documents", "metadatas"],
                limit=limit,
                offset=offset,
            )
            ids = data.get("ids", []) or []
            documents = data.get("documents", []) or []
            metadatas = data.get("metadatas", []) or []

            entries: list[dict] = []
            for idx, doc_id in enumerate(ids):
                entries.append(
                    {
                        "id": doc_id,
                        "document": documents[idx] if idx < len(documents) else "",
                        "metadata": metadatas[idx] if idx < len(metadatas) else {},
                    }
                )
            return entries
        except Exception as e:
            logger.error(f"Failed to list knowledge entries: {e}")
            return []

    def get_knowledge_entry(self, doc_id: str) -> dict | None:
        """Returns one knowledge entry by ID."""
        if not self.vector_store:
            return None

        try:
            data = self.vector_store.get(ids=[doc_id], include=["documents", "metadatas"])
            ids = data.get("ids", []) or []
            if not ids:
                return None

            documents = data.get("documents", []) or []
            metadatas = data.get("metadatas", []) or []
            return {
                "id": ids[0],
                "document": documents[0] if documents else "",
                "metadata": metadatas[0] if metadatas else {},
            }
        except Exception as e:
            logger.error(f"Failed to get knowledge entry {doc_id}: {e}")
            return None

    def upsert_knowledge_entry(self, doc_id: str, question: str, answer: str, admin_id: int) -> bool:
        """Updates or inserts a knowledge entry by ID."""
        if not self.vector_store:
            logger.error("Cannot update knowledge entry: Vector store is not initialized.")
            return False

        metadata = {
            "source": "admin_manual",
            "admin_id": int(admin_id),
            "record_type": "qa_pair",
            "updated_by_admin": int(admin_id),
        }
        text = self._format_qa_text(question=question, answer=answer)

        try:
            self.vector_store.add_texts(texts=[text], metadatas=[metadata], ids=[doc_id])
            return True
        except Exception as e:
            logger.error(f"Failed to upsert knowledge entry {doc_id}: {e}")
            return False

    def delete_knowledge_entry(self, doc_id: str) -> bool:
        """Deletes one knowledge entry by ID."""
        if not self.vector_store:
            logger.error("Cannot delete knowledge entry: Vector store is not initialized.")
            return False

        try:
            self.vector_store.delete(ids=[doc_id])
            return True
        except Exception as e:
            logger.error(f"Failed to delete knowledge entry {doc_id}: {e}")
            return False

    def count_knowledge_entries(self) -> int:
        """Returns total number of entries in the vector store."""
        if not self.vector_store:
            return 0

        try:
            return self.vector_store._collection.count()
        except Exception as e:
            logger.error(f"Failed to count knowledge entries: {e}")
            return 0
