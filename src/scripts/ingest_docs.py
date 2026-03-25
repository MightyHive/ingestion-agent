import os
import sys

# Project root is two levels above this script
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
sys.path.append(repo_root)

from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_chroma import Chroma

from src.config.settings import settings


def ingest_documents() -> None:
    print("📚 Loading documents from 'docs/'...")

    loader = DirectoryLoader("./docs", glob="**/*.txt", loader_cls=TextLoader)
    documents = loader.load()

    if not documents:
        print("⚠️ No documents found in 'docs/'.")
        return

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = text_splitter.split_documents(documents)

    print(f"✂️ Split into {len(chunks)} chunks.")

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=settings.GOOGLE_API_KEY,
    )

    print("🧠 Persisting vectors to local Chroma...")
    Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory="./chroma_db",
    )

    print("✅ Ingestion complete.")


if __name__ == "__main__":
    ingest_documents()
