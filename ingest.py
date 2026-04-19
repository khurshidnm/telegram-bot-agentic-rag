import os
import shutil
import logging
from dotenv import load_dotenv
from langchain_community.document_loaders import DirectoryLoader, TextLoader, PyPDFLoader, Docx2txtLoader, UnstructuredExcelLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

DOCS_DIR = "./docs"
PERSIST_DIR = "./chroma_db"

# Markdown headers to split on — preserves section context
MARKDOWN_HEADERS = [
    ("#", "topic"),
    ("##", "section"),
    ("###", "subsection"),
]


def split_markdown_documents(docs):
    """
    Smart splitting for Markdown documents.
    1. First splits by Markdown headers (keeping section context).
    2. Then splits large sections into smaller chunks with overlap.
    Each chunk gets a prefix like "Topic: Bank & Cash Operations > Section: Step-by-Step SOPs"
    so the AI always knows what topic the chunk belongs to.
    """
    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=MARKDOWN_HEADERS,
        strip_headers=False,
    )

    # Secondary splitter for large sections
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=200,
        add_start_index=True,
    )

    all_chunks = []

    for doc in docs:
        # Step 1: Split by markdown headers
        header_splits = md_splitter.split_text(doc.page_content)

        for header_doc in header_splits:
            # Build a context prefix from the headers
            context_parts = []
            for key in ["topic", "section", "subsection"]:
                if key in header_doc.metadata:
                    context_parts.append(f"{key.capitalize()}: {header_doc.metadata[key]}")

            context_prefix = " > ".join(context_parts)

            # Step 2: If the section is too long, split it further
            sub_chunks = text_splitter.split_text(header_doc.page_content)

            for chunk_text in sub_chunks:
                # Prepend the section context to every chunk so the AI
                # always knows what topic this chunk belongs to
                enriched_text = f"[{context_prefix}]\n\n{chunk_text}" if context_prefix else chunk_text

                metadata = {
                    **doc.metadata,
                    **header_doc.metadata,
                    "context_prefix": context_prefix,
                }

                all_chunks.append(Document(page_content=enriched_text, metadata=metadata))

    return all_chunks


def split_generic_documents(docs):
    """Standard splitting for non-Markdown documents (PDF, DOCX, etc.)."""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=200,
        add_start_index=True,
    )
    return text_splitter.split_documents(docs)


def ingest_documents():
    """Reads docs from the docs folder, chunks them, and stores them in ChromaDB."""
    if not os.path.exists(DOCS_DIR):
        logger.error(f"Directory {DOCS_DIR} does not exist. Create it and add some documents.")
        return

    logger.info("Loading documents...")
    text_loader_kwargs = {'autodetect_encoding': True}

    # Separate markdown files from other formats
    md_loader = DirectoryLoader(DOCS_DIR, glob="**/*.md", loader_cls=TextLoader, loader_kwargs=text_loader_kwargs)
    other_loaders = [
        DirectoryLoader(DOCS_DIR, glob="**/*.txt", loader_cls=TextLoader, loader_kwargs=text_loader_kwargs),
        DirectoryLoader(DOCS_DIR, glob="**/*.pdf", loader_cls=PyPDFLoader),
        DirectoryLoader(DOCS_DIR, glob="**/*.docx", loader_cls=Docx2txtLoader),
        DirectoryLoader(DOCS_DIR, glob="**/*.xlsx", loader_cls=UnstructuredExcelLoader),
    ]

    # Load markdown docs
    md_docs = []
    try:
        md_docs = md_loader.load()
        logger.info(f"Loaded {len(md_docs)} Markdown documents.")
    except Exception as e:
        logger.error(f"Error loading Markdown documents: {e}")

    # Load other docs
    other_docs = []
    for loader in other_loaders:
        try:
            loaded = loader.load()
            logger.info(f"Loaded {len(loaded)} documents.")
            other_docs.extend(loaded)
        except Exception as e:
            logger.error(f"Error loading documents: {e}")

    if not md_docs and not other_docs:
        logger.warning("No documents found to ingest.")
        return

    # Smart splitting
    all_chunks = []

    if md_docs:
        logger.info("Splitting Markdown documents with header-aware splitter...")
        md_chunks = split_markdown_documents(md_docs)
        logger.info(f"Created {len(md_chunks)} Markdown chunks (with section context).")
        all_chunks.extend(md_chunks)

    if other_docs:
        logger.info("Splitting other documents with standard splitter...")
        other_chunks = split_generic_documents(other_docs)
        logger.info(f"Created {len(other_chunks)} standard chunks.")
        all_chunks.extend(other_chunks)

    logger.info(f"Total chunks to ingest: {len(all_chunks)}")

    # Preview first 3 chunks for debugging
    for i, chunk in enumerate(all_chunks[:3]):
        logger.info(f"--- Sample Chunk {i+1} ---")
        logger.info(chunk.page_content[:200] + "...")

    # Clear old database to prevent duplicate entries
    if os.path.exists(PERSIST_DIR):
        logger.info("Clearing old vector store to prevent duplicates...")
        shutil.rmtree(PERSIST_DIR)

    logger.info("Initializing embeddings and ChromaDB...")
    embeddings = OpenAIEmbeddings()

    # Create and persist the vector store
    vectorstore = Chroma.from_documents(
        documents=all_chunks,
        embedding=embeddings,
        persist_directory=PERSIST_DIR,
    )

    logger.info(f"Ingestion complete. {len(all_chunks)} chunks stored in vector database.")


if __name__ == "__main__":
    ingest_documents()
