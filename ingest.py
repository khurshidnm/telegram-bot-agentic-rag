import os
import logging
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader, Docx2txtLoader, UnstructuredExcelLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

DOCS_DIR = "./docs"
PERSIST_DIR = "./chroma_db"

def ingest_documents():
    """Reads docs from the docs folder, chunks them, and stores them in ChromaDB."""
    if not os.path.exists(DOCS_DIR):
        logger.error(f"Directory {DOCS_DIR} does not exist. Create it and add some documents.")
        return

    logger.info("Loading documents...")
    text_loader_kwargs={'autodetect_encoding': True}
    
    loaders = [
        DirectoryLoader(DOCS_DIR, glob="**/*.txt", loader_cls=TextLoader, loader_kwargs=text_loader_kwargs),
        DirectoryLoader(DOCS_DIR, glob="**/*.md", loader_cls=TextLoader, loader_kwargs=text_loader_kwargs),
        DirectoryLoader(DOCS_DIR, glob="**/*.pdf", loader_cls=PyPDFLoader),
        DirectoryLoader(DOCS_DIR, glob="**/*.docx", loader_cls=Docx2txtLoader),
        DirectoryLoader(DOCS_DIR, glob="**/*.xlsx", loader_cls=UnstructuredExcelLoader)
    ]
    
    docs = []
    for loader in loaders:
        try:
            loaded_docs = loader.load()
            logger.info(f"Loaded {len(loaded_docs)} documents.")
            docs.extend(loaded_docs)
        except Exception as e:
            logger.error(f"Error loading documents with {loader.__class__.__name__}: {e}")

    if not docs:
        logger.warning("No documents found to ingest.")
        return

    logger.info("Splitting documents into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True,
    )
    splits = text_splitter.split_documents(docs)
    logger.info(f"Created {len(splits)} chunks.")

    logger.info("Initializing embeddings and ChromaDB...")
    embeddings = OpenAIEmbeddings()
    
    # Create and persist the vector store
    vectorstore = Chroma.from_documents(
        documents=splits,
        embedding=embeddings,
        persist_directory=PERSIST_DIR
    )
    
    logger.info("Ingestion complete. Vector store persisted.")

if __name__ == "__main__":
    ingest_documents()
